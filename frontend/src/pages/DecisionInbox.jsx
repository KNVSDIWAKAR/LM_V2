import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, CircleX, FileSearch, Inbox, LoaderCircle, UserRound } from "lucide-react";
import { Link, useLocation, useParams } from "wouter";
import LoanDrawer from "../components/knowledge/LoanDrawer";
import Card from "../components/ui/Card";
import UnderlineTabs from "../components/ui/UnderlineTabs";
import { StatusPill, fg, mutedFg, useRefreshRuns } from "../components/process/ProcessParts";
import { RunTable } from "../components/runs/RunPrimitives";
import { apiGet, apiPost } from "../lib/api";
import { PROCESSES } from "../lib/navigation";
import { timeAgo } from "../lib/utils";
import { money, pct } from "../lib/caseDetails";

const RESULT_COLOR = { fail: "hsl(0, 72%, 48%)", review: "hsl(32, 90%, 38%)", missing: "hsl(0, 72%, 48%)", invalid: "hsl(0, 72%, 48%)",
  approved: "hsl(142, 60%, 32%)", pass: "hsl(142, 60%, 32%)", declined: "hsl(0, 72%, 48%)", not_selected: "hsl(var(--muted-foreground))" };
const REVIEWER = "reviewer@workbench.local";
const QC_FIELDS = [
  ["borrower_property_verified", "Borrower & property match the Note"],
  ["principal_matches_msp", "Principal balance matches MSP"],
  ["new_terms_match_plan", "New terms match the approved plan"],
];
const toChoice = (v) => (v === true ? "true" : v === false ? "false" : "");
const fromChoice = (v) => (v === "true" ? true : v === "false" ? false : null);

function DecisionRow({ d, active, onSelect }) {
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
          {d.borrower_name}
        </span>
        <span className="font-sans text-[11px] shrink-0" style={mutedFg}>
          {timeAgo(d.created_at)}
        </span>
      </div>
      <p className="font-sans text-xs mt-0.5 line-clamp-2" style={mutedFg}>
        {d.reason}
      </p>
      <div className="flex items-center justify-between gap-2 mt-1">
        <span className="font-mono text-[11px]" style={mutedFg}>
          {d.loan_id}
        </span>
        <span className="font-sans text-[11px]" style={mutedFg}>
          {d.stage_name} · {d.team}
        </span>
      </div>
    </button>
  );
}

function DecisionPanel({ d, onOpenLoan, onDecided }) {
  const refresh = useRefreshRuns();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const requiresPlan = d.stage_no === 3 && d.gate === "underwriter_review";
  const plans = requiresPlan ? (d.trial_plans ?? []).filter((p) => p.status === "proposed" || d.status !== "pending") : [];
  const [selectedPlanId, setSelectedPlanId] = useState(plans.length === 1 ? plans[0].plan_id : "");
  const recordsQc = d.stage_no === 5 && d.gate === "underwriting_mod_qc";
  const [qc, setQc] = useState(() => Object.fromEntries(QC_FIELDS.map(([k]) => [k, toChoice(d.qc?.[k])])));
  const pending = d.status === "pending";

  async function retire() {
    setBusy("retire");
    setError(null);
    try {
      const decision = await apiPost(`/api/decisions/${d.id}/retire`, {});
      const retired = { decision, stage_status: "Waiting", workflow_outcome: `Run ${d.stage_name} again to re-evaluate under the current rules` };
      setResult(retired);
      onDecided(retired);
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  }

  async function decide(decision) {
    setBusy(decision);
    setError(null);
    try {
      const r = await apiPost(`/api/decisions/${d.id}/decide`, {
        decision, decided_by: REVIEWER, note: note.trim() || null,
        ...(requiresPlan && decision === "approved" ? { selected_plan_id: selectedPlanId } : {}),
        ...(recordsQc && decision === "approved" ? { qc: Object.fromEntries(QC_FIELDS.map(([k]) => [k, fromChoice(qc[k])])) } : {}),
      });
      setResult(r);
      onDecided(r);
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-4 min-w-0">
      <Card className="flex flex-col gap-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="font-sans text-xs" style={mutedFg}>
              <Link href={PROCESSES[d.stage_no - 1]?.path ?? "/"} className="hover:underline">
                Process {d.stage_no} · {d.stage_name}
              </Link>{" "}
              · gate <span className="font-mono">{d.gate}</span>
            </p>
            <button onClick={onOpenLoan} className="font-serif text-xl leading-tight text-left hover:underline" style={fg} title="Open documents">
              {d.borrower_name} <span className="font-mono text-sm" style={mutedFg}>{d.loan_id}</span>
            </button>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onOpenLoan}
              className="inline-flex items-center gap-1.5 font-sans text-xs font-medium px-2.5 py-1 rounded border"
              style={{ borderColor: "hsl(var(--primary) / 0.4)", color: "hsl(var(--primary))", background: "hsl(var(--card))" }}
            >
              <FileSearch size={13} /> Documents & compare
            </button>
            <span className="inline-flex items-center gap-1.5 font-sans text-xs font-medium px-2 py-1 rounded" style={{ background: "hsl(0, 80%, 97%)", color: "hsl(0, 60%, 40%)" }}>
              <UserRound size={13} /> {d.team}
            </span>
          </div>
        </div>
        <p className="font-sans text-sm" style={fg}>
          {d.reason}
        </p>
      </Card>

      <section className="flex flex-col gap-2">
        <h3 className="font-sans text-xs font-semibold uppercase tracking-widest" style={mutedFg}>
          What the checks found ({d.findings.length})
        </h3>
        <RunTable columns={["Check", "Document", "Document says", "MSP says", "Result"]} empty={d.findings.length === 0 ? "No findings recorded." : null}>
          {d.findings.map((f, i) => (
            <tr key={i} style={{ background: "hsl(var(--card))", borderBottom: "1px solid hsl(var(--border))" }}>
              <td className="px-4 py-2.5 font-medium whitespace-nowrap" style={fg}>{f.check}</td>
              <td className="px-4 py-2.5 text-xs" style={mutedFg}>{f.document ?? "—"}</td>
              <td className="px-4 py-2.5 text-xs" style={fg}>{f.doc_value != null ? String(f.doc_value) : f.document ? "—" : f.detail}</td>
              <td className="px-4 py-2.5 text-xs" style={fg}>{f.msp_value != null ? String(f.msp_value) : "—"}</td>
              <td className="px-4 py-2.5 text-xs font-semibold uppercase" style={{ color: RESULT_COLOR[f.result] ?? "inherit" }}>{String(f.result).replace("_", " ")}</td>
            </tr>
          ))}
        </RunTable>
      </section>

      {pending && !result && d.stale ? (
        <Card className="flex flex-col gap-3">
          <p className="font-sans text-sm" style={fg}>
            This review was created by an older {d.stage_name} playbook (gate <span className="font-mono">{d.gate}</span> no longer exists), so it
            cannot be approved or rejected. Retire it to put the loan back to Waiting, then run {d.stage_name} again under the current rules.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <button onClick={retire} disabled={!!busy} className="inline-flex items-center gap-1.5 font-sans text-sm font-medium px-3 py-1.5 rounded-md border disabled:opacity-50"
              style={{ borderColor: "hsl(32, 90%, 38%)", color: "hsl(32, 90%, 38%)", background: "hsl(var(--card))" }}>
              {busy === "retire" ? <LoaderCircle size={14} className="animate-spin" /> : <CircleX size={14} />}
              Retire & reset to Waiting
            </button>
          </div>
          {error && <p className="font-sans text-sm text-red-600">{error}</p>}
        </Card>
      ) : pending && !result ? (
        <Card className="flex flex-col gap-3">
          {requiresPlan && (
            <fieldset className="flex flex-col gap-2">
              <legend className="font-sans text-xs font-medium mb-1" style={mutedFg}>Trial plan to approve (required)</legend>
              {plans.map((plan) => (
                <label key={plan.plan_id} className="flex items-start gap-3 rounded-md border px-3 py-2.5 cursor-pointer"
                  style={{ borderColor: selectedPlanId === plan.plan_id ? "hsl(var(--primary))" : "hsl(var(--border))", background: "hsl(var(--card))" }}>
                  <input type="radio" name={`plan-${d.id}`} value={plan.plan_id} checked={selectedPlanId === plan.plan_id}
                    onChange={() => setSelectedPlanId(plan.plan_id)} className="mt-1" />
                  <span className="flex-1 min-w-0">
                    <span className="flex flex-wrap justify-between gap-2">
                      <span className="font-sans text-sm font-medium" style={fg}>{plan.plan_name}</span>
                      <span className="font-serif text-lg tabular-nums" style={fg}>{money(plan.trial_payment)}/mo</span>
                    </span>
                    <span className="block font-sans text-xs mt-0.5" style={mutedFg}>
                      P&I {money(plan.principal_interest)} + escrow {money(plan.escrow_payment)} · {Number(plan.interest_rate_pct).toFixed(3)}% over {plan.amortization_months} mo ·
                      {" "}{plan.trial_duration_months} trial payments from {plan.first_due_date} · housing ratio {pct(plan.housing_ratio)}
                      {plan.payment_change_pct != null ? ` · ${plan.payment_change_pct > 0 ? "+" : ""}${pct(plan.payment_change_pct)} vs current` : ""}
                    </span>
                    <span className="block font-mono text-[11px] mt-1" style={mutedFg}>{plan.reason_codes.map((c) => c.code).join(" · ")}</span>
                  </span>
                </label>
              ))}
              {plans.length === 0 && <span className="font-sans text-xs" style={mutedFg}>No proposed plan is open for this evaluation, so it cannot be approved.</span>}
            </fieldset>
          )}
          {recordsQc && (
            <fieldset className="flex flex-col gap-2">
              <legend className="font-sans text-xs font-medium mb-1" style={mutedFg}>MOD QC verification (unreviewed items stay pending in the Final Mod checks)</legend>
              {QC_FIELDS.map(([key, label]) => (
                <label key={key} className="flex flex-wrap items-center justify-between gap-2 font-sans text-sm" style={fg}>
                  {label}
                  <select value={qc[key]} onChange={(e) => setQc({ ...qc, [key]: e.target.value })} className="rounded-md border px-2 py-1 text-sm"
                    style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card))", ...fg }}>
                    <option value="">Not reviewed</option>
                    <option value="true">Verified</option>
                    <option value="false">Mismatch found</option>
                  </select>
                </label>
              ))}
            </fieldset>
          )}
          <label className="flex flex-col gap-1">
            <span className="font-sans text-xs font-medium" style={mutedFg}>
              Note (required to reject)
            </span>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              className="rounded-md border px-3 py-2 font-sans text-sm outline-none"
              style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card))", ...fg }}
              placeholder="e.g. Typo in MSP name, same borrower — verified on the call"
            />
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => decide("approved")}
              disabled={!!busy || (requiresPlan && !plans.some((p) => p.plan_id === selectedPlanId))}
              className="inline-flex items-center gap-1.5 font-sans text-sm font-medium px-3 py-1.5 rounded-md disabled:opacity-50"
              style={{ background: "hsl(142, 60%, 32%)", color: "white" }}
            >
              {busy === "approved" ? <LoaderCircle size={14} className="animate-spin" /> : <CircleCheck size={14} />}
              Approve & continue
            </button>
            <button
              onClick={() => decide("rejected")}
              disabled={!!busy || !note.trim()}
              title={note.trim() ? "" : "Add a note to reject"}
              className="inline-flex items-center gap-1.5 font-sans text-sm font-medium px-3 py-1.5 rounded-md border disabled:opacity-50"
              style={{ borderColor: "hsl(0, 72%, 48%)", color: "hsl(0, 72%, 48%)", background: "hsl(var(--card))" }}
            >
              {busy === "rejected" ? <LoaderCircle size={14} className="animate-spin" /> : <CircleX size={14} />}
              Reject
            </button>
            <span className="font-sans text-xs" style={mutedFg}>
              Approve resumes the playbook from this gate; reject ends the case.
            </span>
          </div>
          {error && <p className="font-sans text-sm text-red-600">{error}</p>}
        </Card>
      ) : (
        <Card className="flex flex-col gap-1.5">
          <p className="font-sans text-sm" style={fg}>
            <span className="font-semibold capitalize">{(result?.decision ?? d).status}</span> by {(result?.decision ?? d).decided_by}{" "}
            {timeAgo((result?.decision ?? d).decided_at)}
          </p>
          {(result?.decision ?? d).trial_plans?.filter((p) => p.status === "approved").map((p) => (
            <p key={p.plan_id} className="font-sans text-sm" style={{ color: RESULT_COLOR.approved }}>
              Approved plan: <span className="font-semibold">{p.plan_name}</span> · {money(p.trial_payment)}/mo × {p.trial_duration_months} from {p.first_due_date}
            </p>
          ))}
          {(result?.decision ?? d).note && (
            <p className="font-sans text-sm" style={mutedFg}>
              “{(result?.decision ?? d).note}”
            </p>
          )}
          {result && (
            <div className="flex flex-wrap items-center gap-2 font-sans text-sm" style={fg}>
              {d.stage_name} is now <StatusPill status={result.stage_status} />
              {result.workflow_outcome && <span style={mutedFg}>· {result.workflow_outcome}</span>}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

const TABS = [
  { key: "pending", label: "Waiting" },
  { key: "approved", label: "Approved" },
  { key: "rejected", label: "Rejected" },
];

export default function DecisionInbox() {
  const params = useParams();
  const [, navigate] = useLocation();
  const [tab, setTab] = useState("pending");
  const [openLoan, setOpenLoan] = useState(null);
  const [flash, setFlash] = useState(null);
  const qc = useQueryClient();
  const { data: all = [], isLoading } = useQuery({ queryKey: ["decisions"], queryFn: () => apiGet("/api/decisions"), refetchInterval: 5000 });

  const visible = all.filter((d) => d.status === tab);
  const selectedId = params.id ?? visible[0]?.id;
  const selected = all.find((d) => d.id === selectedId);
  const tabs = TABS.map((t) => ({ ...t, count: all.filter((d) => d.status === t.key).length }));

  // Show the decision's effect at once: move the item out of Waiting and open the next case.
  function onDecided(result) {
    const decided = result.decision;
    const next = visible.find((d) => d.id !== decided.id);
    qc.setQueryData(["decisions"], (old = []) => old.map((d) => (d.id === decided.id ? decided : d)));
    setFlash({
      ...result,
      borrower: decided.borrower_name,
      loanId: decided.loan_id,
      stage: decided.stage_name,
    });
    if (tab === "pending") navigate(next ? `/decision-inbox/${next.id}` : "/decision-inbox");
  }

  return (
    <div className="px-2 sm:px-6 py-6 max-w-7xl mx-auto flex flex-col gap-5">
      <div>
        <h1 className="font-serif text-2xl font-semibold tracking-tight" style={fg}>
          Decision Inbox
        </h1>
        <p className="font-sans text-sm mt-1" style={mutedFg}>
          Cases a playbook paused for a person. Approving continues the case from where it stopped; it then keeps flowing until it
          finishes or hits a blocker.
        </p>
      </div>

      {flash && (
        <div
          className="flex flex-wrap items-center gap-2 rounded-md border px-4 py-2.5 font-sans text-sm"
          style={{
            borderColor: flash.decision.status === "approved" ? "hsl(142, 50%, 70%)" : "hsl(0, 60%, 80%)",
            background: flash.decision.status === "approved" ? "hsl(142, 60%, 96%)" : "hsl(0, 80%, 97%)",
            ...fg,
          }}
        >
          {flash.decision.status === "approved" ? <CircleCheck size={15} style={{ color: "hsl(142, 60%, 32%)" }} /> : <CircleX size={15} style={{ color: "hsl(0, 72%, 48%)" }} />}
          <span className="font-semibold capitalize">{flash.decision.status}</span>
          <span>
            {flash.borrower} <span className="font-mono text-xs" style={mutedFg}>{flash.loanId}</span>
          </span>
          <span style={mutedFg}>·</span>
          <span>{flash.stage} →</span>
          <StatusPill status={flash.stage_status} />
          {flash.workflow_outcome && <span style={mutedFg}>· {flash.workflow_outcome}</span>}
          <button onClick={() => setFlash(null)} className="ml-auto text-xs hover:underline" style={mutedFg}>
            Dismiss
          </button>
        </div>
      )}

      <UnderlineTabs
        tabs={tabs}
        value={tab}
        onChange={(t) => {
          setTab(t);
          navigate("/decision-inbox");
        }}
      />

      {isLoading ? (
        <p className="font-sans text-sm" style={mutedFg}>Loading…</p>
      ) : visible.length === 0 && !selected ? (
        <div className="flex flex-col items-center gap-2 py-16" style={mutedFg}>
          <Inbox size={28} />
          <p className="font-sans text-sm">{tab === "pending" ? "Nothing is waiting for a decision." : `No ${tab} decisions yet.`}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-[320px_minmax(0,1fr)] gap-6 items-start">
          <aside className="flex flex-col gap-1.5 md:max-h-[calc(100vh-240px)] overflow-y-auto pr-1">
            {visible.map((d) => (
              <DecisionRow key={d.id} d={d} active={d.id === selectedId} onSelect={() => navigate(`/decision-inbox/${d.id}`)} />
            ))}
          </aside>
          {selected && <DecisionPanel key={selected.id} d={selected} onOpenLoan={() => setOpenLoan(selected)} onDecided={onDecided} />}
        </div>
      )}
      <LoanDrawer loanId={openLoan?.loan_id} borrowerName={openLoan?.borrower_name} onClose={() => setOpenLoan(null)} />
    </div>
  );
}
