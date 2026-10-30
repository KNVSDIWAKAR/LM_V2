export default function NotFound({ title }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-3">
      <h1 className="font-serif text-2xl" style={{ color: "hsl(var(--foreground))" }}>
        {title}
      </h1>
      <p className="font-sans text-sm" style={{ color: "hsl(var(--muted-foreground))" }}>
        Coming soon
      </p>
    </div>
  );
}
