import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { FileSearch, Inbox, LoaderCircle, X } from "lucide-react";
import { useLocation } from "wouter";
import Card from "../ui/Card";
import { PrimaryButton, StatusPill, fg, mutedFg } from "./ProcessParts";
import { apiGet, apiPost } from "../../lib/api";
import { answerPresentation, answerSummary } from "../../lib/retentionAnswers";

const colors = { pass: "hsl(142, 60%, 32%)", fail: "hsl(0, 72%, 48%)", pending: "hsl(32, 90%, 38%)" };
const showAnswer = (value) => value === true ? "Yes" : value === false ? "No" : value ?? "Not determined";

export default function RetentionCaseDrawer({ loan, onClose, onDocuments, onRefresh }) {
  const panel = useRef(null);
  const [, navigate] = useLocation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["process", 2, "retention-case", loan.loan_id],
    queryFn: () => apiGet(`/api/retention/cases/${loan.loan_id}`),
    refetchInterval: 5000,
  });

  useEffect(() => {
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel.current?.focus();
    const keydown = (event) => {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab") return;
      const elements = panel.current?.querySelectorAll('button:not([disabled]), a[href], [tabindex="0"]');
      if (!elements?.length) return;
      const first = elements[0], last = elements[elements.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    };
    window.addEventListener("keydown", keydown);
    return () => {
      document.body.style.overflow = overflow;
      window.removeEventListener("keydown", keydown);
      previous?.focus();
    };
  }, [onClose]);

  async function route() {
    if (data?.open_decision_id) {
      navigate(`/decision-inbox/${data.open_decision_id}`);
      return;
    }
    setBusy(true); setError(null);
    try {
      const result = await apiPost(`/api/retention/cases/${loan.loan_id}/review`, {});
      onRefresh();
      navigate(`/decision-inbox/${result.decision_id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const report = data?.report;
  const status = data?.status ?? loan.status;
  const counts = answerSummary(report?.answers, report?.stip_list);
  return (
    <>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 z-40" style={{ background: "rgba(0,0,0,0.3)" }} onClick={onClose} />
      <motion.aside ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="retention-case-title"
        initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }} transition={{ type: "spring", stiffness: 320, damping: 34 }}
        className="fixed right-0 top-0 h-full z-50 flex flex-col outline-none shadow-2xl"
        style={{ width: "min(760px, 100vw)", background: "hsl(var(--background))", borderLeft: "1px solid hsl(var(--border))" }}>
        <header className="flex items-start justify-between gap-3 px-6 py-5 border-b" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card))" }}>
          <div>
            <p className="font-mono text-xs mb-1" style={mutedFg}>Loan {loan.loan_id} · Retention Eligibility</p>
            <h2 id="retention-case-title" className="font-serif text-2xl mb-2" style={fg}>{loan.borrower_name}</h2>
            <StatusPill status={status ?? "Waiting"} />
          </div>
          <button onClick={onClose} className="p-2 rounded hover:bg-black/5" aria-label="Close retention case"><X size={20} /></button>
        </header>
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {isLoading && <p className="flex items-center gap-2" style={mutedFg}><LoaderCircle className="animate-spin" size={16} /> Loading case report…</p>}
          {isError && <p role="alert">Could not load the report. <button onClick={() => refetch()} className="underline">Try again</button></p>}
          {data && !report && <Card><p style={mutedFg}>{data.last_run_status === "failed" ? "The last run failed. See Agent Runs for its error." : "No saved question report exists for this case yet. Imported statuses do not contain an evaluation trace."}</p></Card>}
          {report && <>
            <Card className="space-y-3">
              <div className="flex flex-wrap justify-between gap-3 font-sans text-sm">
                <span style={mutedFg}>Evaluated {report.evaluation_date}</span>
              </div>
              <p className="text-xs" style={mutedFg}>Review start: {report.review_start_date ?? "Unavailable"} · {report.answers.length} questions · {counts.pass} passed · {counts.fail} failed · {counts.neutral} informational</p>
              {report.question_results_version !== 2 && <p className="text-xs" style={mutedFg}>Saved before the latest question rules. Re-run eligible cases to apply the current document checks; the saved case verdict has not been changed.</p>}
              {report.exit_reason && <p className="text-sm" style={fg}>{report.exit_reason}</p>}
              {report.dm712_required && <p className="text-sm font-semibold" style={{ color: colors.fail }}>DM712 required · {report.stip_count} outstanding stip(s)</p>}
            </Card>
            {status === "Facially Incomplete" && <section aria-labelledby="stips-title">
              <h3 id="stips-title" className="font-sans text-sm font-semibold mb-2" style={fg}>Stips ({report.stip_count})</h3>
              <div className="space-y-2">{report.stip_list.map((stip) => <Card key={stip.stip_id} className="!p-3 border-l-4">
                <p className="font-mono text-[11px] mb-1" style={mutedFg}>{stip.stip_id} · {stip.question_id}{stip.wage_number ? ` · Wage #${stip.wage_number}` : ""} · {stip.category}</p>
                <h4 className="font-sans text-sm font-semibold" style={fg}>{stip.document_required}</h4>
                <p className="text-sm mt-1" style={mutedFg}>{stip.reason}</p>
              </Card>)}</div>
            </section>}
            <section aria-labelledby="questions-title">
              <h3 id="questions-title" className="font-sans text-sm font-semibold mb-3" style={fg}>Decision path · questions reached ({report.answers.length})</h3>
              <div className="space-y-3">{report.answers.map((answer, index) => {
                const presentation = answerPresentation(answer, report.stip_list);
                return <Card key={`${answer.question_id}-${index}`} className="!p-4">
                <div className="flex justify-between items-start gap-3">
                  <p className="font-mono text-xs" style={mutedFg}>{answer.question_id}{answer.wage_number ? ` · Wage #${answer.wage_number} · ${answer.wage_source ?? "Unknown employer"}` : ""}</p>
                  {presentation.badge && <span className="text-[11px] font-semibold uppercase rounded-full border px-2 py-0.5" style={{ color: colors[presentation.result], borderColor: colors[presentation.result] }}>{presentation.badge}</span>}
                </div>
                <h4 className="font-sans text-sm font-semibold mt-2" style={fg}>{answer.question}</h4>
                <p className="text-sm mt-2" style={presentation.dateOnly ? { color: "#111111" } : fg}>{answer.not_applicable ? "Not applicable" : showAnswer(answer.answer)}</p>
                <p className="text-xs mt-1.5 leading-relaxed" style={mutedFg}>{answer.explanation}</p>
                {answer.sub_checks?.map((check) => <p key={check.borrower} className="text-xs mt-2" style={mutedFg}>{check.borrower} signed: {showAnswer(check.answer)}</p>)}
              </Card>;
              })}</div>
            </section>
          </>}
        </div>
        <footer className="border-t px-6 py-4 space-y-2" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card))" }}>
          {error && <p className="text-sm" role="alert" style={{ color: colors.fail }}>{error}</p>}
          <div className="flex flex-wrap gap-2">
            <PrimaryButton icon={FileSearch} onClick={() => onDocuments(data ?? loan)}>View documents</PrimaryButton>
            {status && status !== "Facially Complete" && <PrimaryButton icon={Inbox} onClick={route} busy={busy}
              disabled={!data?.open_decision_id && !data?.can_route_to_inbox}>
              {data?.open_decision_id ? "Open Decision Inbox item" : "Route to Decision Inbox"}
            </PrimaryButton>}
          </div>
          {status === "Facially Incomplete" && <p className="text-[11px]" style={mutedFg}>Routing requests review; approving that review does not waive outstanding document stips.</p>}
        </footer>
      </motion.aside>
    </>
  );
}