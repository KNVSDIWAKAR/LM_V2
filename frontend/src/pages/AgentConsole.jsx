import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { Send, Square } from "lucide-react";
import { useLocation, useSearch } from "wouter";
import useAgentChat from "../hooks/useAgentChat";
import ChatMessage from "../components/chat/ChatMessage";
import PipelineSteps from "../components/chat/PipelineSteps";
import AgentContextPanel from "../components/chat/AgentContextPanel";

const panelStyle = {
  background: "hsl(var(--card))",
  borderColor: "hsl(var(--border))",
  borderRadius: "var(--radius)",
};

export default function AgentConsole() {
  const { messages, pipelineSteps, isStreaming, activeSkill, activeFiles, sendMessage, stopStream } =
    useAgentChat();
  const [draft, setDraft] = useState("");
  const bottomRef = useRef(null);
  const consumedQueryRef = useRef(false);
  const [, navigate] = useLocation();
  const search = useSearch();

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pipelineSteps]);

  // Command Center hands off its prompt via ?message=…; send it once, then clean the URL.
  useEffect(() => {
    if (consumedQueryRef.current) return;
    const message = new URLSearchParams(search ?? "").get("message");
    if (message) {
      consumedQueryRef.current = true;
      sendMessage(message);
      navigate("/agent-console", { replace: true });
    }
  }, [search, sendMessage, navigate]);

  const submit = useCallback(() => {
    const text = draft.trim();
    if (!text || isStreaming) return;
    setDraft("");
    sendMessage(text);
  }, [draft, isStreaming, sendMessage]);

  const onKeyDown = useCallback(
    (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        submit();
      }
    },
    [submit],
  );

  const reversedIdx = [...messages].reverse().findIndex((m) => m.role === "agent");
  const lastAgentIdx = reversedIdx !== -1 ? messages.length - 1 - reversedIdx : -1;
  const hasDraft = draft.trim().length > 0;

  return (
    <div className="flex gap-4" style={{ height: "calc(100vh - 80px)", overflow: "hidden" }}>
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex-none mb-4">
          <h1 className="font-serif text-2xl leading-tight" style={{ color: "hsl(var(--foreground))" }}>
            Mortgage Operations Orchestrator
          </h1>
          <div className="flex items-center gap-1.5 mt-1">
            <span className="w-2 h-2 rounded-full flex-none" style={{ background: "hsl(142, 71%, 45%)" }} />
            <span className="text-xs font-sans" style={{ color: "hsl(var(--muted-foreground))" }}>
              Online &amp; Ready
            </span>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto rounded border px-4 py-4 mb-3" style={panelStyle}>
          {messages.length === 0 ? (
            <div className="flex items-center justify-center h-full" style={{ color: "hsl(var(--muted-foreground))" }}>
              <p className="font-sans text-sm text-center">
                Send a message to start a conversation with the Mortgage Operations Orchestrator.
              </p>
            </div>
          ) : (
            messages.map((message, i) => {
              const showSteps = i === lastAgentIdx && (isStreaming || pipelineSteps.length > 0);
              return (
                <Fragment key={i}>
                  {showSteps && message.role === "agent" && (
                    <PipelineSteps steps={pipelineSteps} isStreaming={isStreaming} />
                  )}
                  <ChatMessage message={message} />
                </Fragment>
              );
            })
          )}
          <div ref={bottomRef} />
        </div>

        <div className="flex-none rounded border px-3 py-2" style={panelStyle}>
          <div className="flex items-end gap-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              rows={1}
              placeholder="Message Mortgage Operations Orchestrator..."
              disabled={isStreaming}
              className="flex-1 resize-none font-sans text-sm outline-none bg-transparent leading-relaxed"
              style={{
                color: "hsl(var(--foreground))",
                caretColor: "hsl(var(--primary))",
                minHeight: "36px",
                maxHeight: "120px",
              }}
              onInput={(e) => {
                const el = e.currentTarget;
                el.style.height = "auto";
                el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
              }}
            />
            <button
              onClick={isStreaming ? stopStream : submit}
              disabled={!isStreaming && !hasDraft}
              className="flex-none flex items-center justify-center w-8 h-8 rounded transition-colors"
              style={{
                background: isStreaming
                  ? "hsl(0, 84%, 60%)"
                  : hasDraft
                    ? "hsl(var(--primary))"
                    : "hsl(var(--muted))",
                color: isStreaming || hasDraft ? "hsl(var(--primary-foreground))" : "hsl(var(--muted-foreground))",
              }}
              aria-label={isStreaming ? "Stop" : "Send"}
            >
              {isStreaming ? <Square size={14} fill="currentColor" /> : <Send size={14} />}
            </button>
          </div>
          <p className="mt-1.5 text-xs font-sans" style={{ color: "hsl(var(--muted-foreground))" }}>
            AI can make mistakes. Verify critical loan data.
          </p>
        </div>
      </div>

      <AgentContextPanel activeSkill={activeSkill} activeFiles={activeFiles} />
    </div>
  );
}
