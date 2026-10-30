import { cn } from "../../lib/utils";

export default function Card({ className, children }) {
  return (
    <div
      className={cn("border p-5", className)}
      style={{
        background: "hsl(var(--card))",
        borderColor: "hsl(var(--border))",
        borderRadius: "var(--radius)",
      }}
    >
      {children}
    </div>
  );
}

/** Big serif number tile used across the Observe pages. */
export function StatCard({ value, label, sublabel, sublabelClass }) {
  return (
    <Card className="flex flex-col items-center justify-center text-center gap-1 py-6">
      <div
        className="text-3xl font-semibold leading-none"
        style={{ fontFamily: "var(--font-serif)", letterSpacing: "-0.02em", color: "hsl(var(--foreground))" }}
      >
        {value}
      </div>
      <div
        className="text-xs font-medium uppercase tracking-widest mt-1"
        style={{ fontFamily: "var(--font-sans)", color: "hsl(var(--muted-foreground))" }}
      >
        {label}
      </div>
      {sublabel && (
        <div className={cn("text-xs font-sans mt-0.5", sublabelClass)} style={{ fontFamily: "var(--font-sans)" }}>
          {sublabel}
        </div>
      )}
    </Card>
  );
}

export function PageHeader({ title, subtitle }) {
  return (
    <div>
      <h1 className="font-serif text-2xl leading-tight" style={{ color: "hsl(var(--foreground))" }}>
        {title}
      </h1>
      {subtitle && (
        <p className="mt-1 font-sans text-sm" style={{ color: "hsl(var(--muted-foreground))" }}>
          {subtitle}
        </p>
      )}
    </div>
  );
}
