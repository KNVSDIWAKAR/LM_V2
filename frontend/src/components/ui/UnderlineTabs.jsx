/** Border-bottom tab strip with optional count pills (Decision Inbox, Agent Runs, Compliance…). */
export default function UnderlineTabs({ tabs, value, onChange }) {
  return (
    <div className="flex gap-1 border-b" style={{ borderColor: "hsl(var(--border))" }}>
      {tabs.map((tab) => {
        const active = value === tab.key;
        return (
          <button
            key={tab.key}
            onClick={() => onChange(tab.key)}
            className="px-4 py-2 font-sans text-sm font-medium transition-colors"
            style={{
              color: active ? "hsl(var(--foreground))" : "hsl(var(--muted-foreground))",
              borderBottom: active ? "2px solid hsl(var(--primary))" : "2px solid transparent",
              background: "transparent",
              cursor: "pointer",
            }}
          >
            {tab.label}
            {tab.count > 0 && (
              <span
                className="ml-1.5 rounded-full px-1.5 py-0.5 text-xs"
                style={{
                  background: active ? "hsl(var(--primary))" : "hsl(var(--muted))",
                  color: active ? "hsl(var(--primary-foreground))" : "hsl(var(--muted-foreground))",
                }}
              >
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
