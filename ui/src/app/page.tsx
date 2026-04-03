"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

type ChatResult = {
  answer: string;
  tool_calls: string[];
  supporting_data: Record<string, unknown>;
  warnings: string[];
};

const API_BASE =
  process.env.NEXT_PUBLIC_ORCHESTRATOR_URL ?? "http://localhost:8000";

export default function HomePage() {
  const [sessionId, setSessionId] = useState<string>("");
  const [files, setFiles] = useState<FileList | null>(null);
  const [ingestMsg, setIngestMsg] = useState<string>("");
  const [question, setQuestion] = useState<string>("");
  const [chatHistory, setChatHistory] = useState<
    Array<{ question: string; result: ChatResult }>
  >([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("initializing");

  const isReady = useMemo(
    () => Boolean(sessionId) && status === "ready",
    [sessionId, status]
  );

  useEffect(() => {
    const boot = async () => {
      const response = await fetch(`${API_BASE}/api/session`, { method: "POST" });
      const payload = await response.json();
      setSessionId(payload.session_id);
      setStatus("needs_upload");
    };
    void boot();
  }, []);

  const ingest = async (event: FormEvent) => {
    event.preventDefault();
    if (!files || files.length === 0) {
      setIngestMsg("Select at least one PDF.");
      return;
    }
    setBusy(true);
    setStatus("uploading");
    setIngestMsg("");
    try {
      const formData = new FormData();
      for (const file of Array.from(files)) {
        formData.append("files", file);
      }
      const response = await fetch(
        `${API_BASE}/api/documents/ingest?session_id=${encodeURIComponent(sessionId)}`,
        {
          method: "POST",
          body: formData
        }
      );
      const payload = await response.json();
      if (!response.ok) {
        setStatus("needs_upload");
        setIngestMsg(payload?.detail?.error ?? "Ingestion failed.");
        return;
      }
      setStatus("ready");
      setIngestMsg(`Ingested ${payload.count} transactions from ${payload.sources} file(s).`);
    } catch {
      setStatus("needs_upload");
      setIngestMsg("Network error while uploading documents.");
    } finally {
      setBusy(false);
    }
  };

  const ask = async (event: FormEvent) => {
    event.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, question })
      });
      const payload = await response.json();
      if (!response.ok) {
        setIngestMsg(payload?.detail?.error ?? "Failed to process question.");
        return;
      }
      setChatHistory((prev) => [...prev, { question, result: payload as ChatResult }]);
      setQuestion("");
    } catch {
      setIngestMsg("Network error while asking question.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main>
      <h1>Financial Data Assistant</h1>
      <p>Session: {sessionId || "creating..."}</p>

      <section className="card">
        <h2>1) Upload PDF Statements</h2>
        <form onSubmit={ingest}>
          <input
            type="file"
            multiple
            accept="application/pdf"
            onChange={(e) => setFiles(e.target.files)}
          />
          <div style={{ marginTop: "0.8rem" }}>
            <button type="submit" disabled={busy || !sessionId}>
              {busy && status === "uploading" ? "Uploading..." : "Ingest Documents"}
            </button>
          </div>
        </form>
        <p>{ingestMsg}</p>
      </section>

      <section className="card">
        <h2>2) Ask Questions</h2>
        <form onSubmit={ask}>
          <textarea
            rows={4}
            value={question}
            placeholder="Example: What are my biggest spending categories?"
            onChange={(e) => setQuestion(e.target.value)}
          />
          <div style={{ marginTop: "0.8rem" }}>
            <button type="submit" disabled={!isReady || busy}>
              Ask
            </button>
          </div>
        </form>
        {!isReady && <p>Upload statements first to enable chat.</p>}
      </section>

      {chatHistory.map((item, idx) => (
        <section className="card" key={`${idx}-${item.question}`}>
          <h3>Q: {item.question}</h3>
          <p><strong>A:</strong> {item.result.answer}</p>
          <p>
            <strong>Tools:</strong> {item.result.tool_calls.join(", ")}
          </p>
          <details>
            <summary>Supporting data</summary>
            <pre>{JSON.stringify(item.result.supporting_data, null, 2)}</pre>
          </details>
        </section>
      ))}
    </main>
  );
}
