import { useCallback, useRef, useState } from "react";
import { API_BASE } from "../lib/api";

/** Split an SSE buffer into complete `event:`/`data:` frames plus the unparsed tail. */
function parseSseBuffer(buffer) {
  const frames = buffer.split("\n\n");
  const rest = frames.pop() ?? "";
  const events = [];
  for (const frame of frames) {
    const event = frame.match(/^event: (.+)$/m);
    const data = frame.match(/^data: (.+)$/m);
    if (!event || !data) continue;
    try {
      events.push({ event: event[1].trim(), data: JSON.parse(data[1]) });
    } catch {
      /* skip malformed frame */
    }
  }
  return { events, rest };
}

function appendToLastAgent(messages, text, { replaceIfEmpty = false } = {}) {
  if (messages.length === 0) return messages;
  const next = [...messages];
  const last = next[next.length - 1];
  if (last.role !== "agent") return messages;
  next[next.length - 1] = {
    ...last,
    content: replaceIfEmpty ? last.content || text : last.content + text,
  };
  return next;
}

/**
 * Streams a conversation with the orchestrator over POST /api/chat (SSE).
 * Events: pipeline_step (upserted by id), delta (answer text), done, error.
 */
export default function useAgentChat() {
  const [messages, setMessages] = useState([]);
  const [pipelineSteps, setPipelineSteps] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeSkill, setActiveSkill] = useState(null);
  const [activeFiles, setActiveFiles] = useState([]);
  const abortRef = useRef(null);

  const stopStream = useCallback(() => {
    abortRef.current?.abort();
    setIsStreaming(false);
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setPipelineSteps([]);
    setIsStreaming(false);
    setActiveSkill(null);
    setActiveFiles([]);
  }, []);

  const sendMessage = useCallback(async (text, options) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setMessages((prev) => [...prev, { role: "user", content: text }, { role: "agent", content: "" }]);
    setPipelineSteps([]);
    setActiveSkill(null);
    setActiveFiles([]);
    setIsStreaming(true);

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: options?.augment ? `${options.augment}\n\n${text}` : text,
          journeyId: options?.journeyId,
        }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const { events, rest } = parseSseBuffer(buffer);
        buffer = rest;

        for (const { event, data } of events) {
          switch (event) {
            case "pipeline_step": {
              setPipelineSteps((prev) => {
                const idx = prev.findIndex((s) => s.id === data.id);
                if (idx === -1) return [...prev, data];
                const next = [...prev];
                next[idx] = { ...next[idx], ...data };
                return next;
              });
              if (data.type === "skill_load") {
                setActiveSkill(data.label.replace("Loading skill — ", ""));
              }
              if (data.file) {
                setActiveFiles((prev) => (prev.includes(data.file) ? prev : [...prev, data.file]));
              }
              break;
            }
            case "delta":
              setMessages((prev) => appendToLastAgent(prev, data.text ?? ""));
              break;
            case "done":
              setIsStreaming(false);
              break;
            case "error": {
              const message = data.error ?? "Unknown error";
              console.error("[chat] agent error:", message);
              setMessages((prev) => appendToLastAgent(prev, `\n\n[Error: ${message}]`));
              setIsStreaming(false);
              break;
            }
            default:
              break;
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name !== "AbortError") {
        console.error("[chat] stream connection error:", err);
        setMessages((prev) =>
          appendToLastAgent(prev, `[Connection error: ${err.message}]`, { replaceIfEmpty: true }),
        );
      }
      setIsStreaming(false);
    }
  }, []);

  return {
    messages,
    pipelineSteps,
    isStreaming,
    activeSkill,
    activeFiles,
    sendMessage,
    stopStream,
    reset,
  };
}
