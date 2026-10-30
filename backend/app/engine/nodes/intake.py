"""Process 1 · Intake & Doc Review — the node functions behind harness/intake/playbook.yaml.

Every threshold and field list comes from harness/intake/rules.yaml (deps.rules); nothing
about the business rules is hard-coded here. Each check appends a finding:
    {"check", "result": pass|fail|review|missing|invalid, "detail", ...}
"""

import re
from datetime import date
from typing import Any

from ... import models
from ..registry import node


def _norm(value: str | None) -> str:
    """Case- and punctuation-insensitive form for comparing names and addresses."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (value or "").lower())).strip()


def _finding(check: str, result: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"check": check, "result": result, "detail": detail, **extra}


def _iso_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


# --------------------------------------------------------------------------- #
# 1 · Access data from the DB
# --------------------------------------------------------------------------- #


@node("intake.load_case")
def load_case(state: dict, deps) -> dict:
    msp = deps.db.get(models.Msp, state["loan_id"])
    if msp is None:
        raise LookupError(f"Loan {state['loan_id']} is not in MSP")
    extracted = deps.db.get(models.ExtractedData, state["loan_id"])

    case = {
        "loan_id": msp.loan_id,
        "received_at": extracted.extracted_at.isoformat() if extracted and extracted.extracted_at else None,
        "extraction_status": extracted.extraction_status if extracted else None,
        "documents": {t: getattr(extracted, t) if extracted else None for t in models.DOCUMENT_TYPES},
        "flags": (extracted.flags if extracted else None) or {},
    }
    msp_view = {
        "borrower_name": msp.borrower_name,
        "coborrower_name": msp.coborrower_name,
        "borrower_ssn_last4": msp.borrower_ssn_last4,
        "coborrower_ssn_last4": msp.coborrower_ssn_last4,
        "property_address": msp.property_address,
        "loan_type": msp.loan_type,
        "bankruptcy": msp.bankruptcy,
        "foreclosure": msp.foreclosure,
        "dlq1": msp.dlq1,
        "lmt3": msp.lmt3,
        "notes": (msp.nots or {}).get("notes", []),
    }
    received = sum(1 for d in case["documents"].values() if d)
    return {
        "context": {"case": case, "msp": msp_view},
        "findings": [],
        "detail": f"{received} of {len(models.DOCUMENT_TYPES)} documents on file",
    }


# --------------------------------------------------------------------------- #
# 2 · Business check: query MSP (BK / FC)
# --------------------------------------------------------------------------- #


@node("intake.msp_check")
def msp_check(state: dict, deps) -> dict:
    rules = deps.rules["bk_fc"]
    msp = state["context"]["msp"]
    bk = msp.get("bankruptcy") or {}
    fc = msp.get("foreclosure") or {}
    findings = list(state.get("findings", []))

    if bk.get("status") in rules["bk_active_statuses"]:
        detail = f"Bankruptcy active — chapter {bk.get('chapter')}, case {bk.get('case_number')}, filed {bk.get('filing_date')}"
        findings.append(_finding("Bankruptcy", "fail", detail, team=rules["bk_team"]))
        return {"outcome": "bk_active", "findings": findings, "detail": f"{detail}. Case goes to {rules['bk_team']} and ends."}
    findings.append(_finding("Bankruptcy", "pass", f"Status {bk.get('status') or 'None'}"))

    sale = _iso_date(fc.get("sale_date"))
    if sale is not None:
        days = (sale - deps.now.date()).days
        if days <= rules["sale_window_days"]:
            detail = f"Foreclosure sale on {sale.isoformat()} — {days} day(s) away (window {rules['sale_window_days']})"
            findings.append(_finding("Foreclosure sale", "review", detail, days_to_sale=days, team=rules["oversight_team"]))
            return {"outcome": "sale_within_window", "findings": findings, "review_reason": detail, "detail": detail}
        findings.append(_finding("Foreclosure sale", "pass", f"Sale on {sale.isoformat()}, {days} days away"))
    else:
        findings.append(_finding("Foreclosure sale", "pass", f"Foreclosure status {fc.get('status') or 'None'}; no sale date"))

    return {"outcome": "clear", "findings": findings, "detail": "No active bankruptcy; no sale inside the window"}


# --------------------------------------------------------------------------- #
# 3 · Required documents received, and the application form matches MSP
# --------------------------------------------------------------------------- #


@node("intake.document_checks")
def document_checks(state: dict, deps) -> dict:
    rules = deps.rules["documents"]
    match = rules["match_msp"]
    msp = state["context"]["msp"]
    docs = state["context"]["case"]["documents"]
    maa = docs.get("application_form") or {}
    findings = list(state.get("findings", []))
    problems: list[dict[str, Any]] = []

    missing = [f"{models.DOCUMENT_TYPES[d]} not received" for d in rules["required"] if not docs.get(d)]
    if missing:
        findings += [_finding("Required documents", "missing", m) for m in missing]
        return {"outcome": "missing", "findings": findings, "detail": "; ".join(missing)}
    findings.append(_finding("Required documents", "pass", "All required documents received"))

    def compare(check: str, document: str, doc_value: Any, msp_value: Any, normalize=_norm) -> None:
        if doc_value is None or msp_value is None:
            return
        ok = normalize(str(doc_value)) == normalize(str(msp_value))
        f = _finding(check, "pass" if ok else "fail", f"{document}: {doc_value!r} vs MSP {msp_value!r}", document=document, doc_value=doc_value, msp_value=msp_value)
        findings.append(f)
        if not ok:
            problems.append(f)

    if match.get("borrower_name"):
        compare("Borrower name", "Application form", maa.get("borrower_name"), msp["borrower_name"])
    if match.get("coborrower_name") and msp.get("coborrower_name"):
        compare("Co-borrower name", "Application form", maa.get("coborrower_name"), msp["coborrower_name"])
    if match.get("borrower_ssn_last4"):
        compare("Borrower SSN", "Application form", maa.get("borrower_ssn_last4"), msp["borrower_ssn_last4"], str)
    if match.get("coborrower_ssn_last4") and msp.get("coborrower_ssn_last4"):
        compare("Co-borrower SSN", "Application form", maa.get("coborrower_ssn_last4"), msp["coborrower_ssn_last4"], str)
    if match.get("property_address"):
        compare("Property address", "Application form", maa.get("property_address"), msp["property_address"])

    if problems:
        reason = "; ".join(f"{p['check']}: {p['detail']}" for p in problems)
        return {"outcome": "mismatch", "findings": findings, "review_reason": reason, "detail": f"{len(problems)} mismatch(es) for review"}
    return {"outcome": "clear", "findings": findings, "detail": "Application form received and matches MSP"}


# --------------------------------------------------------------------------- #
# 4 · Send the pack to the next stage and hand off
# --------------------------------------------------------------------------- #


@node("intake.handoff")
def handoff(state: dict, deps) -> dict:
    cfg = deps.rules["handoff"]
    docs = state["context"]["case"]["documents"]
    pack = {
        "loan_number": state["loan_id"],
        "to_team": cfg["team"],
        "checklist": [{"document": models.DOCUMENT_TYPES[d], "received": bool(docs.get(d))} for d in cfg["checklist"]],
        "approved_exceptions": state.get("decision"),
    }
    context = {**state["context"], "handoff": pack}
    return {"context": context, "detail": f"Pack for loan {state['loan_id']} handed to {cfg['team']}"}
