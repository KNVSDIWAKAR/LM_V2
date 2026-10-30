import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CircleAlert, LoaderCircle, Search, Server, StickyNote } from "lucide-react";
import Card from "../components/ui/Card";
import { Fields, Section, YesNo, money, ssn, text } from "../components/knowledge/LoanDocuments";
import { apiGet } from "../lib/api";

const mutedFg = { color: "hsl(var(--muted-foreground))" };
const fg = { color: "hsl(var(--foreground))" };
const BAD = "hsl(0, 72%, 48%)";
const WARN = "hsl(32, 90%, 38%)";

/** ISO date (YYYY-MM-DD) → "Mar 10, 2026", read as a calendar date so it never shifts a day. */
function day(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

// The MSP screens in the order a servicer works them, with what each one is.
const SCREENS = [
  { key: "overview", label: "Overview", hint: "Borrowers, property, bankruptcy, foreclosure, HOA" },
  { key: "DLQ1", label: "DLQ1", hint: "Delinquency" },
  { key: "ANA1", label: "ANA1", hint: "Escrow analysis" },
  { key: "HAZ1", label: "HAZ1", hint: "Hazard insurance" },
  { key: "LMT1", label: "LMT1", hint: "Loss-mitigation status" },
  { key: "LMT3", label: "LMT3", hint: "Loss-mitigation review dates" },
  { key: "NOTS", label: "NOTS", hint: "Servicing notes" },
  { key: "USR2", label: "USR2", hint: "User-defined status" },
];

const isActive = (status) => status && status !== "None";

function Status({ icon: Icon, children, spin }) {
  return (
    <div className="flex items-center gap-2 py-12 justify-center" style={mutedFg}>
      <Icon size={18} className={spin ? "animate-spin" : undefined} />
      <span className="font-sans text-sm">{children}</span>
    </div>
  );
}

function Chip({ children, color }) {
  return (
    <span className="font-sans text-[11px] font-medium px-1.5 py-0.5 rounded border whitespace-nowrap" style={{ color, borderColor: color }}>
      {children}
    </span>
  );
}

function LoanRow({ loan, active, onSelect }) {
  return (
    <button
      onClick={onSelect}
      className="w-full text-left px-3 py-2.5 rounded-md border transition-colors"
      style={{
        background: active ? "hsl(var(--muted))" : "hsl(var(--card))",
        borderColor: active ? "hsl(var(--primary) / 0.35)" : "hsl(var(--border))",
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-sans text-sm font-medium truncate" style={fg}>
          {loan.borrower_name}
        </span>
        {loan.months_delinquent != null && (
          <span className="font-sans text-[11px] shrink-0 tabular-nums" style={loan.months_delinquent >= 3 ? { color: BAD } : mutedFg}>
            {loan.months_delinquent} mo DLQ
          </span>
        )}
      </div>
      <div className="flex items-center justify-between gap-2 mt-1">
        <span className="font-mono text-xs" style={mutedFg}>
          {loan.loan_id}
        </span>
        <span className="flex gap-1">
          {isActive(loan.foreclosure_status) && <Chip color={BAD}>FC</Chip>}
          {isActive(loan.bankruptcy_status) && <Chip color={WARN}>BK</Chip>}
          {loan.property_state && <span className="font-sans text-[11px]" style={mutedFg}>{loan.property_state}</span>}
        </span>
      </div>
    </button>
  );
}

function Overview({ loan }) {
  const bk = loan.bankruptcy ?? {};
  const fc = loan.foreclosure ?? {};
  const hoa = loan.hoa ?? {};
  return (
    <div className="flex flex-col gap-6">
      <Section title="Borrowers">
        <Fields
          items={[
            ["Borrower", loan.borrower_name],
            ["SSN", ssn(loan.borrower_ssn_last4)],
            ["Loan type", loan.loan_type],
            ["Co-borrower", text(loan.coborrower_name)],
            ["SSN", ssn(loan.coborrower_ssn_last4)],
          ]}
        />
      </Section>
      <Section title="Property">
        <Fields
          cols={2}
          items={[
            ["Property address", loan.property_address],
            ["Mailing address", loan.mailing_address],
          ]}
        />
      </Section>
      <Section title="Bankruptcy" aside={isActive(bk.status) && <Chip color={WARN}>{bk.status}</Chip>}>
        <Fields
          items={[
            ["Status", text(bk.status)],
            ["Chapter", text(bk.chapter)],
            ["Case number", text(bk.case_number)],
            ["Filed", day(bk.filing_date)],
            ["Closed", day(bk.closed_date)],
          ]}
        />
      </Section>
      <Section title="Foreclosure" aside={isActive(fc.status) && <Chip color={BAD}>{fc.status}</Chip>}>
        <Fields
          items={[
            ["Status", text(fc.status)],
            ["Referred", day(fc.referral_date)],
            ["Sale date", day(fc.sale_date)],
          ]}
        />
      </Section>
      <Section title="HOA">
        <Fields
          items={[
            ["HOA", <YesNo key="h" value={hoa.hoa_exists} goodWhen={hoa.hoa_exists} />],
            ["Association", text(hoa.association_name)],
            ["Monthly dues", money(hoa.monthly_amount)],
          ]}
        />
      </Section>
    </div>
  );
}

function ScreenBody({ screen, loan }) {
  if (screen === "overview") return <Overview loan={loan} />;
  const data = loan.servicing_data?.[screen];
  if (!data) return <Status icon={Server}>No {screen} screen on file for this loan.</Status>;

  switch (screen) {
    case "DLQ1":
      return (
        <Fields
          items={[
            ["Months delinquent", <span key="m" className="font-semibold" style={data.months_delinquent >= 3 ? { color: BAD } : fg}>{data.months_delinquent}</span>],
            ["Next due date", day(data.due_date)],
            ["Unpaid principal balance", money(data.upb_balance)],
            ["Investor", data.investor_type],
            ["Loan type", data.loan_type],
            ["Borrowers on loan", data.number_of_borrowers],
            ["Property state", data.property_state],
            ["Property address", data.property_address],
            ["Mailing address", data.mailing_address],
          ]}
        />
      );
    case "ANA1":
      return (
        <Fields
          items={[
            ["Escrow payment", money(data.escrow_payment_amount)],
            ["Escrow current", <YesNo key="e" value={data.escrow_current} />],
            ["Tax bill on file", <YesNo key="t" value={data.tax_bill_on_file} />],
            ["Tax bill date", day(data.tax_bill_date)],
          ]}
        />
      );
    case "HAZ1":
      return (
        <Fields
          items={[
            ["Carrier", data.carrier],
            ["Policy number", <span key="p" className="font-mono text-xs">{data.policy_number}</span>],
            ["Policy current", <YesNo key="c" value={data.policy_current} />],
            ["Expires", day(data.policy_expiry_date)],
          ]}
        />
      );
    case "LMT1":
      return (
        <Fields
          items={[
            ["Status", text(data.status_description)],
            ["Modification status", text(data.mod_status)],
            ["Loan type status", text(data.loan_type_status)],
          ]}
        />
      );
    case "LMT3":
      return (
        <Fields
          cols={2}
          items={[
            ["Review start", day(data.review_start_date)],
            ["L92 date", day(data.l92_date)],
            ["Review start − 10 days", day(data.review_date_minus_10)],
            ["Review start − 90 days", day(data.review_date_minus_90)],
          ]}
        />
      );
    case "NOTS":
      return (
        <Section title={`${data.notes.length} note${data.notes.length === 1 ? "" : "s"}`} aside={<span className="font-sans text-xs" style={mutedFg}>Latest {day(data.latest_note_date)}</span>}>
          <ol className="flex flex-col gap-2">
            {data.notes.map((note, i) => (
              <li key={i} className="flex gap-3 rounded-md border px-3 py-2" style={{ borderColor: "hsl(var(--border))" }}>
                <StickyNote size={14} className="mt-0.5 shrink-0" style={mutedFg} />
                <span className="font-sans text-sm" style={fg}>{note}</span>
              </li>
            ))}
          </ol>
        </Section>
      );
    case "USR2":
      return <Fields items={[["Status", text(data.status)]]} />;
    default:
      return <pre className="font-mono text-xs whitespace-pre-wrap">{JSON.stringify(data, null, 2)}</pre>;
  }
}

export function LoanScreens({ loanId }) {
  const [screen, setScreen] = useState("overview");
  const { data: loan, isLoading, isError } = useQuery({
    queryKey: ["msp-loan", loanId],
    queryFn: () => apiGet(`/api/loans/${loanId}`),
  });

  if (isLoading) return <Status icon={LoaderCircle} spin>Loading MSP record…</Status>;
  if (isError || !loan) return <Status icon={CircleAlert}>Could not load this loan.</Status>;

  const dlq = loan.servicing_data?.DLQ1;
  const current = SCREENS.find((s) => s.key === screen);

  return (
    <div className="flex flex-col gap-4 min-w-0">
      <Card className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-mono text-xs" style={mutedFg}>
            MSP · Loan {loan.loan_id}
          </p>
          <h2 className="font-serif text-xl leading-tight" style={fg}>
            {loan.borrower_name}
          </h2>
          <p className="font-sans text-sm" style={mutedFg}>
            {loan.coborrower_name ? `with ${loan.coborrower_name} · ` : ""}
            {loan.property_address}
          </p>
        </div>
        {dlq && (
          <div className="flex gap-6 text-right">
            <div>
              <p className="font-sans text-[11px] uppercase tracking-wider" style={mutedFg}>UPB</p>
              <p className="font-serif text-lg tabular-nums" style={fg}>{money(dlq.upb_balance)}</p>
            </div>
            <div>
              <p className="font-sans text-[11px] uppercase tracking-wider" style={mutedFg}>Delinquent</p>
              <p className="font-serif text-lg tabular-nums" style={dlq.months_delinquent >= 3 ? { color: BAD } : fg}>
                {dlq.months_delinquent} mo
              </p>
            </div>
            <div>
              <p className="font-sans text-[11px] uppercase tracking-wider" style={mutedFg}>Investor</p>
              <p className="font-serif text-lg" style={fg}>{dlq.investor_type}</p>
            </div>
          </div>
        )}
      </Card>

      <div className="flex gap-1 border-b overflow-x-auto" style={{ borderColor: "hsl(var(--border))" }}>
        {SCREENS.map((s) => {
          const active = screen === s.key;
          const present = s.key === "overview" || !!loan.servicing_data?.[s.key];
          return (
            <button
              key={s.key}
              onClick={() => setScreen(s.key)}
              title={s.hint}
              className={`px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors ${s.key === "overview" ? "font-sans" : "font-mono"}`}
              style={{
                color: active ? "hsl(var(--foreground))" : "hsl(var(--muted-foreground))",
                borderBottom: active ? "2px solid hsl(var(--primary))" : "2px solid transparent",
                opacity: present ? 1 : 0.5,
              }}
            >
              {s.label}
            </button>
          );
        })}
      </div>

      <Card className="flex flex-col gap-4">
        {current.key !== "overview" && (
          <p className="font-sans text-xs uppercase tracking-widest" style={mutedFg}>
            {current.label} — {current.hint}
          </p>
        )}
        <ScreenBody screen={screen} loan={loan} />
      </Card>
    </div>
  );
}

export default function Systems() {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const { data: loans = [], isLoading, isError } = useQuery({
    queryKey: ["msp-loans"],
    queryFn: () => apiGet("/api/loans"),
  });

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return loans;
    return loans.filter(
      (l) => l.loan_id.includes(q) || l.borrower_name.toLowerCase().includes(q) || (l.coborrower_name ?? "").toLowerCase().includes(q),
    );
  }, [loans, query]);
  const current = selected ?? loans[0]?.loan_id ?? null;
  const inForeclosure = loans.filter((l) => isActive(l.foreclosure_status)).length;
  const inBankruptcy = loans.filter((l) => isActive(l.bankruptcy_status)).length;

  return (
    <div className="px-2 sm:px-6 py-6 max-w-7xl mx-auto">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-serif text-2xl font-semibold tracking-tight" style={fg}>
            Systems
          </h1>
          <p className="font-sans text-sm mt-1" style={mutedFg}>
            MSP — the servicing system of record. Each loan&apos;s borrower details and servicing screens.
          </p>
        </div>
        {loans.length > 0 && (
          <div className="flex gap-4 font-sans text-xs" style={mutedFg}>
            <span><span className="font-semibold" style={fg}>{loans.length}</span> loans</span>
            <span><span className="font-semibold" style={{ color: BAD }}>{inForeclosure}</span> in foreclosure</span>
            <span><span className="font-semibold" style={{ color: WARN }}>{inBankruptcy}</span> with bankruptcy</span>
          </div>
        )}
      </div>

      {isLoading && <Status icon={LoaderCircle} spin>Loading MSP loans…</Status>}
      {isError && <Status icon={CircleAlert}>Failed to load MSP data. Make sure the API server is running.</Status>}
      {!isLoading && !isError && loans.length === 0 && (
        <Status icon={Server}>No MSP data yet. Load it with python -m scripts.reset_db.</Status>
      )}

      {loans.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-[280px_minmax(0,1fr)] gap-6 items-start">
          <aside className="flex flex-col gap-2 md:sticky md:top-4">
            <label className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={mutedFg} />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search name or loan #"
                className="w-full pl-8 pr-3 py-2 rounded-md border font-sans text-sm outline-none"
                style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card))", ...fg }}
              />
            </label>
            <p className="font-sans text-xs px-1" style={mutedFg}>
              {visible.length} of {loans.length} loans
            </p>
            <div className="flex flex-col gap-1.5 md:max-h-[calc(100vh-220px)] overflow-y-auto pr-1">
              {visible.map((loan) => (
                <LoanRow key={loan.loan_id} loan={loan} active={loan.loan_id === current} onSelect={() => setSelected(loan.loan_id)} />
              ))}
            </div>
          </aside>
          {current && <LoanScreens key={current} loanId={current} />}
        </div>
      )}
    </div>
  );
}
