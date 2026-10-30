import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CircleAlert, FileText, LoaderCircle, Search, TriangleAlert } from "lucide-react";
import Card from "../components/ui/Card";
import { DocumentBody, FLAG_LABELS } from "../components/knowledge/LoanDocuments";
import { apiGet } from "../lib/api";

const mutedFg = { color: "hsl(var(--muted-foreground))" };
const fg = { color: "hsl(var(--foreground))" };
const WARN = "hsl(32, 90%, 38%)";

const SHORT_LABELS = {
  application_form: "MAA",
  paystubs: "Paystubs",
  bank_statement: "Bank",
  credit_report: "Credit",
  letter_of_explanation: "LOE",
};

function Status({ icon: Icon, children, spin }) {
  return (
    <div className="flex items-center gap-2 py-12 justify-center" style={mutedFg}>
      <Icon size={18} className={spin ? "animate-spin" : undefined} />
      <span className="font-sans text-sm">{children}</span>
    </div>
  );
}

/** One loan in the left-hand list: borrower, loan number, which documents are on file. */
function LoanRow({ item, active, onSelect }) {
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
          {item.borrower_name}
        </span>
        {item.flags.length > 0 && (
          <span
            className="inline-flex items-center gap-1 font-sans text-[11px] font-medium shrink-0"
            style={{ color: WARN }}
            title={item.flags.map((f) => FLAG_LABELS[f] ?? f).join(", ")}
          >
            <TriangleAlert size={12} />
            {item.flags.length}
          </span>
        )}
      </div>
      <div className="flex items-center justify-between gap-2 mt-1">
        <span className="font-mono text-xs" style={mutedFg}>
          {item.loan_id}
        </span>
        <span className="flex gap-1" aria-label="Documents on file">
          {Object.entries(item.documents).map(([type, present]) => (
            <span
              key={type}
              title={`${SHORT_LABELS[type] ?? type}: ${present ? "on file" : "not submitted"}`}
              className="inline-block rounded-full"
              style={{ width: 7, height: 7, background: present ? "hsl(142, 60%, 40%)" : "hsl(var(--border))" }}
            />
          ))}
        </span>
      </div>
    </button>
  );
}

export function LoanPackage({ loanId }) {
  const [tab, setTab] = useState("application_form");
  const { data, isLoading, isError } = useQuery({
    queryKey: ["documents", loanId],
    queryFn: () => apiGet(`/api/documents/${loanId}`),
  });

  if (isLoading) return <Status icon={LoaderCircle} spin>Loading documents…</Status>;
  if (isError || !data) return <Status icon={CircleAlert}>Could not load this loan&apos;s documents.</Status>;

  const raised = Object.entries(data.flags).filter(([, v]) => v);
  const types = Object.keys(data.document_labels);

  return (
    <div className="flex flex-col gap-4 min-w-0">
      <Card className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-mono text-xs" style={mutedFg}>
            Loan {data.loan_id}
          </p>
          <h2 className="font-serif text-xl leading-tight" style={fg}>
            {data.borrower_name}
          </h2>
          {data.coborrower_name && (
            <p className="font-sans text-sm" style={mutedFg}>
              with {data.coborrower_name}
            </p>
          )}
        </div>
        <div className="text-right font-sans text-xs" style={mutedFg}>
          <p>
            Extraction <span className="font-medium capitalize" style={fg}>{data.extraction_status}</span>
          </p>
          {data.extracted_at && <p>{new Date(data.extracted_at).toLocaleString()}</p>}
        </div>
      </Card>

      {raised.length > 0 && (
        <div
          className="flex flex-wrap items-center gap-2 rounded-md border px-3 py-2"
          style={{ borderColor: "hsl(32, 90%, 70%)", background: "hsl(40, 100%, 97%)" }}
        >
          <TriangleAlert size={14} style={{ color: WARN }} />
          <span className="font-sans text-xs font-semibold" style={{ color: WARN }}>
            Extraction flags:
          </span>
          {raised.map(([flag]) => (
            <span key={flag} className="font-sans text-xs" style={{ color: WARN }}>
              {FLAG_LABELS[flag] ?? flag}
            </span>
          ))}
        </div>
      )}

      <div className="flex gap-1 border-b overflow-x-auto" style={{ borderColor: "hsl(var(--border))" }}>
        {types.map((type) => {
          const present = data[type] != null && !(Array.isArray(data[type]) && data[type].length === 0);
          const active = tab === type;
          return (
            <button
              key={type}
              onClick={() => setTab(type)}
              className="flex items-center gap-1.5 px-3 py-2 font-sans text-sm font-medium whitespace-nowrap transition-colors"
              style={{
                color: active ? "hsl(var(--foreground))" : "hsl(var(--muted-foreground))",
                borderBottom: active ? "2px solid hsl(var(--primary))" : "2px solid transparent",
                opacity: present ? 1 : 0.55,
              }}
            >
              <FileText size={13} />
              {data.document_labels[type]}
              {type === "paystubs" && present && (
                <span className="rounded-full px-1.5 text-xs" style={{ background: "hsl(var(--muted))" }}>
                  {data.paystubs.length}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <Card>
        <DocumentBody type={tab} docs={data} />
      </Card>
    </div>
  );
}

export default function KnowledgeBase() {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const { data: loans = [], isLoading, isError } = useQuery({
    queryKey: ["documents"],
    queryFn: () => apiGet("/api/documents"),
  });

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return loans;
    return loans.filter(
      (l) => l.loan_id.includes(q) || l.borrower_name.toLowerCase().includes(q) || (l.coborrower_name ?? "").toLowerCase().includes(q),
    );
  }, [loans, query]);
  const current = selected ?? loans[0]?.loan_id ?? null;

  return (
    <div className="px-2 sm:px-6 py-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="font-serif text-2xl font-semibold tracking-tight" style={fg}>
          Knowledge Base
        </h1>
        <p className="font-sans text-sm mt-1" style={mutedFg}>
          Each borrower&apos;s loss-mitigation package — the MAA, paystubs, bank statement, credit report and letter of
          explanation, as extracted.
        </p>
      </div>

      {isLoading && <Status icon={LoaderCircle} spin>Loading loans…</Status>}
      {isError && <Status icon={CircleAlert}>Failed to load documents. Make sure the API server is running.</Status>}
      {!isLoading && !isError && loans.length === 0 && (
        <Status icon={FileText}>No documents yet. Import extracted_data.json with scripts/import_data.py.</Status>
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
              {visible.map((item) => (
                <LoanRow key={item.loan_id} item={item} active={item.loan_id === current} onSelect={() => setSelected(item.loan_id)} />
              ))}
            </div>
          </aside>
          {current && <LoanPackage key={current} loanId={current} />}
        </div>
      )}
    </div>
  );
}
