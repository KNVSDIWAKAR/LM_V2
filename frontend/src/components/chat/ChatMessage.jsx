import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const fg = { color: "hsl(var(--foreground))" };
const cellBorder = { borderColor: "hsl(var(--border))", ...fg };

/** Markdown element overrides for agent answers. */
export const chatMarkdownComponents = {
  table: ({ children }) => (
    <div className="overflow-x-auto my-2">
      <table className="text-xs border-collapse w-full font-sans" style={{ borderColor: "hsl(var(--border))" }}>
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => <thead style={{ background: "hsl(var(--muted))" }}>{children}</thead>,
  th: ({ children }) => (
    <th className="px-3 py-1.5 text-left font-medium text-xs font-sans border" style={cellBorder}>
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="px-3 py-1 text-xs font-sans border" style={cellBorder}>
      {children}
    </td>
  ),
  code: ({ className, children }) =>
    className?.startsWith("language-") ? (
      <pre
        className="rounded p-3 overflow-x-auto text-xs my-2"
        style={{
          background: "hsl(25, 30%, 15%)",
          color: "hsl(36, 20%, 80%)",
          fontFamily: "var(--font-mono)",
          borderRadius: "var(--radius)",
        }}
      >
        <code className={className}>{children}</code>
      </pre>
    ) : (
      <code
        className="rounded px-1 py-0.5 text-xs font-mono"
        style={{ background: "hsl(var(--muted))", ...fg, fontFamily: "var(--font-mono)" }}
      >
        {children}
      </code>
    ),
  h1: ({ children }) => (
    <h1 className="text-base font-serif font-semibold mt-3 mb-1" style={fg}>
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-sm font-serif font-semibold mt-2.5 mb-1" style={fg}>
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-sm font-sans font-semibold mt-2 mb-0.5" style={fg}>
      {children}
    </h3>
  ),
  p: ({ children }) => <p className="mb-1.5 leading-relaxed font-sans text-sm">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 ml-4 list-disc font-sans text-sm space-y-0.5">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 ml-4 list-decimal font-sans text-sm space-y-0.5">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => (
    <strong className="font-semibold" style={fg}>
      {children}
    </strong>
  ),
  blockquote: ({ children }) => (
    <blockquote
      className="border-l-2 pl-3 my-2 italic text-sm"
      style={{ borderColor: "hsl(var(--primary))", color: "hsl(var(--muted-foreground))" }}
    >
      {children}
    </blockquote>
  ),
};

export default function ChatMessage({ message }) {
  if (!message.content) return null;

  if (message.role === "user") {
    return (
      <div className="flex justify-end mb-3">
        <div
          className="max-w-[80%] rounded-2xl px-4 py-2.5 font-sans text-sm"
          style={{
            background: "hsl(var(--primary) / 0.08)",
            color: "hsl(var(--foreground))",
            border: "1px solid hsl(var(--border))",
          }}
        >
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start mb-3">
      <div className="max-w-[90%] font-sans text-sm" style={fg}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={chatMarkdownComponents}>
          {message.content}
        </ReactMarkdown>
      </div>
    </div>
  );
}
