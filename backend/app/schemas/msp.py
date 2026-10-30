"""MSP loan profile and its screens. Used to validate imports and to shape responses."""

from datetime import date

from pydantic import BaseModel, ConfigDict


class Screen(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class Bankruptcy(Screen):
    status: str
    chapter: str | None = None
    case_number: str | None = None
    filing_date: date | None = None
    closed_date: date | None = None


class Foreclosure(Screen):
    status: str
    referral_date: date | None = None
    sale_date: date | None = None


class Hoa(Screen):
    hoa_exists: bool
    monthly_amount: float
    association_name: str | None = None


class Ana1(Screen):
    tax_bill_date: date | None = None
    escrow_current: bool
    tax_bill_on_file: bool
    escrow_payment_amount: float


class Payment(Screen):
    """One payment MSP posted to the loan. Trial Monitoring matches these to installments."""

    payment_date: date
    amount: float
    transaction_type: str | None = None
    reference: str | None = None


class Dlq1(Screen):
    due_date: date | None = None
    loan_type: str
    upb_balance: float
    investor_type: str
    property_state: str
    mailing_address: str
    property_address: str
    months_delinquent: int
    number_of_borrowers: int
    interest_rate: float | None = None  # current note rate, percent
    # Payments received; None means MSP did not send history (not the same as "no payments").
    payment_history: list[Payment] | None = None


class Haz1(Screen):
    carrier: str
    policy_number: str
    policy_current: bool
    policy_expiry_date: date | None = None


class Lmt1(Screen):
    mod_status: str | None = None
    loan_type_status: str = ""
    status_description: str = ""


class Lmt3(Screen):
    l92_date: date | None = None
    review_start_date: date | None = None
    review_date_minus_10: date | None = None
    review_date_minus_90: date | None = None
    # Closing-code dates checked by Final Underwriting (must run in this order, on working days).
    x65_date: date | None = None
    e74_date: date | None = None
    j03_date: date | None = None
    x58_date: date | None = None
    e68_date: date | None = None


class Nots(Screen):
    notes: list[str] = []
    latest_note_date: date | None = None


class Usr2(Screen):
    status: str


class Task(Screen):
    task_id: str
    status: str
    description: str | None = None
    opened_date: date | None = None
    completed_date: date | None = None


class TaskScreen(Screen):
    """TASK1 / MES1: open and completed servicing tasks."""

    tasks: list[Task] = []


class Lsmr(Screen):
    """LSMR: the permanent modification terms."""

    current_interest_rate: float | None = None
    new_interest_rate: float | None = None
    new_term_months: int | None = None
    new_principal_balance: float | None = None
    new_payment_amount: float | None = None
    first_payment_date: date | None = None
    maturity_date: date | None = None


class ServicingData(Screen):
    """The MSP screens, keyed by screen code."""

    ANA1: Ana1 | None = None
    DLQ1: Dlq1 | None = None
    HAZ1: Haz1 | None = None
    LMT1: Lmt1 | None = None
    LMT3: Lmt3 | None = None
    NOTS: Nots | None = None
    USR2: Usr2 | None = None
    TASK1: TaskScreen | None = None
    MES1: TaskScreen | None = None
    LSMR: Lsmr | None = None


class MspLoanBase(Screen):
    loan_id: str
    borrower_name: str
    coborrower_name: str | None = None
    borrower_ssn_last4: str
    coborrower_ssn_last4: str | None = None
    property_address: str
    mailing_address: str
    loan_type: str


class MspLoanIn(MspLoanBase):
    """One loan exactly as it arrives from MSP."""

    bankruptcy: Bankruptcy | None = None
    foreclosure: Foreclosure | None = None
    hoa: Hoa | None = None
    servicing_data: ServicingData = ServicingData()


class MspLoanSummary(MspLoanBase):
    investor_type: str | None
    property_state: str | None
    months_delinquent: int | None
    upb_balance: float | None
    bankruptcy_status: str | None
    foreclosure_status: str | None


class MspLoanOut(MspLoanIn):
    pass
