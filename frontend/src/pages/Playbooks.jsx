import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileCode2, FileSearch, ListChecks } from "lucide-react";
import LoanDrawer from "../components/knowledge/LoanDrawer";
import Card from "../components/ui/Card";
import UnderlineTabs from "../components/ui/UnderlineTabs";
import { PlaybookFlow, StatusPill, fg, mutedFg } from "../components/process/ProcessParts";
import { RunStatus } from "../components/runs/RunPrimitives";
import { apiGet } from "../lib/api";

/** Rules YAML as readable sections: scalars as label/value, lists as chips, maps as rows. */
function RuleValue({ value }) {
  if (Array.isArray(value))
    return (
      <span className="flex flex-wrap gap-1">
        {value.map((v) => (
          <span key={String(v)} className="font-mono text-[11px] px-1.5 py-0.5 rounded" style={{ background: "hsl(var(--muted))", ...fg }}>
            {String(v)}
          </span>
        ))}
      </span>
    );
  if (value && typeof value === "object")
    return (
      <dl className="grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-4 gap-y-1">
        {Object.entries(value).map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="font-mono text-xs" style={mutedFg}>{k}</dt>
            <dd className="font-sans text-xs" style={fg}><RuleValue value={v} /></dd>
          </div>
        ))}
      </dl>
    );
  return <span className="font-mono text-xs" style={fg}>{String(value)}</span>;
}

function Rules({ rules }) {
  const { version, ...sections } = rules;
  return (
    <div className="flex flex-col gap-4">
      <p className="font-sans text-xs" style={mutedFg}>
        Version <span className="font-mono" style={fg}>{version}</span> — every agent run records the version it used.
      </p>
      {Object.entries(sections).map(([name, value]) => (
        <section key={name} className="flex flex-col gap-2">
          <h3 className="font-sans text-xs font-semibold uppercase tracking-widest" style={mutedFg}>{name.replace(/_/g, " ")}</h3>
          <div className="rounded-md border p-3" style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card))" }}>
            <RuleValue value={value} />
          </div>
        </section>
      ))}
    </div>
  );
}

function YamlFiles({ files }) {
  const names = Object.keys(files);
  const [current, setCurrent] = useState(names[0]);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex gap-1.5">
        {names.map((n) => (
          <button
            key={n}
            onClick={() => setCurrent(n)}
            className="font-mono text-xs px-2 py-1 rounded border"
            style={n === current ? { borderColor: "hsl(var(--primary))", ...fg } : { borderColor: "hsl(var(--border))", ...mutedFg }}
          >
            backend/{n}
          </button>
        ))}
      </div>
      <pre className="rounded-md p-4 text-xs overflow-x-auto font-mono leading-relaxed" style={{ background: "hsl(220, 25%, 12%)", color: "hsl(210, 30%, 88%)" }}>
        {files[current]}
      </pre>
    </div>
  );
}

/** Pick a loan; its latest agent run for this stage lights up the path it took. */
function LoanPath({ stageNo, playbook, onOpenDocs }) {
  const [loanId, setLoanId] = useState("");
  const { data: process } = useQuery({ queryKey: ["process", stageNo], queryFn: () => apiGet(`/api/processes/${stageNo}`) });
  const { data: runs = [] } = useQuery({
    queryKey: ["agent-runs", "loan", loanId, stageNo],
    queryFn: () => apiGet(`/api/agent-runs?loan_id=${loanId}&stage_no=${stageNo}`),
    enabled: !!loanId,
  });
  const loans = process?.loans ?? [];
  const loan = loans.find((l) => l.loan_id === loanId);
  const run = runs[0];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={loanId}
          onChange={(e) => setLoanId(e.target.value)}
          className="rounded-md border px-2 py-1.5 font-sans text-sm"
          style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card))", ...fg }}
        >
          <option value="">Trace a loan through this playbook…</option>
          {loans.map((l) => (
            <option key={l.loan_id} value={l.loan_id}>
              {l.borrower_name} · {l.loan_id} · {l.status ?? (l.position === "waiting" ? "Waiting" : "Not reached")}
            </option>
          ))}
        </select>
        {loan && (
          <>
            <StatusPill status={loan.status} />
            {run && <RunStatus status={run.status} />}
            <button
              onClick={() => onOpenDocs(loan)}
              className="inline-flex items-center gap-1.5 font-sans text-xs font-medium px-2.5 py-1 rounded border ml-auto"
              style={{ borderColor: "hsl(var(--primary) / 0.4)", color: "hsl(var(--primary))", background: "hsl(var(--card))" }}
            >
              <FileSearch size={13} /> Documents & compare
            </button>
          </>
        )}
      </div>
      {loan && !run && (
        <p className="font-sans text-xs" style={mutedFg}>
          This loan has not been run through {playbook.name} yet.
        </p>
      )}
      <PlaybookFlow playbook={playbook} trace={run?.trace} />
    </div>
  );
}

const TABS = [
  { key: "flow", label: "Steps" },
  { key: "rules", label: "Rules" },
  { key: "yaml", label: "YAML" },
];

export default function Playbooks() {
  const [stageNo, setStageNo] = useState(1);
  const [tab, setTab] = useState("flow");
  const [openLoan, setOpenLoan] = useState(null);
  const { data: processes = [] } = useQuery({ queryKey: ["processes"], queryFn: () => apiGet("/api/processes") });
  const current = processes.find((p) => p.stage_no === stageNo);
  const { data: playbook } = useQuery({
    queryKey: ["playbook", stageNo],
    queryFn: () => apiGet(`/api/processes/${stageNo}/playbook`),
    enabled: !!current?.playbook,
  });

  return (
    <div className="px-2 sm:px-6 py-6 max-w-7xl mx-auto flex flex-col gap-5">
      <div>
        <h1 className="font-serif text-2xl font-semibold tracking-tight" style={fg}>
          Playbooks
        </h1>
        <p className="font-sans text-sm mt-1 max-w-3xl" style={mutedFg}>
          Each process runs from two files in <code className="font-mono text-xs">backend/harness/&lt;process&gt;/</code>: the playbook (the
          steps and where each outcome leads) and the rules (thresholds, required documents, fields that must match MSP). Change the files,
          restart the backend, and the agents follow the new version.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[240px_minmax(0,1fr)] gap-6 items-start">
        <aside className="flex flex-col gap-1.5">
          {processes.map((p) => (
            <button
              key={p.stage_no}
              onClick={() => setStageNo(p.stage_no)}
              className="text-left px-3 py-2.5 rounded-md border"
              style={{
                background: p.stage_no === stageNo ? "hsl(var(--muted))" : "hsl(var(--card))",
                borderColor: p.stage_no === stageNo ? "hsl(var(--primary) / 0.35)" : "hsl(var(--border))",
              }}
            >
              <p className="font-sans text-[11px] uppercase tracking-wider" style={mutedFg}>Process {p.stage_no}</p>
              <p className="font-sans text-sm font-medium" style={fg}>{p.name}</p>
              <p className="font-sans text-[11px] mt-0.5" style={p.playbook ? { color: "hsl(142, 60%, 30%)" } : mutedFg}>
                {p.playbook ? `Live · rules v${p.rules_version}` : "Not built yet"}
              </p>
            </button>
          ))}
        </aside>

        <Card className="flex flex-col gap-4 min-w-0">
          {!current ? null : !current.playbook ? (
            <div className="flex flex-col items-center gap-2 py-12 text-center" style={mutedFg}>
              <FileCode2 size={28} />
              <p className="font-sans text-sm" style={fg}>{current.name} has no playbook yet.</p>
              <p className="font-sans text-xs max-w-md">
                Add <code className="font-mono">harness/&lt;process&gt;/playbook.yaml</code> and <code className="font-mono">rules.yaml</code> with
                stage_no {current.stage_no}, plus its node functions in <code className="font-mono">app/engine/nodes/</code>. Cases waiting at this
                stage continue automatically once it exists.
              </p>
            </div>
          ) : !playbook ? (
            <p className="font-sans text-sm" style={mutedFg}>Loading playbook…</p>
          ) : (
            <>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="font-serif text-xl" style={fg}>{playbook.name}</h2>
                  <p className="font-sans text-xs" style={mutedFg}>
                    <ListChecks size={12} className="inline mr-1" />
                    {playbook.agent} · starts at <span className="font-mono">{playbook.start}</span> · {playbook.nodes.length} nodes
                  </p>
                </div>
              </div>
              <UnderlineTabs tabs={TABS} value={tab} onChange={setTab} />
              {tab === "flow" && <LoanPath stageNo={stageNo} playbook={playbook} onOpenDocs={setOpenLoan} />}
              {tab === "rules" && <Rules rules={playbook.rules} />}
              {tab === "yaml" && <YamlFiles files={playbook.files} />}
            </>
          )}
        </Card>
      </div>

      <LoanDrawer loanId={openLoan?.loan_id} borrowerName={openLoan?.borrower_name} onClose={() => setOpenLoan(null)} />
    </div>
  );
}
