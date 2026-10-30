// Side panel for one loan: compare its documents with MSP, read the documents, or read the MSP screens.
// Opened from the Decision Inbox and the process pages.
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { CircleCheck, CircleX, LoaderCircle, Minus, X } from "lucide-react";
import UnderlineTabs from "../ui/UnderlineTabs";
import { apiGet } from "../../lib/api";
import { LoanPackage } from "../../pages/KnowledgeBase";
import { LoanScreens } from "../../pages/Systems";

const mutedFg = { color: "hsl(var(--muted-foreground))" };
const fg = { color: "hsl(var(--foreground))" };
const GOOD = "hsl(142, 60%, 32%)";
const BAD = "hsl(0, 72%, 48%)";

// Same comparison the Intake playbook uses: case- and punctuation-insensitive.
const norm = (v) =>
  String(v ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9 ]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

function employerFromNotes(notes = []) {
  for (const n of notes) {
    const m = n.match(/Source Of Borrower Wages Is (.+)$/);
    if (m) return m[1].trim();
  }
  return null;
}

/** Each field MSP holds, the value every document gives for it, and whether they agree. */
function buildComparison(docs, msp) {
  const maa = docs.application_form ?? {};
  const credit = docs.credit_report ?? {};
  const bank = docs.bank_statement ?? {};
  const stubs = docs.paystubs ?? [];
  const sd = msp.servicing_data ?? {};
  const rows = [
    {
      field: "Borrower name",
      msp: msp.borrower_name,
      sources: [
        ["Application form", maa.borrower_name],
        ["Credit report", credit.borrower_name],
        ...stubs.map((s, i) => [`Paystub ${i + 1}`, s.employee_name]),
        ["Bank statement", bank.account_holder_name],
      ],
    },
    {
      field: "Co-borrower name",
      msp: msp.coborrower_name,
      sources: [
        ["Application form", maa.coborrower_name],
        ["Credit report", credit.coborrower_name],
        ["Bank statement", bank.coborrower_on_account],
      ],
    },
    { field: "Borrower SSN (last 4)", msp: msp.borrower_ssn_last4, sources: [["Application form", maa.borrower_ssn_last4], ["Credit report", credit.borrower_ssn_last4]] },
    {
      field: "Co-borrower SSN (last 4)",
      msp: msp.coborrower_ssn_last4,
      sources: [["Application form", maa.coborrower_ssn_last4], ["Credit report", credit.coborrower_ssn_last4]],
    },
    { field: "Property address", msp: msp.property_address, sources: [["Application form", maa.property_address]] },
    { field: "Mailing address", msp: msp.mailing_address, sources: [["Application form", maa.mailing_address]] },
    {
      field: "Employer",
      msp: employerFromNotes(sd.NOTS?.notes),
      mspLabel: "MSP NOTS",
      sources: stubs.map((s, i) => [`Paystub ${i + 1}`, s.employer_name]),
    },
    {
      field: "HOA",
      msp: msp.hoa ? (msp.hoa.hoa_exists ? "Yes" : "No") : null,
      sources: [["Application form", maa.hoa_indicated == null ? null : maa.hoa_indicated ? "Yes" : "No"]],
    },
  ];
  return rows.map((r) => ({
    ...r,
    sources: r.sources
      .filter(([, v]) => v != null && v !== "")
      .map(([doc, v]) => ({ doc, value: v, match: r.msp == null ? null : norm(v) === norm(r.msp) })),
  }));
}

function Compare({ loanId }) {
  const docs = useQuery({ queryKey: ["documents", loanId], queryFn: () => apiGet(`/api/documents/${loanId}`) });
  const msp = useQuery({ queryKey: ["msp-loan", loanId], queryFn: () => apiGet(`/api/loans/${loanId}`) });
  if (docs.isLoading || msp.isLoading)
    return (
      <p className="flex items-center gap-2 font-sans text-sm py-8 justify-center" style={mutedFg}>
        <LoaderCircle size={16} className="animate-spin" /> Loading…
      </p>
    );
  if (!docs.data || !msp.data) return <p className="font-sans text-sm py-8 text-center" style={mutedFg}>Documents or MSP record not found for this loan.</p>;

  const rows = buildComparison(docs.data, msp.data);
  const mismatches = rows.reduce((n, r) => n + r.sources.filter((s) => s.match === false).length, 0);

  return (
    <div className="flex flex-col gap-3">
      <p className="font-sans text-sm" style={mismatches ? { color: BAD } : { color: GOOD }}>
        {mismatches ? `${mismatches} value${mismatches === 1 ? "" : "s"} differ from MSP` : "Every document agrees with MSP"}
      </p>
      <div className="overflow-x-auto rounded border" style={{ borderColor: "hsl(var(--border))" }}>
        <table className="w-full text-sm font-sans" style={{ borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "hsl(var(--muted))" }}>
              {["Field", "MSP", "Document", "Document says", ""].map((c, i) => (
                <th key={i} className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider" style={mutedFg}>
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) =>
              (r.sources.length ? r.sources : [{ doc: "—", value: null, match: null }]).map((s, i) => (
                <tr key={`${r.field}-${i}`} style={{ borderTop: i === 0 ? "1px solid hsl(var(--border))" : "none", background: s.match === false ? "hsl(0, 85%, 97%)" : "transparent" }}>
                  {i === 0 && (
                    <>
                      <td rowSpan={Math.max(r.sources.length, 1)} className="px-3 py-2 align-top font-medium whitespace-nowrap" style={fg}>
                        {r.field}
                      </td>
                      <td rowSpan={Math.max(r.sources.length, 1)} className="px-3 py-2 align-top" style={fg}>
                        {r.msp ?? <span style={mutedFg}>—</span>}
                        {r.mspLabel && <span className="block text-[11px]" style={mutedFg}>{r.mspLabel}</span>}
                      </td>
                    </>
                  )}
                  <td className="px-3 py-2 text-xs whitespace-nowrap" style={mutedFg}>{s.doc}</td>
                  <td className="px-3 py-2" style={s.match === false ? { color: BAD, fontWeight: 600 } : fg}>
                    {s.value ?? <span style={mutedFg}>—</span>}
                  </td>
                  <td className="px-3 py-2">
                    {s.match === true && <CircleCheck size={15} style={{ color: GOOD }} />}
                    {s.match === false && <CircleX size={15} style={{ color: BAD }} />}
                    {s.match == null && s.value != null && <Minus size={15} style={mutedFg} />}
                  </td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
      <p className="font-sans text-xs" style={mutedFg}>
        Names and addresses are compared ignoring case and punctuation, the same way the Intake playbook checks them.
      </p>
    </div>
  );
}

const TABS = [
  { key: "compare", label: "Compare with MSP" },
  { key: "documents", label: "Documents" },
  { key: "msp", label: "MSP" },
];

/** Render with a loanId to open; onClose clears it. */
export default function LoanDrawer({ loanId, borrowerName, onClose, initialTab = "compare" }) {
  const [tab, setTab] = useState(initialTab);
  useEffect(() => {
    if (loanId) setTab(initialTab);
  }, [loanId, initialTab]);
  useEffect(() => {
    if (!loanId) return undefined;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [loanId, onClose]);

  return (
    <AnimatePresence>
      {loanId && (
        <>
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40"
            style={{ background: "rgba(0,0,0,0.25)" }}
            onClick={onClose}
          />
          <motion.div
            key="panel"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 34 }}
            className="fixed right-0 top-0 h-full z-50 flex flex-col"
            style={{ width: "min(1040px, 100vw)", background: "hsl(var(--background))", borderLeft: "1px solid hsl(var(--border))" }}
          >
            <div className="flex items-start justify-between gap-3 px-5 pt-4 pb-2" style={{ background: "hsl(var(--card))" }}>
              <div>
                <p className="font-mono text-xs" style={mutedFg}>Loan {loanId}</p>
                <h2 className="font-serif text-lg leading-tight" style={fg}>{borrowerName ?? "Loan documents"}</h2>
              </div>
              <button onClick={onClose} className="p-1.5 rounded" style={mutedFg} aria-label="Close">
                <X size={18} />
              </button>
            </div>
            <div className="px-5" style={{ background: "hsl(var(--card))" }}>
              <UnderlineTabs tabs={TABS} value={tab} onChange={setTab} />
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-4">
              {tab === "compare" && <Compare loanId={loanId} />}
              {tab === "documents" && <LoanPackage key={loanId} loanId={loanId} />}
              {tab === "msp" && <LoanScreens key={loanId} loanId={loanId} />}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
