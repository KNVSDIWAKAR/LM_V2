"""The five extracted documents. Each is validated field by field on import (unknown fields are rejected)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Paystub(Strict):
    employee_name: str
    employer_name: str
    employer_ein: str | None = None
    pay_frequency: str
    pay_period_start: str
    pay_period_end: str
    pay_date: str
    gross_current_period: float
    gross_ytd: float | None = None
    net_pay: float | None = None
    annual_salary: float | None = None
    ytd_periods_paid: int | None = None
    has_ytd_earnings: bool
    has_variable_pay: bool
    is_handwritten: bool


class CreditReport(Strict):
    borrower_name: str
    coborrower_name: str | None = None
    borrower_ssn_last4: str | None = None
    coborrower_ssn_last4: str | None = None
    representative_credit_score: int | None = None
    credit_score_equifax: int | None = None
    credit_score_experian: int | None = None
    credit_score_transunion: int | None = None
    mortgage_status: str | None = None
    mortgage_balance: float | None = None
    monthly_mortgage_payment: float | None = None
    monthly_obligations: float | None = None
    total_monthly_payments: float | None = None
    total_balance: float | None = None
    total_debt: float | None = None
    revolving_utilization: float | None = None
    late_payments: str | None = None
    open_accounts: int | None = None
    total_accounts: int | None = None
    collections: int | None = None
    derogatory_marks: int | None = None
    public_records: int | None = None
    recent_hard_inquiries: int | None = None
    hardship_reason: str | None = None


class Deposit(Strict):
    date: str
    type: str
    description: str
    reference_number: str
    balance: float | None = None


class BankStatement(Strict):
    institution_name: str
    account_holder_name: str
    coborrower_on_account: str | None = None
    account_last4: str | None = None
    statement_start_date: str
    statement_end_date: str
    opening_balance: float | None = None
    closing_balance: float | None = None
    all_deposits: list[Deposit] = []
    recurring_deposits_over_250: list[Deposit] = []


class IncomeSource(Strict):
    type: str
    gross_monthly_amount: float


class ApplicationForm(Strict):
    type: str
    borrower_name: str
    coborrower_name: str | None = None
    borrower_ssn_last4: str | None = None
    coborrower_ssn_last4: str | None = None
    property_address: str
    mailing_address: str
    occupancy_status: str | None = None
    desired_workflow: str | None = None
    hardship_reason: str | None = None
    hardship_start_date: str | None = None
    hoa_indicated: bool | None = None
    income_sources: list[IncomeSource] = []
    other_income_amount: float | None = None
    other_income_description: str | None = None
    borrower_signature: bool
    borrower_signature_date: str | None = None
    coborrower_signature: bool
    coborrower_signature_date: str | None = None


class DepositReference(Strict):
    reference: str


class LetterOfExplanation(Strict):
    borrower_name: str
    coborrower_name: str | None = None
    purpose: str
    income_type_explained: str | None = None
    monthly_amount_explained: float | None = None
    duration_of_income: str | None = None
    deposit_references: list[DepositReference] = []
    loe_sufficient: Literal["yes", "no"]


class NeighbourhoodDocument(Strict):
    """Neighbourhood (partial-claim) document used by Final Underwriting. Dates are MM/DD/YYYY as extracted."""

    document_date: str | None = None
    borrower_name: str | None = None
    property_address: str | None = None
    upb: float | None = None
    prior_partial_claim_amounts: list[float] | None = None


class ExtractionFlags(Strict):
    loe_insufficient: bool = False
    only_one_paystub: bool = False
    bank_statement_gap: bool = False
    maa_page_count_issue: bool = False
    missing_borrower_signature: bool = False
    missing_coborrower_signature: bool = False
    paystub_less_than_30_days_employment: bool = False


class DocumentSet(Strict):
    """The five documents for one loan, as stored."""

    application_form: ApplicationForm | None = None
    paystubs: list[Paystub] | None = None
    bank_statement: BankStatement | None = None
    credit_report: CreditReport | None = None
    letter_of_explanation: LetterOfExplanation | None = None
    neighbourhood_document: NeighbourhoodDocument | None = None


# --------------------------------------------------------------------------- #
# Responses
# --------------------------------------------------------------------------- #


class DocumentSummary(BaseModel):
    """One loan's row in the Knowledge Base list."""

    loan_id: str
    borrower_name: str
    coborrower_name: str | None
    extraction_status: str
    extracted_at: datetime | None
    documents: dict[str, bool]  # document type → submitted
    flags: list[str]  # raised flag names


class LoanDocuments(DocumentSet):
    model_config = ConfigDict(extra="ignore")

    loan_id: str
    borrower_name: str
    coborrower_name: str | None
    extraction_status: str
    extracted_at: datetime | None
    flags: ExtractionFlags
    document_labels: dict[str, str]
