import { useState } from "react";
import { Paperclip, Send } from "lucide-react";
import { cn } from "../../lib/utils";

/** Pill-shaped prompt box used on the Command Center hero. */
export default function PromptInput({ placeholder, onSend, className }) {
  const [value, setValue] = useState("");
  const hasValue = value.trim().length > 0;

  const submit = () => {
    if (!hasValue) return;
    onSend(value.trim());
    setValue("");
  };

  return (
    <div
      className={cn(
        "flex items-center gap-3 px-4 py-3 rounded-2xl glass-input",
        "focus-within:outline focus-within:outline-2",
        className,
      )}
      style={{ border: "1px solid hsl(var(--border))", outlineColor: "hsl(var(--ring))" }}
    >
      <button
        type="button"
        className="shrink-0 transition-colors"
        style={{ color: "hsl(var(--muted-foreground))" }}
        tabIndex={-1}
        aria-label="Attach file"
      >
        <Paperclip size={18} />
      </button>
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder={placeholder}
        className="flex-1 bg-transparent outline-none font-sans text-sm"
        style={{ color: "hsl(var(--foreground))" }}
      />
      <button
        type="button"
        onClick={submit}
        disabled={!hasValue}
        aria-label="Send"
        className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 transition-colors"
        style={
          hasValue
            ? { background: "hsl(var(--primary))", color: "hsl(var(--primary-foreground))" }
            : { color: "hsl(var(--muted-foreground))", background: "transparent" }
        }
      >
        <Send size={16} />
      </button>
    </div>
  );
}
