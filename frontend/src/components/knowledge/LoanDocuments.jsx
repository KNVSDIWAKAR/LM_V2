// Renderers for the five extracted loss-mitigation documents (see backend app/schemas/documents.py).
import { CircleCheck, CircleX, FileX, Link2 } from "lucide-react";
import Card from "../ui/Card";

const mutedFg = { color: "hsl(var(--muted-foreground))" };
const fg = { color: "hsl(var(--foreground))" };
const GOOD = "hsl(142, 60%, 32%)";
const BAD = "hsl(0, 72%, 48%)";
const WARN = "hsl(32, 90%, 38%)";

export const money = (v) =>
  v == null ? "—" : Number(v).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
export const text = (v) => (v == null || v === "" ? "—" : String(v));
export const ssn = (last4) => (last4 ? `•••-••-${last4}` : "—");

export const FLAG_LABELS = {
  loe_insufficient: "Letter of explanation insufficient",
  only_one_paystub: "Only one paystub",
  bank_statement_gap: "Gap in bank statement",
  maa_page_count_issue: "MAA page count issue",
  missing_borrower_signature: "Missing borrower signature",
  missing_coborrower_signature: "Missing co-borrower signature",
  paystub_less_than_30_days_employment: "Paystub shows < 30 days employment",
};

export function YesNo({ value, yes = "Yes", no = "No", goodWhen = true }) {
  if (value == null) return <span style={mutedFg}>—</span>;
  const good = value === goodWhen;
  const Icon = value ? CircleCheck : CircleX;
  return (
    <span className="inline-flex items-center gap-1 font-medium" style={{ color: good ? GOOD : BAD }}>
      <Icon size={13} />
      {value ? yes : no}
    </span>
  );
}

export function Section({ title, children, aside }) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-sans text-xs font-semibold uppercase tracking-widest" style={mutedFg}>
          {title}
        </h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** Label/value pairs in a responsive grid. */
export function Fields({ items, cols = 3 }) {
  return (
    <dl className={`grid grid-cols-1 sm:grid-cols-2 ${cols === 3 ? "lg:grid-cols-3" : ""} gap-x-6 gap-y-3`}>
      {items.map(([label, value]) => (
        <div key={label} className="min-w-0">
          <dt className="font-sans text-[11px] uppercase tracking-wider" style={mutedFg}>
            {label}
          </dt>
          <dd className="font-sans text-sm mt-0.5 break-words" style={fg}>
            {value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Table({ columns, rows, align = {} }) {
  return (
    <div className="overflow-x-auto rounded border" style={{ borderColor: "hsl(var(--border))", borderRadius: "var(--radius)" }}>
      <table className="w-full text-sm font-sans" style={{ borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "hsl(var(--muted))" }}>
            {columns.map((c) => (
              <th
                key={c}
                className="px-3 py-2 text-xs font-semibold uppercase tracking-wider whitespace-nowrap"
                style={{ ...mutedFg, textAlign: align[c] ?? "left" }}
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={{ borderTop: "1px solid hsl(var(--border))" }}>
              {row.map((cell, j) => (
                <td key={j} className="px-3 py-2 align-top" style={{ ...fg, textAlign: align[columns[j]] ?? "left" }}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Application Form (MAA)
// --------------------------------------------------------------------------- //

function ApplicationForm({ doc }) {
  const income = doc.income_sources ?? [];
  const totalIncome = income.reduce((n, s) => n + (s.gross_monthly_amount || 0), 0) + (doc.other_income_amount || 0);
  return (
    <div className="flex flex-col gap-6">
      <Section title="Borrowers">
        <Fields
          items={[
            ["Borrower", doc.borrower_name],
            ["SSN", ssn(doc.borrower_ssn_last4)],
            ["Signed", <span key="s" className="inline-flex gap-2"><YesNo value={doc.borrower_signature} /><span style={mutedFg}>{doc.borrower_signature_date ?? ""}</span></span>],
            ["Co-borrower", text(doc.coborrower_name)],
            ["SSN", ssn(doc.coborrower_ssn_last4)],
            [
              "Signed",
              doc.coborrower_name ? (
                <span key="c" className="inline-flex gap-2"><YesNo value={doc.coborrower_signature} /><span style={mutedFg}>{doc.coborrower_signature_date ?? ""}</span></span>
              ) : (
                "—"
              ),
            ],
          ]}
        />
      </Section>

      <Section title="Property & request">
        <Fields
          items={[
            ["Property address", doc.property_address],
            ["Mailing address", doc.mailing_address],
            ["Occupancy", text(doc.occupancy_status)],
            ["Desired outcome", text(doc.desired_workflow)],
            ["HOA indicated", <YesNo key="h" value={doc.hoa_indicated} goodWhen={doc.hoa_indicated} />],
            ["Form", text(doc.type)],
          ]}
        />
      </Section>

      <Section title="Hardship">
        <Fields
          items={[
            ["Reason", text(doc.hardship_reason)],
            ["Started", text(doc.hardship_start_date)],
          ]}
        />
      </Section>

      <Section title="Monthly income (gross)" aside={<span className="font-sans text-sm font-semibold" style={fg}>{money(totalIncome)} / mo</span>}>
        <Table
          columns={["Source", "Amount"]}
          align={{ Amount: "right" }}
          rows={[
            ...income.map((s) => [
              s.type,
              <span key="a" className="tabular-nums" style={s.gross_monthly_amount ? fg : mutedFg}>{money(s.gross_monthly_amount)}</span>,
            ]),
            [
              `Other income${doc.other_income_description ? ` — ${doc.other_income_description}` : ""}`,
              <span key="o" className="tabular-nums" style={doc.other_income_amount ? fg : mutedFg}>{money(doc.other_income_amount)}</span>,
            ],
          ]}
        />
      </Section>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Paystubs
// --------------------------------------------------------------------------- //

function Paystubs({ doc }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {doc.map((p, i) => (
        <Card key={i} className="flex flex-col gap-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="font-sans text-[11px] uppercase tracking-wider" style={mutedFg}>
                Paystub {i + 1} of {doc.length}
              </p>
              <p className="font-serif text-lg leading-tight" style={fg}>
                {p.employer_name}
              </p>
              <p className="font-sans text-xs" style={mutedFg}>
                EIN {text(p.employer_ein)} · {p.employee_name}
              </p>
            </div>
            <div className="text-right shrink-0">
              <p className="font-sans text-[11px] uppercase tracking-wider" style={mutedFg}>
                Gross this period
              </p>
              <p className="font-serif text-xl tabular-nums" style={fg}>
                {money(p.gross_current_period)}
              </p>
            </div>
          </div>
          <Fields
            cols={2}
            items={[
              ["Pay period", `${p.pay_period_start} – ${p.pay_period_end}`],
              ["Pay date", p.pay_date],
              ["Frequency", p.pay_frequency],
              ["Net pay", money(p.net_pay)],
              ["Gross YTD", money(p.gross_ytd)],
              ["YTD periods paid", text(p.ytd_periods_paid)],
              ["Annual salary", money(p.annual_salary)],
              ["YTD earnings shown", <YesNo key="y" value={p.has_ytd_earnings} />],
              ["Variable pay", <YesNo key="v" value={p.has_variable_pay} goodWhen={false} />],
              ["Handwritten", <YesNo key="h" value={p.is_handwritten} goodWhen={false} />],
            ]}
          />
        </Card>
      ))}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Bank statement
// --------------------------------------------------------------------------- //

function depositKind(description) {
  const d = description.toUpperCase();
  if (d.includes("PAYROLL")) return ["Payroll", "hsl(217, 70%, 45%)"];
  if (d.includes("UNEMPLOYMENT")) return ["Unemployment", WARN];
  if (d.includes("DIVIDEND")) return ["Investment", "hsl(270, 50%, 45%)"];
  if (d.includes("OTHER INCOME")) return ["Other income", GOOD];
  return ["Deposit", "hsl(var(--muted-foreground))"];
}

function BankStatement({ doc }) {
  const deposits = doc.all_deposits ?? [];
  return (
    <div className="flex flex-col gap-6">
      <Section title="Account">
        <Fields
          items={[
            ["Institution", doc.institution_name],
            ["Account holder", doc.account_holder_name],
            ["Joint holder", text(doc.coborrower_on_account)],
            ["Account", doc.account_last4 ? `•••• ${doc.account_last4}` : "—"],
            ["Statement period", `${doc.statement_start_date} – ${doc.statement_end_date}`],
            ["Opening → closing", `${money(doc.opening_balance)} → ${money(doc.closing_balance)}`],
          ]}
        />
      </Section>
      <Section title={`Deposits (${deposits.length})`}>
        <Table
          columns={["Date", "Kind", "Description", "Reference", "Balance after"]}
          align={{ "Balance after": "right" }}
          rows={deposits.map((d) => {
            const [kind, color] = depositKind(d.description);
            return [
              <span key="d" className="tabular-nums whitespace-nowrap">{d.date}</span>,
              <span key="k" className="text-xs font-medium whitespace-nowrap" style={{ color }}>{kind}</span>,
              d.description,
              <span key="r" className="font-mono text-xs" style={mutedFg}>{d.reference_number}</span>,
              <span key="b" className="tabular-nums">{money(d.balance)}</span>,
            ];
          })}
        />
        {(doc.recurring_deposits_over_250 ?? []).length > 0 && (
          <p className="font-sans text-xs" style={mutedFg}>
            {doc.recurring_deposits_over_250.length} recurring deposit(s) over $250 identified.
          </p>
        )}
      </Section>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Credit report
// --------------------------------------------------------------------------- //

function scoreColor(score) {
  if (score == null) return "hsl(var(--muted-foreground))";
  if (score >= 670) return GOOD;
  if (score >= 580) return WARN;
  return BAD;
}

function ScoreTile({ label, score, emphasis }) {
  return (
    <div
      className="rounded-md border px-4 py-3 flex flex-col gap-0.5"
      style={{
        borderColor: emphasis ? scoreColor(score) : "hsl(var(--border))",
        background: emphasis ? "hsl(var(--muted))" : "hsl(var(--card))",
      }}
    >
      <span className="font-sans text-[11px] uppercase tracking-wider" style={mutedFg}>
        {label}
      </span>
      <span className="font-serif text-2xl tabular-nums leading-none" style={{ color: scoreColor(score) }}>
        {score ?? "—"}
      </span>
    </div>
  );
}

function CreditReport({ doc }) {
  return (
    <div className="flex flex-col gap-6">
      <Section title="Scores">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <ScoreTile label="Representative" score={doc.representative_credit_score} emphasis />
          <ScoreTile label="Equifax" score={doc.credit_score_equifax} />
          <ScoreTile label="Experian" score={doc.credit_score_experian} />
          <ScoreTile label="TransUnion" score={doc.credit_score_transunion} />
        </div>
      </Section>
      <Section title="Mortgage">
        <Fields
          items={[
            ["Status", text(doc.mortgage_status)],
            ["Balance", money(doc.mortgage_balance)],
            ["Monthly payment", money(doc.monthly_mortgage_payment)],
            ["Late payments", text(doc.late_payments)],
            ["Hardship (as reported)", text(doc.hardship_reason)],
          ]}
        />
      </Section>
      <Section title="Obligations & accounts">
        <Fields
          items={[
            ["Monthly obligations", money(doc.monthly_obligations)],
            ["Total monthly payments", money(doc.total_monthly_payments)],
            ["Total balance", money(doc.total_balance)],
            ["Open / total accounts", `${text(doc.open_accounts)} / ${text(doc.total_accounts)}`],
            ["Revolving utilization", doc.revolving_utilization == null ? "—" : `${doc.revolving_utilization}%`],
            ["Recent hard inquiries", text(doc.recent_hard_inquiries)],
          ]}
        />
      </Section>
      <Section title="Derogatory">
        <Fields
          items={[
            ["Derogatory marks", text(doc.derogatory_marks)],
            ["Collections", text(doc.collections)],
            ["Public records", text(doc.public_records)],
          ]}
        />
      </Section>
      <Section title="Identity">
        <Fields
          items={[
            ["Borrower", `${doc.borrower_name} · ${ssn(doc.borrower_ssn_last4)}`],
            ["Co-borrower", doc.coborrower_name ? `${doc.coborrower_name} · ${ssn(doc.coborrower_ssn_last4)}` : "—"],
          ]}
        />
      </Section>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Letter of explanation
// --------------------------------------------------------------------------- //

function LetterOfExplanation({ doc, bankStatement }) {
  const deposits = Object.fromEntries((bankStatement?.all_deposits ?? []).map((d) => [d.reference_number, d]));
  const sufficient = doc.loe_sufficient === "yes";
  return (
    <div className="flex flex-col gap-6">
      <div
        className="rounded-md border px-4 py-3 font-sans text-sm"
        style={{ borderColor: sufficient ? GOOD : BAD, background: "hsl(var(--card))", ...fg }}
      >
        <span className="font-semibold" style={{ color: sufficient ? GOOD : BAD }}>
          {sufficient ? "Sufficient" : "Insufficient"}
        </span>{" "}
        — {doc.purpose}
      </div>
      <Section title="Explanation">
        <Fields
          items={[
            ["Income explained", text(doc.income_type_explained)],
            ["Monthly amount", money(doc.monthly_amount_explained)],
            ["Duration", text(doc.duration_of_income)],
            ["Borrower", doc.borrower_name],
            ["Co-borrower", text(doc.coborrower_name)],
          ]}
        />
      </Section>
      <Section title={`Deposits referenced (${(doc.deposit_references ?? []).length})`}>
        <Table
          columns={["Reference", "In bank statement", "Date", "Description"]}
          rows={(doc.deposit_references ?? []).map(({ reference }) => {
            const match = deposits[reference];
            return [
              <span key="r" className="font-mono text-xs">{reference}</span>,
              match ? (
                <span key="m" className="inline-flex items-center gap-1 text-xs font-medium" style={{ color: GOOD }}><Link2 size={12} />Matched</span>
              ) : (
                <span key="m" className="text-xs font-medium" style={{ color: BAD }}>Not found</span>
              ),
              match?.date ?? "—",
              match?.description ?? "—",
            ];
          })}
        />
      </Section>
    </div>
  );
}

// --------------------------------------------------------------------------- //

export function NotSubmitted({ label }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-16 text-center">
      <FileX size={28} style={{ ...mutedFg, opacity: 0.6 }} />
      <p className="font-sans text-sm font-medium" style={fg}>
        {label} not submitted
      </p>
      <p className="font-sans text-xs" style={mutedFg}>
        Nothing was extracted for this document.
      </p>
    </div>
  );
}

/** Render one document of a loan's package by its type key. */
export function DocumentBody({ type, docs }) {
  const doc = docs[type];
  const label = docs.document_labels?.[type] ?? type;
  if (doc == null || (Array.isArray(doc) && doc.length === 0)) return <NotSubmitted label={label} />;
  switch (type) {
    case "application_form":
      return <ApplicationForm doc={doc} />;
    case "paystubs":
      return <Paystubs doc={doc} />;
    case "bank_statement":
      return <BankStatement doc={doc} />;
    case "credit_report":
      return <CreditReport doc={doc} />;
    case "letter_of_explanation":
      return <LetterOfExplanation doc={doc} bankStatement={docs.bank_statement} />;
    default:
      return <pre className="font-mono text-xs whitespace-pre-wrap">{JSON.stringify(doc, null, 2)}</pre>;
  }
}
