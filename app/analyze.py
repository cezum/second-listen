"""Run the debrief playbook over a transcript (file-upload mode).

A pre-recorded clip has no live dialogue, so there is nobody to interrupt. The
playbook runs over the finished transcript and returns:

    signals   — [{dimension, quote, signal, escalation}]
    questions — [{question, for}]

instead of asking them one at a time. This is the same playbook the live agent
uses, applied to text.

The analysis is pluggable. Set an OpenAI-compatible endpoint in .env:

    LLM_BASE_URL  e.g. https://api.deepseek.com/v1   (or DashScope / GLM / Ark)
    LLM_API_KEY   the key for that provider
    LLM_MODEL     e.g. deepseek-chat

Without a key, a keyword matcher over the escalation checklist gives a degraded
but working fallback so the pipeline still runs end to end.
"""

import json
import os
import re
import urllib.error
import urllib.request

# The playbook, in a form an LLM can read and answer against. Kept in sync with
# the system prompt in agents/second-listen.jsonc.
PLAYBOOK_PROMPT = """You are the post-investment debrief partner for a venture investor. Below is a transcript of the investor casually retelling a founder call. Extract risk signals hidden in the remarks, and draft the follow-up questions the checklist demands.

The playbook (risk grading framework):
- Grades: A (healthy, exit potential) / B (stable, self-sustaining) / C (distressed) / G (policy-driven, judged separately). You never assign a grade yourself.
- Five evidence dimensions: operations (revenue/profit/cash trend), exit_potential (IPO or M&A progress), self_funding (margins, operating cash flow, financing), team_integrity (key-person changes, core role vacancies), financial_health (net assets, leverage, receivables, litigation).

Escalation checklist (set escalation=true when a signal matches):
- key personnel loss or core role vacancy (e.g., CFO left, finance unmanaged)
- funds used outside the agreed purpose (e.g., grant money moved to payroll)
- major litigation, violations, or safety/environmental accidents
- breach by the investee harming investors
- equity or control changes
- missed performance targets triggering buyback or compensation
- disbursement beyond 10% of the approved amount, or project delayed 2+ years
- major adverse policy or market changes

Rules:
- Quote the investor's own words for each signal (a short clause).
- Only log real signals from the text; do not invent or speculate.
- For each escalation trigger, write the follow-up question the checklist needs (e.g., who covers the role and since when; was there written approval).
- Ignore small talk (e.g., office renovations).

Return ONLY a JSON object, no prose, with this shape:
{"signals":[{"dimension":"...","quote":"...","signal":"...","escalation":true}],
 "questions":[{"question":"...","for":"..."}]}
If there are no signals, return {"signals":[],"questions":[]}.
"""

# Checklist keyword patterns for the no-LLM fallback. Each maps a regex to a
# (dimension, signal label, escalation flag). Order matters: first match wins
# per pattern so a clause is not double-counted.
_KEYWORD_RULES = [
    (r"(CFO|chief financial|finance (director|head)|财务总监|财务负责人).{0,40}(left|departed|quit|resigned|离开|离职|走了|无人|空缺|vacant|unmanaged)",
     "team_integrity", "key personnel loss / core role vacancy", True),
    (r"(grant|subsidy|研发补助|补助|专项资金|专款).{0,40}(payroll|工资|工资条|diverted|moved|挪|挪用|用于.*发工资)",
     "financial_health", "funds used outside the agreed purpose", True),
    (r"(litigation|lawsuit|sued|起诉|诉讼|被告)", "financial_health",
     "litigation", True),
    (r"(violation|违规|事故|accident|safety|安全)", "financial_health",
     "violation / accident", True),
    (r"(equity|股权|control|控制权).{0,30}(change|changed|变更|转让|稀释)", "team_integrity",
     "equity or control change", True),
    (r"(buyback|回购|compensation|补偿|对赌|业绩未达标|trigger)", "operations",
     "performance target / buyback", True),
    (r"(revenue|营收|收入).{0,40}(flat|走平|持平|stagnant|declin|下滑|下降|负增长)", "operations",
     "revenue trend", False),
    (r"(cash flow|现金流|资金链).{0,40}(negative|不乐观|没.{0,3}乐观|恶化|吃紧|紧张|为负|断裂)", "self_funding",
     "cash flow", False),
]


# Human-readable signal labels and follow-up questions, per language. The
# keyword matcher works for both English and Chinese transcripts; the result
# should read in the same language the investor spoke.
_SIGNAL_LABELS = {
    "key personnel loss / core role vacancy": "关键人员流失 / 核心岗位空缺",
    "funds used outside the agreed purpose": "资金未按约定用途使用",
    "litigation": "诉讼",
    "violation / accident": "违规 / 事故",
    "equity or control change": "股权或控制权变更",
    "performance target / buyback": "业绩目标未达标 / 回购",
    "revenue trend": "营收趋势",
    "cash flow": "现金流",
}


def _label(signal: str, language: str) -> str:
    if language == "zh":
        return _SIGNAL_LABELS.get(signal, signal)
    return signal


def _question(signal: str, language: str) -> str:
    """The single follow-up question the checklist needs, in the speaker's language."""
    if language == "zh":
        if "personnel" in signal or "vacancy" in signal:
            return "相关岗位离职后由谁接手、从什么时候开始？"
        if "funds" in signal:
            return "该笔资金挪作他用，是否有书面审批？"
        if "litigation" in signal:
            return "诉讼相关的书面记录和下一步处理方案是什么？"
        if "violation" in signal:
            return "违规/事故的书面记录和整改方案是什么？"
        if "equity" in signal:
            return "股权/控制权变更的依据和影响是什么？"
        if "performance" in signal or "buyback" in signal:
            return "业绩未达标的书面记录和触发条款是什么？"
        return "是什么驱动了这一变化，是否已在预测中体现？"
    if "personnel" in signal or "vacancy" in signal:
        return "Who is covering the role since they left, and since when?"
    if "funds" in signal:
        return "Was there written approval to use the funds for this purpose?"
    if "litigation" in signal:
        return "Can you share the written record of the litigation and next steps?"
    if "violation" in signal:
        return "Can you share the written record and remediation plan for this?"
    if "equity" in signal:
        return "What is the basis and impact of the equity/control change?"
    if "performance" in signal or "buyback" in signal:
        return "What is the written record and trigger clause for the missed target?"
    return "What is driving the change, and is it in the forecast?"


def analyze_transcript(transcript: str, language: str = None) -> dict:
    if os.environ.get("LLM_API_KEY"):
        return _analyze_with_llm(transcript, language)
    return _analyze_with_keywords(transcript, language)


def _analyze_with_keywords(transcript: str, language: str = None) -> dict:
    signals = []
    questions = []
    seen = set()
    for pattern, dimension, signal, escalation in _KEYWORD_RULES:
        if signal in seen:
            continue
        match = re.search(pattern, transcript, re.IGNORECASE)
        if not match:
            continue
        seen.add(signal)
        quote = match.group(0).strip()
        signals.append({
            "dimension": dimension,
            "quote": quote,
            "signal": _label(signal, language),
            "escalation": escalation,
        })
        questions.append({"question": _question(signal, language), "for": dimension})
    return {"signals": signals, "questions": questions}


def _analyze_with_llm(transcript: str, language: str = None) -> dict:
    base = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "")
    if not base or not model:
        return _analyze_with_keywords(transcript, language)

    lang_hint = "Respond in Simplified Chinese." if language == "zh" else "Respond in English."
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": PLAYBOOK_PROMPT + "\n\n" + lang_hint},
            {"role": "user", "content": transcript},
        ],
        "temperature": 0,
    }).encode()
    req = urllib.request.Request(
        base + "/chat/completions", data=payload, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as res:
            raw = json.loads(res.read().decode())
    except (urllib.error.HTTPError, ValueError) as err:
        # Fall back to keywords rather than failing the whole upload.
        return _analyze_with_keywords(transcript, language)

    content = raw["choices"][0]["message"]["content"]
    # Strip a code fence if the model wrapped the JSON in one.
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"signals": [], "questions": [], "raw": content}
