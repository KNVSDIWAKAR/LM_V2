"""Source adapters and report bookkeeping for retention only; no LLM or network calls.

Missing JSON keys stay missing. In particular, bank `balance` is NOT a deposit amount,
an extraction timestamp is NOT a document date, and GSE is NOT proof of FNMA ownership.
"""

import re
from copy import deepcopy
from datetime import date, datetime
from functools import wraps

from .registry import node


# Optional audit metadata, never eligibility policy. Keep the report shape stable
# when the harness omits confidence; explicit YAML values override these defaults.
DEFAULT_CONFIDENCE = {"high": 0.98, "medium": 0.92, "inferred": 0.85, "default": 0.50, "decimals": 2}


def norm(value):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(value or "").lower())).strip()


def parse_date(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            pass
    return None


def number(value):
    try:
        return float(value) if value is not None and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


def contains(text, keywords):
    text = f" {norm(text)} "
    return any(f" {norm(word)} " in text for word in keywords)


def classify(text, mapping):
    # Income labels include stems (salaries/salary), so use normalized substring matching.
    text = norm(text)
    return next((label for label, words in mapping.items() if any(norm(w) in text for w in words)), None)


def dated_notes(msp):
    screen = msp.get("nots") or {}
    dates = msp.get("lmt3") or {}
    lo, hi = parse_date(dates.get("review_date_minus_10")), parse_date(dates.get("review_start_date"))
    if lo is None or hi is None:
        return []
    out = []
    for item in screen.get("notes", []):
        # The seed stores strings with a screen-level latest_note_date. Structured dated
        # notes, when present, use their own date instead of borrowing that screen date.
        text = item.get("text", "") if isinstance(item, dict) else item
        stamp = item.get("date") if isinstance(item, dict) else screen.get("latest_note_date")
        day = parse_date(stamp)
        if day and lo <= day <= hi:
            out.append({"text": str(text), "date": day.isoformat()})
    return out


def primary_stubs(context):
    name = norm(context["msp"]["borrower_name"])
    return [s for s in context["documents"].get("paystubs") or [] if norm(s.get("employee_name")) == name]


class Evaluation:
    def __init__(self, state, deps):
        self.context = deepcopy(state["context"])
        self.rules = deps.rules
        self.confidence = {**DEFAULT_CONFIDENCE, **(self.rules.get("confidence") or {})}
        self.now = deps.now
        self.report = self.context["report"]
        self.msp = self.context["msp"]
        self.docs = self.context["documents"]
        self.maa = self.docs.get("application_form") or {}
        self.flags = self.context["flags"]
        self.bank = self.docs.get("bank_statement") or {}
        self.loe = self.docs.get("letter_of_explanation") or {}
        self.dates = self.msp.get("lmt3") or {}
        self.notes = self.context["notes"]
        self.note_text = " ".join(n["text"] for n in self.notes)
        self.investor = (self.msp.get("dlq1") or {}).get("investor_type")
        self.policy = self.rules["investors"].get(self.investor, {})
        self.outcome = None

    @property
    def joint(self):
        return bool(self.msp.get("coborrower_name")) or (number((self.msp.get("dlq1") or {}).get("number_of_borrowers")) or 0) > 1

    @property
    def wage(self):
        return self.context.get("wage_sources", [None])[self.context.get("wage_index", 0)]

    @property
    def stubs(self):
        return [s for s in primary_stubs(self.context) if norm(s.get("employer_name")) == norm(self.wage)]

    @property
    def latest(self):
        dated = [s for s in self.stubs if parse_date(s.get("pay_date"))]
        return max(dated, key=lambda s: parse_date(s["pay_date"]), default={})

    def payroll(self, wage=None):
        # Do not attribute joint/unknown account deposits to the primary borrower.
        if norm(self.bank.get("account_holder_name")) != norm(self.msp["borrower_name"]):
            return []
        out = [d for d in self.bank.get("all_deposits", []) if contains(d.get("description"), self.rules["payroll_keywords"])]
        if wage:
            out = [d for d in out if self.employer_matches(wage, d.get("description"))]
        return out

    def employer_matches(self, employer, description):
        a, b = norm(employer), norm(description)
        if not a or not b:
            return False
        # Explicit full-name containment only. Truncated bank descriptions are not proof
        # of a match; they can instead become a fallback source for human review.
        return a in b or b in a

    def note_employers(self):
        found = []
        for note in self.notes:
            for pattern in self.rules["note_employer_patterns"]:
                match = re.search(pattern, note["text"], re.IGNORECASE)
                if match and norm(match[1]) not in [norm(s) for s in found]:
                    found.append(match[1].strip())
        return found

    def stip(self, question_id, key=None, **values):
        template = self.rules["stips"][key or question_id]
        values = {**self.rules["thresholds"], "review_date_minus_90": self.dates.get("review_date_minus_90") or "[review date unavailable]",
                  "borrower_name": self.msp["borrower_name"], **values}
        row = {"stip_id": f"STIP-{len(self.report['stip_list']) + 1:03d}", "question_id": question_id,
               **{k: str(v).format(**values) for k, v in template.items()}}
        if "wage_index" in self.context and question_id in {f"Q{i}" for i in range(12, 20)}:
            row["wage_source"] = self.wage
            row["wage_number"] = self.context["wage_index"] + 1
        self.report["stip_list"].append(row)

    def answer(self, qid, value, level="high", explanation="Primary source checked.", *, stip_key=None,
               force_stip=False, informational=False, not_applicable=False, **extra):
        cfg = self.confidence
        confidence = cfg[level]
        before = len(self.report["stip_list"])
        trigger = (value is None or (value is False and qid in self.rules["false_stip"])
                   or (value is True and qid in self.rules["true_stip"]))
        if not informational and not not_applicable and qid not in self.rules["never_stip"] and (trigger or force_stip):
            self.stip(qid, stip_key)
        failed = len(self.report["stip_list"]) > before
        date_only = qid in self.rules.get("date_only_questions", [])
        # A missing required value fails its check; optional unknown values and
        # date-only outputs have no verdict. Confidence never changes a badge.
        result = "fail" if failed else "pass" if not_applicable else "neutral" if date_only or value is None else "pass"
        row = {"question_id": qid, "question": self.rules["questions"][qid], "answer": value,
               "confidence": confidence, "explanation": explanation,
               "result": result, **extra}
        if date_only:
            row["display_type"] = "date"
        if not_applicable:
            row["not_applicable"] = True
        if "wage_index" in self.context and qid in {f"Q{i}" for i in range(12, 20)} | {"Q15a"}:
            row.update(wage_number=self.context["wage_index"] + 1, wage_source=self.wage)
        self.report["answers"].append(row)
        self.outcome = "yes" if value is True else "no" if value is False else "unknown" if value is None else str(value)
        return row

    def finish(self):
        report = self.report
        cfg = self.confidence
        applicable = [a for a in report["answers"] if not a.get("not_applicable")]
        answered = [a for a in applicable if a["answer"] is not None]
        report["overall_confidence"] = round(sum(a["confidence"] for a in answered) / len(answered), cfg["decimals"]) if answered else cfg["default"]
        # Source confidence is retained only as audit metadata, not a review trigger.
        report["confidence_considered"] = False
        report["question_results_version"] = 2
        report["low_confidence_flags"] = []
        report["stip_count"] = len(report["stip_list"])
        report["dm712_required"] = bool(report["stip_count"])
        report["summary"] = {"total_questions": len(report["answers"]),
                             "passed": sum(a["result"] == "pass" for a in report["answers"]),
                             "failed": sum(a["result"] == "fail" for a in report["answers"]),
                             "neutral": sum(a["result"] == "neutral" for a in report["answers"]),
                             "low_confidence": 0}
        findings = [{"check": f"{a['question_id']} · {a['question']}", "result": a["result"],
                     "detail": a["explanation"], "question_id": a["question_id"], "confidence": a["confidence"],
                     "answer": a["answer"]} for a in report["answers"] if not a.get("not_applicable")]
        findings += [{"check": s["question_id"], "result": "fail", "detail": s["reason"], "document": s["document_required"]} for s in report["stip_list"]]
        return {"context": self.context, "findings": findings, "outcome": self.outcome,
                "detail": self.context.get("exit_reason") or f"{report['stip_count']} stip(s)",
                "review_reason": ""}


def question(qid):
    """Register separate Python nodes while keeping report persistence consistent."""
    def decorate(fn):
        @node(f"retention.{qid}")
        @wraps(fn)
        def execute(state, deps):
            evaluation = Evaluation(state, deps)
            fn(evaluation)
            return evaluation.finish()
        return execute
    return decorate