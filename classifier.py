"""Rule-based classifier: topics, impact, audiences, action-required, deadline.

Deliberately transparent (keyword rules) so every tag can be explained in an
interview. Swap `classify` for an LLM/TF-IDF model later if wanted.
"""
import re
from datetime import date, datetime

TOPIC_RULES = {
    "AML/CTF": ["aml", "ctf", "money laundering", "counter-terrorism financing",
                "austrac", "suspicious matter", "smr", "threshold transaction",
                "customer due diligence", "kyc", "tranche 2", "reporting entity"],
    "Superannuation": ["superannuation", "super guarantee", "sg rate", "payday super",
                       "super fund", "choice of fund"],
    "Payroll": ["payroll", "payg", "withholding", "stp", "single touch payroll",
                "payslip", "wages"],
    "Tax": ["income tax", "gst", "fringe benefits", "land tax", "tax return",
            "bas ", "ato ", "deduction", "capital gains"],
    "Employment": ["fair work", "award", "minimum wage", "modern award",
                   "unfair dismissal", "enterprise agreement", "leave entitlement",
                   "casual", "employee"],
    "Trust Accounts": ["trust account", "trust money", "legal practitioner",
                       "law society", "legal services council", "conveyancing"],
    "Property": ["property", "settlement", "stamp duty", "pexa", "conveyanc",
                 "strata", "title"],
    "Privacy & Data": ["privacy", "data breach", "notifiable data", "oaic",
                       "cyber security"],
    "Sanctions": ["sanction", "dfat", "autonomous sanctions", "pep "],
}

HIGH_WORDS = ["mandatory", "must ", "penalt", "enforcement", "infringement",
              "civil penalty", "breach", "new obligation", "obligations",
              "legislation", "act ", "amendment", "commence", "from 1 july",
              "effective", "compliance deadline", "court"]
MED_WORDS = ["guidance", "update", "consultation", "changes", "review", "draft",
             "reminder", "clarif"]

AUDIENCE_RULES = {
    "Law firms": ["law firm", "legal practitioner", "solicitor", "lawyer",
                  "legal services", "trust account", "conveyanc"],
    "Accountants": ["accountant", "tax agent", "bookkeeper", "bas agent"],
    "Real estate": ["real estate", "property", "agent", "settlement", "strata"],
    "Employers": ["employer", "payroll", "super guarantee", "award", "wages",
                  "employee"],
    "Reporting entities": ["reporting entity", "austrac", "aml", "tranche 2"],
}

ACTION_WORDS = ["must", "required to", "deadline", "by 1 ", "by 30 ", "from 1 ",
                "register", "enrol", "lodge", "report by", "due", "mandatory",
                "need to", "prepare for"]

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\s+(20\d{2})\b", re.I)


def _hits(text: str, words: list[str]) -> int:
    return sum(1 for w in words if w in text)


def extract_deadline(text: str, published: date) -> date | None:
    """Return the earliest explicit future date mentioned in the text."""
    found = []
    for d, m, y in _DATE_RE.findall(text):
        try:
            dt = date(int(y), MONTHS[m.lower()], int(d))
        except ValueError:
            continue
        if dt >= published:
            found.append(dt)
    return min(found) if found else None


def classify(title: str, summary: str, published: date) -> dict:
    text = f" {title} {summary} ".lower()

    topics = [t for t, kws in TOPIC_RULES.items() if _hits(text, kws)]
    audiences = [a for a, kws in AUDIENCE_RULES.items() if _hits(text, kws)]

    high, med = _hits(text, HIGH_WORDS), _hits(text, MED_WORDS)
    if high >= 2:
        impact = "High"
    elif high == 1 or med >= 2:
        impact = "Medium"
    else:
        impact = "Low"

    deadline = extract_deadline(f"{title}. {summary}", published)
    action = int(_hits(text, ACTION_WORDS) >= 1 and (impact != "Low" or deadline is not None))

    return {
        "topics": ", ".join(topics) or "Other",
        "impact": impact,
        "audiences": ", ".join(audiences) or "General",
        "action_req": action,
        "deadline": deadline.isoformat() if deadline else None,
    }
