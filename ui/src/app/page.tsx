"use client";

import {
  ChangeEvent,
  FormEvent,
  KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react";

type ChatResult = {
  answer: string;
  tool_calls: string[];
  supporting_data: Record<string, unknown>;
  warnings: string[];
};

type MessageRole = "user" | "assistant" | "system" | "error";

type ChatMessage = {
  id: string;
  role: MessageRole;
  text: string;
  attachments?: string[];
  toolCalls?: string[];
  supportingData?: Record<string, unknown>;
  warnings?: string[];
};

const API_BASE =
  process.env.NEXT_PUBLIC_ORCHESTRATOR_URL ?? "http://localhost:8000";

export default function HomePage() {
  const [sessionId, setSessionId] = useState<string>("");
  const [composerText, setComposerText] = useState("");
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const boot = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/session`, { method: "POST" });
        const payload = await response.json();
        if (!response.ok || !payload?.session_id) {
          setMessages([
            {
              id: crypto.randomUUID(),
              role: "error",
              text: "Unable to initialize session. Please refresh and try again.",
            },
          ]);
          return;
        }
        setSessionId(payload.session_id);
        setMessages([
          {
            id: crypto.randomUUID(),
            role: "system",
            text: "Session ready. Attach PDF statements and ask a question in one message.",
          },
        ]);
      } catch {
        setMessages([
          {
            id: crypto.randomUUID(),
            role: "error",
            text: "Network error while creating session.",
          },
        ]);
      }
    };
    void boot();
  }, []);

  const onPickFiles = () => {
    fileInputRef.current?.click();
  };

  const onFilesSelected = (event: ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(event.target.files ?? []);
    if (!selected.length) return;

    const onlyPdf = selected.filter((file) => {
      const byMime = file.type === "application/pdf";
      const byName = file.name.toLowerCase().endsWith(".pdf");
      return byMime || byName;
    });

    if (onlyPdf.length !== selected.length) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "error",
          text: "Only PDF files are supported for attachments.",
        },
      ]);
    }

    if (onlyPdf.length > 0) {
      setPendingFiles((prev) => [...prev, ...onlyPdf]);
    }
    event.target.value = "";
  };

  const removeAttachment = (index: number) => {
    setPendingFiles((prev) => prev.filter((_, idx) => idx !== index));
  };

  const handleComposerEnter = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      const form = event.currentTarget.form;
      form?.requestSubmit();
    }
  };

  const handleSend = async (event: FormEvent) => {
    event.preventDefault();
    const text = composerText.trim();
    const hasFiles = pendingFiles.length > 0;
    if (!text && !hasFiles) return;

    if (!sessionId) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "error",
          text: "Session is still initializing. Please try again.",
        },
      ]);
      return;
    }

    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: "user",
        text: text || "(uploaded documents)",
        attachments: pendingFiles.map((file) => file.name),
      },
    ]);

    setIsSending(true);
    let shouldContinueToChat = Boolean(text);

    try {
      if (hasFiles) {
        setIsIngesting(true);
        const formData = new FormData();
        for (const file of pendingFiles) {
          formData.append("files", file);
        }

        const ingestResponse = await fetch(
          `${API_BASE}/api/documents/ingest?session_id=${encodeURIComponent(sessionId)}`,
          { method: "POST", body: formData }
        );
        const ingestPayload = await ingestResponse.json();
        if (!ingestResponse.ok) {
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: "error",
              text: ingestPayload?.detail?.error ?? "Failed to ingest attached PDFs.",
            },
          ]);
          shouldContinueToChat = false;
        } else {
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: "system",
              text: `Ingested ${ingestPayload.count} transactions from ${ingestPayload.sources} file(s).`,
            },
          ]);
        }
      }

      if (shouldContinueToChat) {
        const chatResponse = await fetch(`${API_BASE}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, question: text }),
        });
        const chatPayload = await chatResponse.json();
        if (!chatResponse.ok) {
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: "error",
              text: chatPayload?.detail?.error ?? "Failed to process your question.",
            },
          ]);
        } else {
          const result = chatPayload as ChatResult;
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: "assistant",
              text: result.answer,
              toolCalls: result.tool_calls,
              supportingData: result.supporting_data,
              warnings: result.warnings,
            },
          ]);
        }
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "error",
          text: "Network error while processing your request.",
        },
      ]);
    } finally {
      setComposerText("");
      setPendingFiles([]);
      setIsSending(false);
      setIsIngesting(false);
    }
  };

  return (
    <main className="chat-shell">
      <header className="chat-header">
        <h1>Financial Data Assistant</h1>
        <p>Session: {sessionId || "creating..."}</p>
      </header>

      <section className="chat-thread">
        {messages.map((message) => (
          <article
            className={`message message-${message.role}`}
            key={message.id}
          >
            <div className="message-text">{message.text}</div>
            {message.attachments && message.attachments.length > 0 && (
              <div className="message-attachments">
                {message.attachments.map((name) => (
                  <span className="attachment-chip" key={`${message.id}-${name}`}>
                    {name}
                  </span>
                ))}
              </div>
            )}
            {message.role === "assistant" && (
              <>
                {message.toolCalls && message.toolCalls.length > 0 && (
                  <div className="message-meta">
                    Tools: {message.toolCalls.join(", ")}
                  </div>
                )}
                {message.warnings && message.warnings.length > 0 && (
                  <div className="message-meta">
                    Warnings: {message.warnings.join(" | ")}
                  </div>
                )}
                {message.supportingData && (
                  <details className="supporting-data">
                    <summary>Supporting data</summary>
                    <pre>{JSON.stringify(message.supportingData, null, 2)}</pre>
                  </details>
                )}
              </>
            )}
          </article>
        ))}
      </section>

      <form className="composer" onSubmit={handleSend}>
        {pendingFiles.length > 0 && (
          <div className="pending-attachments">
            {pendingFiles.map((file, index) => (
              <button
                className="attachment-chip removable"
                key={`${file.name}-${index}`}
                onClick={() => removeAttachment(index)}
                type="button"
              >
                {file.name} x
              </button>
            ))}
          </div>
        )}

        <div className="composer-row">
          <button
            className="icon-button"
            onClick={onPickFiles}
            type="button"
            disabled={isSending}
            title="Attach PDF"
          >
            Attach PDF
          </button>
          <input
            ref={fileInputRef}
            type="file"
            hidden
            multiple
            accept="application/pdf,.pdf"
            onChange={onFilesSelected}
          />
          <textarea
            value={composerText}
            onChange={(event) => setComposerText(event.target.value)}
            onKeyDown={handleComposerEnter}
            placeholder="Ask about your spending, anomalies, crypto, stocks, or currency conversion..."
            rows={2}
            disabled={isSending}
          />
          <button
            type="submit"
            disabled={isSending || (!composerText.trim() && pendingFiles.length === 0)}
          >
            {isIngesting ? "Uploading..." : isSending ? "Sending..." : "Send"}
          </button>
        </div>
      </form>
    </main>
  );
}
