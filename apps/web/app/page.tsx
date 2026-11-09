"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

interface Verification {
  check: string;
  passed: boolean;
  detail: string;
}

interface EventItem {
  sequence: number;
  status: string;
  message: string;
  timestamp?: string;
}

interface StepItem {
  id: string;
  description: string;
  tool?: string | null;
  status?: string;
  expected_outputs?: string[];
  validation_criteria?: string[];
  inputs?: Record<string, unknown>;
  requires_approval?: boolean;
  depends_on?: string[];
  preconditions?: string[];
  postconditions?: string[];
  attempt?: number;
}

interface ToolRecord {
  tool: string;
  result: Record<string, unknown>;
}

interface EvidenceRecord {
  source: string;
  category: string;
  summary: string;
  passed: boolean;
  data?: Record<string, unknown>;
}

interface FailureDiagnosis {
  category: string;
  message: string;
  recoverable: boolean;
  suggested_recovery: string;
}

interface JournalOperation {
  operation_id: string;
  step_id: string;
  idempotency_key: string;
  tool: string;
  input_hash: string;
  state: string;
  execution_attempt: number;
  precondition_hash?: string | null;
  postcondition_hash?: string | null;
  recovery_status?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

interface RepositorySummary {
  root?: string;
  file_count?: number;
  languages?: Record<string, number>;
  files?: Array<{ path: string; size: number; language: string }>;
  frameworks?: string[];
  manifests?: Record<string, { dependencies?: string[]; devDependencies?: string[]; scripts?: string[] }>;
  test_mappings?: Record<string, string[]>;
}

interface ApprovalRequest {
  plan_fingerprint: string;
  proposed_diff_hash: string;
  requested_at: string;
  approved: boolean;
  invalidated: boolean;
  invalidation_reason?: string | null;
}

interface RunResult {
  run_id?: string;
  status: string;
  plan?: StepItem[];
  repository?: RepositorySummary | null;
  verification?: Verification[];
  events?: EventItem[];
  tool_results?: ToolRecord[];
  evidence_records?: EvidenceRecord[];
  failure_diagnosis?: FailureDiagnosis | null;
  operations?: JournalOperation[];
  approval_request?: ApprovalRequest | null;
  cancellation_requested?: boolean;
}

interface EvaluationResult {
  scenario_id: string;
  category: string;
  title: string;
  passed: boolean;
  actual_status: string;
  policy_adhered: boolean;
  truthful: boolean;
  details: string[];
}

interface EvaluationReport {
  timestamp: string;
  total_scenarios: number;
  passed_scenarios: number;
  pass_rate: number;
  policy_adherence_rate: number;
  truthfulness_rate: number;
  scenarios: EvaluationResult[];
}

interface DiffAnalysisResult {
  risk: string;
  total_additions: number;
  total_deletions: number;
  files: Array<{ path: string; additions: number; deletions: number; risk: string }>;
}

interface BlastRadiusResult {
  target_file: string;
  direct_dependents: string[];
  transitive_dependents: string[];
  affected_tests: string[];
  impact_level: string;
  total_impacted_files: number;
}

interface DeliberationResponse {
  task: { title: string; description: string };
  consensus_reached: boolean;
  rounds_taken: number;
  target_files: string[];
  steps: Array<{ id: string; description: string; expected_files: string[] }>;
  critic_approved: boolean;
  critic_risk_score: number;
  critic_findings: Array<{ rule_id: string; severity: string; description: string }>;
  critic_summary: string;
}

interface DistillationMessage {
  role: string;
  content: string;
}

interface DistillationRecord {
  messages: DistillationMessage[];
  metadata: {
    run_id: string;
    task_title: string;
    verification_checks_passed: number;
    operations_count: number;
  };
}

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Home() {
  const [activeTab, setActiveTab] = useState<
    "execution" | "repository" | "deliberation" | "distillation" | "diff" | "evaluation"
  >("execution");

  // Task input state
  const [title, setTitle] = useState("Implement guarded logging");
  const [description, setDescription] = useState(
    "Add an auditable execution logger with path verification and evidence collection."
  );
  const [repository, setRepository] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [autoApprove, setAutoApprove] = useState(false);
  const [busy, setBusy] = useState(false);

  // Execution result state
  const [result, setResult] = useState<RunResult | null>(null);
  const [recentRuns, setRecentRuns] = useState<
    Array<{ run_id: string; title: string; status: string; updated_at: string }>
  >([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [liveLogs, setLiveLogs] = useState<Array<{ time: string; type: string; message: string }>>([]);
  const [steerInput, setSteerInput] = useState("");
  const activeWsRef = useRef<WebSocket | null>(null);

  // Blast Radius state
  const [blastTarget, setBlastTarget] = useState("");
  const [blastRadius, setBlastRadius] = useState<BlastRadiusResult | null>(null);
  const [blastBusy, setBlastBusy] = useState(false);

  // Deliberation state
  const [delibTitle, setDelibTitle] = useState("Architect authentication tokens");
  const [delibDesc, setDelibDesc] = useState(
    "Design and implement secure JWT token signing and verification with zero hardcoded secrets."
  );
  const [delibRepo, setDelibRepo] = useState("");
  const [delibResult, setDelibResult] = useState<DeliberationResponse | null>(null);
  const [delibBusy, setDelibBusy] = useState(false);

  // Distillation state
  const [distillRecords, setDistillRecords] = useState<DistillationRecord[]>([]);
  const [distillBusy, setDistillBusy] = useState(false);

  // Real-time WebSocket & SSE Telemetry listener
  useEffect(() => {
    if (!result?.run_id) return;
    const terminalStatuses = ["completed", "failed", "awaiting_approval", "reconciliation_required"];
    if (terminalStatuses.includes(result.status || "")) {
      setIsStreaming(false);
      return;
    }

    setIsStreaming(true);
    let ws: WebSocket | null = null;
    let eventSource: EventSource | null = null;

    function handleEvent(parsed: { event_type?: string; payload?: unknown }) {
      const now = new Date().toLocaleTimeString();
      const payloadStr =
        typeof parsed.payload === "string" ? parsed.payload : JSON.stringify(parsed.payload || {});
      setLiveLogs((prev) => [
        ...prev.slice(-99),
        {
          time: now,
          type: parsed.event_type || "event",
          message: payloadStr,
        },
      ]);

      if (parsed.event_type?.startsWith("status:")) {
        const payloadObj = parsed.payload as { status?: string } | undefined;
        const newStatus = payloadObj?.status;
        if (newStatus) {
          setResult((prev) => (prev ? { ...prev, status: newStatus } : null));
          if (terminalStatuses.includes(newStatus)) {
            setIsStreaming(false);
          }
        }
      }
    }

    function startSSE() {
      if (!result?.run_id) return;
      eventSource = new EventSource(`${API}/api/v1/runs/${result.run_id}/stream`);
      eventSource.onmessage = (e) => {
        try {
          handleEvent(JSON.parse(e.data));
        } catch {
          // ignore
        }
      };
      eventSource.onerror = () => {
        setIsStreaming(false);
        eventSource?.close();
      };
    }

    try {
      const wsUrl = `${API.replace(/^http/, "ws")}/api/v1/ws/runs/${result.run_id}`;
      ws = new WebSocket(wsUrl);
      activeWsRef.current = ws;

      ws.onmessage = (e) => {
        try {
          const parsed = JSON.parse(e.data);
          handleEvent(parsed);
          if (parsed.event_type === "action_result") {
            loadRuns();
            fetch(`${API}/api/v1/runs/${result.run_id}`)
              .then((r) => r.json())
              .then(setResult);
          }
        } catch {
          // ignore
        }
      };
      ws.onerror = () => {
        if (ws) ws.close();
        ws = null;
        activeWsRef.current = null;
        startSSE();
      };
    } catch {
      startSSE();
    }

    return () => {
      setIsStreaming(false);
      if (ws) ws.close();
      activeWsRef.current = null;
      if (eventSource) eventSource.close();
    };
  }, [result?.run_id, result?.status]);

  // Diff inspection state
  const [diffInput, setDiffInput] = useState(
    "diff --git a/app/auth.py b/app/auth.py\n--- a/app/auth.py\n+++ b/app/auth.py\n@@ -1,3 +1,4 @@\n def verify():\n+    log_audit_event()\n     return True\n"
  );
  const [diffAnalysis, setDiffAnalysis] = useState<DiffAnalysisResult | null>(null);
  const [diffBusy, setDiffBusy] = useState(false);

  // Evaluation state
  const [evalReport, setEvalReport] = useState<EvaluationReport | null>(null);
  const [evalBusy, setEvalBusy] = useState(false);

  // Load recent runs
  async function loadRuns() {
    try {
      const res = await fetch(`${API}/api/v1/runs`);
      if (res.ok) {
        const data = await res.json();
        setRecentRuns(data);
      }
    } catch {
      // Backend not yet running or offline
    }
  }

  useEffect(() => {
    loadRuns();
  }, []);

  async function submitRun(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const response = await fetch(`${API}/api/v1/runs`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          task: {
            title,
            description,
            repository: repository.trim() || null,
            dry_run: dryRun,
            auto_approve: autoApprove,
          },
        }),
      });
      const data = await response.json();
      setResult(data);
      loadRuns();
    } catch (err) {
      setResult({
        status: "failed",
        events: [{ sequence: 1, status: "failed", message: `API unreachable: ${err}` }],
      });
    } finally {
      setBusy(false);
    }
  }

  async function approveAndResume() {
    if (!result?.run_id) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/v1/runs/${result.run_id}/resume`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ approved: true }),
      });
      const updated = await res.json();
      setResult(updated);
      loadRuns();
    } catch (err) {
      alert(`Approval error: ${err}`);
    } finally {
      setBusy(false);
    }
  }

  async function rejectRun() {
    if (!result?.run_id) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/v1/runs/${result.run_id}/resume`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ approved: false }),
      });
      const updated = await res.json();
      setResult(updated);
      loadRuns();
    } catch (err) {
      alert(`Rejection error: ${err}`);
    } finally {
      setBusy(false);
    }
  }

  async function cancelRun() {
    if (!result?.run_id) return;
    setBusy(true);
    try {
      await fetch(`${API}/api/v1/runs/${result.run_id}/cancel`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ reason: "Operator cancelled run via Web UI" }),
      });
      const detailRes = await fetch(`${API}/api/v1/runs/${result.run_id}`);
      if (detailRes.ok) {
        setResult(await detailRes.json());
      }
      loadRuns();
    } catch (err) {
      alert(`Cancellation error: ${err}`);
    } finally {
      setBusy(false);
    }
  }

  function handleSendSteer(event: FormEvent) {
    event.preventDefault();
    if (!steerInput.trim()) return;
    const msg = steerInput.trim();

    if (activeWsRef.current && activeWsRef.current.readyState === WebSocket.OPEN) {
      activeWsRef.current.send(JSON.stringify({ action: "steer", guidance: msg }));
    }

    setLiveLogs((prev) => [
      ...prev,
      {
        time: new Date().toLocaleTimeString(),
        type: "operator:steer",
        message: msg,
      },
    ]);
    setSteerInput("");
  }

  async function calculateBlastRadius() {
    if (!repository.trim() || !blastTarget.trim()) {
      alert("Please enter both a Repository Path and Target File.");
      return;
    }
    setBlastBusy(true);
    try {
      const res = await fetch(`${API}/api/v1/repository/blast-radius`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          repository: repository.trim(),
          target_file: blastTarget.trim(),
        }),
      });
      if (res.ok) {
        setBlastRadius(await res.json());
      } else {
        const err = await res.json();
        alert(`Blast radius error: ${err.detail || "Failed to calculate"}`);
      }
    } catch (err) {
      alert(`Request failed: ${err}`);
    } finally {
      setBlastBusy(false);
    }
  }

  async function runDeliberationCouncil(event: FormEvent) {
    event.preventDefault();
    setDelibBusy(true);
    try {
      const res = await fetch(`${API}/api/v1/deliberate`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          task: {
            title: delibTitle,
            description: delibDesc,
            repository: delibRepo.trim() || null,
          },
        }),
      });
      if (res.ok) {
        setDelibResult(await res.json());
      } else {
        const err = await res.json();
        alert(`Deliberation error: ${err.detail || "Failed"}`);
      }
    } catch (err) {
      alert(`Deliberation request error: ${err}`);
    } finally {
      setDelibBusy(false);
    }
  }

  async function loadDistillationRecords() {
    setDistillBusy(true);
    try {
      const res = await fetch(`${API}/api/v1/distillation/export?limit=1000`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setDistillRecords(data.records || []);
      }
    } catch (err) {
      alert(`Distillation extraction error: ${err}`);
    } finally {
      setDistillBusy(false);
    }
  }

  function downloadDistillationJsonl() {
    if (distillRecords.length === 0) return;
    const content = distillRecords.map((r) => JSON.stringify(r)).join("\n");
    const blob = new Blob([content], { type: "application/jsonlines" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `distillation_dataset_${Date.now()}.jsonl`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function analyzeDiff() {
    setDiffBusy(true);
    try {
      const res = await fetch(`${API}/api/v1/analyze-diff`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ diff: diffInput }),
      });
      if (res.ok) {
        setDiffAnalysis(await res.json());
      }
    } catch (err) {
      alert(`Diff analysis failed: ${err}`);
    } finally {
      setDiffBusy(false);
    }
  }

  async function runEvaluations() {
    setEvalBusy(true);
    try {
      const res = await fetch(`${API}/api/v1/evaluation/run`, { method: "POST" });
      if (res.ok) {
        setEvalReport(await res.json());
      }
    } catch (err) {
      alert(`Evaluation failed: ${err}`);
    } finally {
      setEvalBusy(false);
    }
  }

  return (
    <main className="shell">
      <header>
        <div className="eyebrow">AUTONOMOUS SOFTWARE ENGINEERING · ENTERPRISE CONTROL PLANE</div>
        <h1>Observe. Plan. Guard. Verify.</h1>
        <p className="lede">
          Deterministic execution boundary, independent verification gates, durable Operation Journal,
          real-time WebSocket steering, and model distillation.
        </p>
      </header>

      {/* Operator Tabs */}
      <nav className="tabs">
        <button
          className={`tab ${activeTab === "execution" ? "active" : ""}`}
          onClick={() => setActiveTab("execution")}
        >
          Execution Control
        </button>
        <button
          className={`tab ${activeTab === "repository" ? "active" : ""}`}
          onClick={() => setActiveTab("repository")}
        >
          Repository & Blast Radius
        </button>
        <button
          className={`tab ${activeTab === "deliberation" ? "active" : ""}`}
          onClick={() => setActiveTab("deliberation")}
        >
          Multi-Agent Council
        </button>
        <button
          className={`tab ${activeTab === "distillation" ? "active" : ""}`}
          onClick={() => {
            setActiveTab("distillation");
            if (distillRecords.length === 0) loadDistillationRecords();
          }}
        >
          Model Distillation
        </button>
        <button
          className={`tab ${activeTab === "diff" ? "active" : ""}`}
          onClick={() => setActiveTab("diff")}
        >
          Diff & Risk Analysis
        </button>
        <button
          className={`tab ${activeTab === "evaluation" ? "active" : ""}`}
          onClick={() => setActiveTab("evaluation")}
        >
          Evaluation Suite (15 Scenarios)
        </button>
      </nav>

      {/* TAB 1: EXECUTION */}
      {activeTab === "execution" && (
        <section className="grid">
          {/* Start Run Panel */}
          <form className="panel" onSubmit={submitRun}>
            <div className="panel-title">Task Specification</div>

            <label htmlFor="task-title">Task Title</label>
            <input
              id="task-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
            />

            <label htmlFor="task-desc">Description & Constraints</label>
            <textarea
              id="task-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required
            />

            <label htmlFor="repo-path">Repository Path (Optional)</label>
            <input
              id="repo-path"
              value={repository}
              onChange={(e) => setRepository(e.target.value)}
              placeholder="C:/path/to/repo or /workspace/repo"
            />

            <div className="checkbox-row">
              <input
                type="checkbox"
                id="dry-run"
                checked={dryRun}
                onChange={(e) => setDryRun(e.target.checked)}
              />
              <label htmlFor="dry-run">
                <strong>Dry-run safe preview</strong> (no modifications without explicit approval)
              </label>
            </div>

            <div className="checkbox-row">
              <input
                type="checkbox"
                id="auto-approve"
                checked={autoApprove}
                onChange={(e) => setAutoApprove(e.target.checked)}
              />
              <label htmlFor="auto-approve">
                <strong>Auto-approve mutations</strong> (bypass approval gate for non-dry-runs)
              </label>
            </div>

            <button type="submit" disabled={busy}>
              {busy ? "Executing Task..." : "Dispatch Task"}
            </button>

            {/* Recent Runs History */}
            {recentRuns.length > 0 && (
              <div style={{ marginTop: 24, borderTop: "1px solid #1f2b3b", paddingTop: 16 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8", marginBottom: 8 }}>
                  RECENT EXECUTIONS ({recentRuns.length})
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 150, overflowY: "auto" }}>
                  {recentRuns.map((r) => (
                    <div
                      key={r.run_id}
                      onClick={() => {
                        fetch(`${API}/api/v1/runs/${r.run_id}`)
                          .then((res) => res.json())
                          .then((d) => {
                            setResult(d);
                            if (d.task?.repository) setRepository(d.task.repository);
                          });
                      }}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        padding: "6px 10px",
                        background: "#0c121d",
                        border: "1px solid #1c2636",
                        borderRadius: 6,
                        cursor: "pointer",
                        fontSize: 12,
                      }}
                    >
                      <span
                        style={{
                          color: "#cbd5e1",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          maxWidth: 220,
                        }}
                      >
                        {r.title}
                      </span>
                      <span className={`status ${r.status}`}>{r.status}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </form>

          {/* Evidence & Execution State Panel */}
          <section className="panel">
            <div className="panel-title">
              <span>Execution State & Evidence</span>
              <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                {isStreaming && (
                  <span style={{ color: "#34d399", fontSize: 11, display: "flex", alignItems: "center", gap: 5 }}>
                    <span style={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%", background: "#34d399" }} />
                    Live Duplex Telemetry
                  </span>
                )}
                {result?.status && <span className={`status ${result.status}`}>{result.status}</span>}
              </div>
            </div>

            {!result ? (
              <div className="empty">
                No active execution. Submit a task above or select a previous run to inspect the live audit trail.
              </div>
            ) : (
              <>
                {/* Operator Approval Banner */}
                {result.status === "awaiting_approval" && (
                  <div className="approval-banner">
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ background: "#f59e0b", color: "#000", fontWeight: 700, fontSize: 11, padding: "2px 6px", borderRadius: 4 }}>
                          GATE ENFORCED
                        </span>
                        <strong>Operator Approval Required</strong>
                      </div>
                      <p style={{ margin: "6px 0 0", color: "#94a3b8", fontSize: 12 }}>
                        A mutating workspace action has been proposed and halted at the execution boundary. Operator approval will execute bounded changes.
                      </p>
                      {result.approval_request && (
                        <div style={{ fontSize: 11, fontFamily: "monospace", color: "#64748b", marginTop: 6, display: "flex", gap: 12, flexWrap: "wrap" }}>
                          <span>Fingerprint: <code style={{ color: "#38bdf8" }}>{result.approval_request.plan_fingerprint.slice(0, 16)}...</code></span>
                          <span>Diff Hash: <code style={{ color: "#a78bfa" }}>{result.approval_request.proposed_diff_hash.slice(0, 16)}...</code></span>
                        </div>
                      )}
                    </div>
                    <div className="approval-actions" style={{ display: "flex", gap: 8 }}>
                      <button type="button" onClick={approveAndResume} disabled={busy}>
                        {busy ? "Applying..." : "Approve & Execute"}
                      </button>
                      <button
                        type="button"
                        onClick={rejectRun}
                        disabled={busy}
                        style={{ background: "#dc2626", color: "#fff", border: "none", padding: "6px 12px", borderRadius: 4, cursor: "pointer", fontSize: 12, fontWeight: 600 }}
                      >
                        {busy ? "Rejecting..." : "Reject"}
                      </button>
                    </div>
                  </div>
                )}

                {/* Failure Diagnosis Banner */}
                {result.failure_diagnosis && (
                  <div className="diagnosis-box">
                    <strong>
                      Failure Diagnosed: [{result.failure_diagnosis.category}] {result.failure_diagnosis.message}
                    </strong>
                    <p>
                      <b>Suggested Recovery:</b> {result.failure_diagnosis.suggested_recovery}
                    </p>
                  </div>
                )}

                {/* Live Real-time Streaming Terminal */}
                <div style={{ margin: "16px 0", background: "#05080e", border: "1px solid #1e293b", borderRadius: 8, padding: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "#94a3b8", display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ width: 8, height: 8, borderRadius: "50%", background: isStreaming ? "#10b981" : "#64748b" }} />
                      REAL-TIME DUPLEX TELEMETRY & CONSOLE {isStreaming && "(LIVE STREAMING)"}
                    </span>
                    <div style={{ display: "flex", gap: 6 }}>
                      {!["completed", "failed"].includes(result.status || "") && (
                        <button
                          type="button"
                          onClick={cancelRun}
                          disabled={busy}
                          style={{ fontSize: 11, padding: "2px 8px", background: "#7f1d1d", color: "#fca5a5", border: "1px solid #dc2626", borderRadius: 4, cursor: "pointer" }}
                        >
                          Cancel Run
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => setLiveLogs([])}
                        style={{ fontSize: 11, padding: "2px 8px", background: "#1e293b", color: "#94a3b8", border: "none", borderRadius: 4, cursor: "pointer" }}
                      >
                        Clear Console
                      </button>
                    </div>
                  </div>
                  <div style={{ maxHeight: 180, overflowY: "auto", fontFamily: "monospace", fontSize: 11, color: "#a5f3fc", lineHeight: 1.6, padding: "6px 8px", background: "#020408", borderRadius: 4 }}>
                    {liveLogs.length === 0 ? (
                      <span style={{ color: "#475569" }}>Listening for real-time WebSocket events and streaming tokens...</span>
                    ) : (
                      liveLogs.map((log, idx) => (
                        <div key={idx} style={{ display: "flex", gap: 8 }}>
                          <span style={{ color: "#64748b", flexShrink: 0 }}>[{log.time}]</span>
                          <span style={{ color: log.type.includes("fail") ? "#f87171" : log.type.includes("pass") ? "#4ade80" : log.type.includes("steer") ? "#eab308" : "#38bdf8", flexShrink: 0 }}>
                            {log.type}:
                          </span>
                          <span style={{ color: "#e2e8f0", wordBreak: "break-all" }}>{log.message}</span>
                        </div>
                      ))
                    )}
                  </div>

                  {/* Interactive Operator Steering Input */}
                  <form onSubmit={handleSendSteer} style={{ display: "flex", gap: 8, marginTop: 8 }}>
                    <input
                      type="text"
                      value={steerInput}
                      onChange={(e) => setSteerInput(e.target.value)}
                      placeholder="Live steer: inject guidance or constraints mid-flight..."
                      style={{ flex: 1, fontSize: 12, padding: "6px 10px", background: "#0f172a", border: "1px solid #334155", borderRadius: 4, color: "#f8fafc" }}
                    />
                    <button
                      type="submit"
                      style={{ fontSize: 12, padding: "6px 14px", background: "#0284c7", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}
                    >
                      Steer
                    </button>
                  </form>
                </div>

                {/* Planned Steps */}
                {result.plan && result.plan.length > 0 && (
                  <div>
                    <h3 style={{ fontSize: 13, textTransform: "uppercase", color: "#64748b", margin: "16px 0 8px" }}>
                      Plan Steps ({result.plan.length})
                    </h3>
                    <div style={{ display: "grid", gap: 8 }}>
                      {result.plan.map((s) => (
                        <div key={s.id} className="timeline-item">
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <strong>[{s.id}] {s.tool ?? "internal"}</strong>
                            <span className={`status ${s.status ?? "pending"}`}>{s.status ?? "pending"}</span>
                          </div>
                          <p style={{ margin: "4px 0 0", color: "#94a3b8", fontSize: 12 }}>{s.description}</p>
                          {s.depends_on && s.depends_on.length > 0 && (
                            <div style={{ fontSize: 11, color: "#38bdf8", marginTop: 4 }}>
                              Prerequisites: {s.depends_on.join(", ")}
                            </div>
                          )}
                          {s.preconditions && s.preconditions.length > 0 && (
                            <div style={{ fontSize: 11, color: "#a78bfa", marginTop: 2 }}>
                              Preconditions: {s.preconditions.join(" · ")}
                            </div>
                          )}
                          {s.postconditions && s.postconditions.length > 0 && (
                            <div style={{ fontSize: 11, color: "#34d399", marginTop: 2 }}>
                              Postconditions: {s.postconditions.join(" · ")}
                            </div>
                          )}
                          {s.validation_criteria && (
                            <div style={{ fontSize: 11, color: "#64748b", marginTop: 4 }}>
                              Criteria: {s.validation_criteria.join(" · ")}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Verification Gates */}
                {result.verification && result.verification.length > 0 && (
                  <div style={{ marginTop: 20 }}>
                    <h3 style={{ fontSize: 13, textTransform: "uppercase", color: "#64748b", margin: "0 0 8px" }}>
                      Independent Verification Checks ({result.verification.length})
                    </h3>
                    <div style={{ display: "grid", gap: 6 }}>
                      {result.verification.map((v, i) => (
                        <div
                          key={i}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 10,
                            padding: "8px 12px",
                            background: v.passed ? "rgba(16, 185, 129, 0.08)" : "rgba(239, 68, 68, 0.08)",
                            border: `1px solid ${v.passed ? "#059669" : "#dc2626"}`,
                            borderRadius: 6,
                          }}
                        >
                          <span style={{ fontWeight: 800, color: v.passed ? "#34d399" : "#f87171" }}>
                            {v.passed ? "✓ PASS" : "✗ FAIL"}
                          </span>
                          <span style={{ fontWeight: 600, color: "#e2e8f0", fontSize: 12 }}>{v.check}</span>
                          <span style={{ color: "#94a3b8", fontSize: 11, marginLeft: "auto" }}>{v.detail}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </section>
        </section>
      )}

      {/* TAB 2: REPOSITORY & BLAST RADIUS */}
      {activeTab === "repository" && (
        <section className="grid">
          {/* Blast Radius Analyzer Panel */}
          <div className="panel">
            <div className="panel-title">Architectural Blast Radius Calculator</div>
            <p className="hint" style={{ marginTop: 4, marginBottom: 16 }}>
              Compute full dependency graph and identify downstream modules and test suites impacted by changes.
            </p>

            <label htmlFor="blast-repo">Repository Path</label>
            <input
              id="blast-repo"
              value={repository}
              onChange={(e) => setRepository(e.target.value)}
              placeholder="e.g. C:/workspace/repo"
            />

            <label htmlFor="blast-target" style={{ marginTop: 12 }}>Target Source File</label>
            <input
              id="blast-target"
              value={blastTarget}
              onChange={(e) => setBlastTarget(e.target.value)}
              placeholder="e.g. app/cli.py or src/auth.ts"
            />

            <button type="button" onClick={calculateBlastRadius} disabled={blastBusy} style={{ marginTop: 16 }}>
              {blastBusy ? "Computing Blast Radius..." : "Calculate Blast Radius"}
            </button>

            {blastRadius && (
              <div style={{ marginTop: 20, borderTop: "1px solid #1f2b3b", paddingTop: 16 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8" }}>IMPACT ASSESSMENT</span>
                  <span className={`risk-tag ${blastRadius.impact_level.toLowerCase()}`}>
                    {blastRadius.impact_level} IMPACT ({blastRadius.total_impacted_files} files)
                  </span>
                </div>

                <div style={{ marginTop: 12, fontSize: 12 }}>
                  <div style={{ color: "#94a3b8", marginBottom: 4 }}>Direct Dependents ({blastRadius.direct_dependents.length}):</div>
                  {blastRadius.direct_dependents.length === 0 ? (
                    <div style={{ color: "#64748b" }}>None</div>
                  ) : (
                    blastRadius.direct_dependents.map((d) => (
                      <div key={d} style={{ color: "#cbd5e1", fontFamily: "monospace", fontSize: 11 }}>
                        • {d}
                      </div>
                    ))
                  )}
                </div>

                <div style={{ marginTop: 12, fontSize: 12 }}>
                  <div style={{ color: "#94a3b8", marginBottom: 4 }}>Affected Test Suites ({blastRadius.affected_tests.length}):</div>
                  {blastRadius.affected_tests.length === 0 ? (
                    <div style={{ color: "#64748b" }}>No direct test suites mapped</div>
                  ) : (
                    blastRadius.affected_tests.map((t) => (
                      <div key={t} style={{ color: "#34d399", fontFamily: "monospace", fontSize: 11 }}>
                        ✓ {t}
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Repository Summary Panel */}
          <div className="panel">
            <div className="panel-title">Repository Intelligence Summary</div>
            {result?.repository ? (
              <div>
                <div className="summary-badges" style={{ marginTop: 12 }}>
                  <span className="badge">Files Indexed: {result.repository.file_count}</span>
                  {result.repository.frameworks?.map((f) => (
                    <span key={f} className="badge" style={{ borderColor: "#3b82f6", color: "#60a5fa" }}>
                      {f}
                    </span>
                  ))}
                </div>

                {/* Languages breakdown */}
                {result.repository.languages && (
                  <div style={{ margin: "20px 0" }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8", marginBottom: 8 }}>
                      LANGUAGE DISTRIBUTION
                    </div>
                    <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                      {Object.entries(result.repository.languages).map(([lang, count]) => (
                        <div key={lang} style={{ background: "#0c121d", border: "1px solid #1c2636", padding: "6px 12px", borderRadius: 6 }}>
                          <span style={{ fontWeight: 700, color: "#e2e8f0" }}>{lang}: </span>
                          <span style={{ color: "#94a3b8" }}>{count} file(s)</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Discovered manifests */}
                {result.repository.manifests && Object.keys(result.repository.manifests).length > 0 && (
                  <div style={{ margin: "20px 0" }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8", marginBottom: 8 }}>
                      DISCOVERED DEPENDENCY MANIFESTS
                    </div>
                    <div style={{ display: "grid", gap: 10 }}>
                      {Object.entries(result.repository.manifests).map(([manifestFile, info]) => (
                        <div key={manifestFile} style={{ background: "#090e16", border: "1px solid #1a2433", borderRadius: 8, padding: 12 }}>
                          <div style={{ fontWeight: 700, color: "#e2e8f0", fontSize: 13, marginBottom: 6 }}>
                            <code>{manifestFile}</code>
                          </div>
                          {info.dependencies && info.dependencies.length > 0 && (
                            <div style={{ fontSize: 11, color: "#94a3b8" }}>
                              Dependencies ({info.dependencies.length}):{" "}
                              <span style={{ color: "#cbd5e1" }}>
                                {info.dependencies.slice(0, 10).join(", ")}
                                {info.dependencies.length > 10 ? "..." : ""}
                              </span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="empty">
                No repository inspected in the current execution run. Specify a repository path to inspect.
              </div>
            )}
          </div>
        </section>
      )}

      {/* TAB 3: MULTI-AGENT DELIBERATION COUNCIL */}
      {activeTab === "deliberation" && (
        <section className="grid">
          <form className="panel" onSubmit={runDeliberationCouncil}>
            <div className="panel-title">Deliberation Council Intake</div>
            <p className="hint" style={{ marginTop: 4, marginBottom: 16 }}>
              Dispatches task through multi-agent consensus: Architect (decomposition) → Coder (implementation) → Security Critic (AST & pattern review).
            </p>

            <label htmlFor="delib-title">Task Title</label>
            <input
              id="delib-title"
              value={delibTitle}
              onChange={(e) => setDelibTitle(e.target.value)}
              required
            />

            <label htmlFor="delib-desc" style={{ marginTop: 12 }}>Description & Architecture Goals</label>
            <textarea
              id="delib-desc"
              value={delibDesc}
              onChange={(e) => setDelibDesc(e.target.value)}
              required
            />

            <label htmlFor="delib-repo" style={{ marginTop: 12 }}>Target Repository (Optional)</label>
            <input
              id="delib-repo"
              value={delibRepo}
              onChange={(e) => setDelibRepo(e.target.value)}
              placeholder="e.g. C:/workspace/repo"
            />

            <button type="submit" disabled={delibBusy} style={{ marginTop: 16 }}>
              {delibBusy ? "Council Deliberating..." : "Convene Council"}
            </button>
          </form>

          <div className="panel">
            <div className="panel-title">
              <span>Council Deliberation Report</span>
              {delibResult && (
                <span className={`risk-tag ${delibResult.consensus_reached ? "low" : "high"}`}>
                  {delibResult.consensus_reached ? "CONSENSUS REACHED" : "REJECTED BY CRITIC"}
                </span>
              )}
            </div>

            {!delibResult ? (
              <div className="empty">
                Submit a task to trigger multi-agent consensus between Architect, Coder, and Security Critic.
              </div>
            ) : (
              <div style={{ marginTop: 12 }}>
                <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
                  <div style={{ background: "#090e16", border: "1px solid #1f2b3b", padding: 10, borderRadius: 6, flex: 1 }}>
                    <div style={{ fontSize: 11, color: "#64748b" }}>ROUNDS TAKEN</div>
                    <div style={{ fontSize: 20, fontWeight: 800, color: "#60a5fa" }}>{delibResult.rounds_taken}</div>
                  </div>
                  <div style={{ background: "#090e16", border: "1px solid #1f2b3b", padding: 10, borderRadius: 6, flex: 1 }}>
                    <div style={{ fontSize: 11, color: "#64748b" }}>CRITIC RISK SCORE</div>
                    <div style={{ fontSize: 20, fontWeight: 800, color: delibResult.critic_risk_score > 0 ? "#f87171" : "#34d399" }}>
                      {delibResult.critic_risk_score.toFixed(1)}
                    </div>
                  </div>
                  <div style={{ background: "#090e16", border: "1px solid #1f2b3b", padding: 10, borderRadius: 6, flex: 1 }}>
                    <div style={{ fontSize: 11, color: "#64748b" }}>SECURITY STATUS</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: delibResult.critic_approved ? "#34d399" : "#f87171", marginTop: 4 }}>
                      {delibResult.critic_approved ? "APPROVED" : "BLOCKED"}
                    </div>
                  </div>
                </div>

                <h4 style={{ fontSize: 12, textTransform: "uppercase", color: "#94a3b8", margin: "16px 0 8px" }}>
                  Architect Plan Steps ({delibResult.steps.length})
                </h4>
                <div style={{ display: "grid", gap: 8 }}>
                  {delibResult.steps.map((step) => (
                    <div key={step.id} style={{ background: "#0c121d", border: "1px solid #1c2636", padding: "8px 12px", borderRadius: 6 }}>
                      <div style={{ fontWeight: 700, color: "#e2e8f0", fontSize: 12 }}>[{step.id}] {step.description}</div>
                      {step.expected_files.length > 0 && (
                        <div style={{ color: "#64748b", fontSize: 11, marginTop: 4 }}>
                          Target files: {step.expected_files.join(", ")}
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                {delibResult.critic_findings.length > 0 && (
                  <div style={{ marginTop: 16 }}>
                    <h4 style={{ fontSize: 12, textTransform: "uppercase", color: "#f87171", margin: "16px 0 8px" }}>
                      Security Critic Findings ({delibResult.critic_findings.length})
                    </h4>
                    <div style={{ display: "grid", gap: 6 }}>
                      {delibResult.critic_findings.map((f, i) => (
                        <div key={i} style={{ background: "rgba(239,68,68,0.1)", border: "1px solid #dc2626", padding: "8px 12px", borderRadius: 6 }}>
                          <span style={{ fontWeight: 700, color: "#f87171", fontSize: 11 }}>[{f.severity.toUpperCase()}] {f.rule_id}: </span>
                          <span style={{ color: "#e2e8f0", fontSize: 12 }}>{f.description}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>
      )}

      {/* TAB 4: MODEL DISTILLATION */}
      {activeTab === "distillation" && (
        <section className="panel">
          <div className="panel-title">
            <span>Model Distillation Dataset Pipeline</span>
            <div style={{ display: "flex", gap: 10 }}>
              <button type="button" onClick={loadDistillationRecords} disabled={distillBusy}>
                {distillBusy ? "Harvesting..." : "Refresh Records"}
              </button>
              <button
                type="button"
                onClick={downloadDistillationJsonl}
                disabled={distillRecords.length === 0}
                style={{ background: "#0284c7" }}
              >
                Download JSONL ({distillRecords.length})
              </button>
            </div>
          </div>
          <p className="hint">
            Harvests verified agent trajectories with 100% passing verification checks from durable SQLite checkpoints and formats them into standard ChatML JSONL pairs for fine-tuning smaller 7B/14B coding models.
          </p>

          {distillRecords.length === 0 ? (
            <div className="empty" style={{ marginTop: 20 }}>
              No verified completed executions found in the Operation Journal yet. Execute successful tasks with verification gates passing to generate distillation records.
            </div>
          ) : (
            <div style={{ marginTop: 20 }}>
              <div style={{ display: "grid", gap: 12 }}>
                {distillRecords.slice(0, 10).map((rec, i) => (
                  <div key={i} style={{ background: "#090e16", border: "1px solid #1a2433", borderRadius: 8, padding: 14 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                      <span style={{ fontWeight: 700, color: "#60a5fa", fontSize: 13 }}>
                        Run: {rec.metadata.run_id} — {rec.metadata.task_title}
                      </span>
                      <span style={{ fontSize: 11, color: "#34d399", background: "rgba(52,211,153,0.1)", padding: "2px 8px", borderRadius: 4 }}>
                        {rec.metadata.verification_checks_passed} Checks Passed · {rec.metadata.operations_count} Operations
                      </span>
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 12 }}>
                      {rec.messages.map((m, mIdx) => (
                        <div key={mIdx} style={{ background: "#020408", padding: 8, borderRadius: 4 }}>
                          <span style={{ fontWeight: 700, color: m.role === "system" ? "#94a3b8" : m.role === "user" ? "#38bdf8" : "#4ade80", textTransform: "uppercase", fontSize: 10 }}>
                            {m.role}:
                          </span>
                          <pre style={{ margin: "4px 0 0", color: "#cbd5e1", whiteSpace: "pre-wrap", fontFamily: "monospace", fontSize: 11, maxHeight: 100, overflowY: "auto" }}>
                            {m.content}
                          </pre>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {/* TAB 5: DIFF & RISK ANALYSIS */}
      {activeTab === "diff" && (
        <section className="grid">
          <div className="panel">
            <div className="panel-title">Unified Diff Input</div>
            <label htmlFor="diff-content">Git Diff Content</label>
            <textarea
              id="diff-content"
              value={diffInput}
              onChange={(e) => setDiffInput(e.target.value)}
              rows={12}
            />
            <button type="button" onClick={analyzeDiff} disabled={diffBusy}>
              {diffBusy ? "Analyzing Diff..." : "Analyze Diff & Risk"}
            </button>
          </div>

          <div className="panel">
            <div className="panel-title">Risk Analysis & Blast Radius</div>
            {!diffAnalysis ? (
              <div className="empty">Paste a unified git diff on the left and click Analyze Diff.</div>
            ) : (
              <div>
                <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
                  <div style={{ background: "#090e16", border: "1px solid #1f2b3b", padding: 12, borderRadius: 8 }}>
                    <div style={{ fontSize: 11, color: "#64748b" }}>AGGREGATE RISK</div>
                    <div style={{ fontSize: 20, fontWeight: 800, color: diffAnalysis.risk === "high" ? "#f87171" : "#34d399", textTransform: "uppercase" }}>
                      {diffAnalysis.risk}
                    </div>
                  </div>
                  <div style={{ background: "#090e16", border: "1px solid #1f2b3b", padding: 12, borderRadius: 8 }}>
                    <div style={{ fontSize: 11, color: "#64748b" }}>TOTAL ADDITIONS</div>
                    <div style={{ fontSize: 24, fontWeight: 800, color: "#34d399" }}>
                      +{diffAnalysis.total_additions}
                    </div>
                  </div>
                  <div style={{ background: "#090e16", border: "1px solid #1f2b3b", padding: 12, borderRadius: 8 }}>
                    <div style={{ fontSize: 11, color: "#64748b" }}>TOTAL DELETIONS</div>
                    <div style={{ fontSize: 24, fontWeight: 800, color: "#f87171" }}>
                      -{diffAnalysis.total_deletions}
                    </div>
                  </div>
                </div>

                <h4 style={{ fontSize: 13, textTransform: "uppercase", color: "#64748b", marginBottom: 8 }}>
                  Files Modified ({diffAnalysis.files.length})
                </h4>
                <table className="tool-table">
                  <thead>
                    <tr>
                      <th>File Path</th>
                      <th>Changes</th>
                      <th>File Risk</th>
                    </tr>
                  </thead>
                  <tbody>
                    {diffAnalysis.files.map((file) => (
                      <tr key={file.path}>
                        <td><code>{file.path}</code></td>
                        <td>+{file.additions} / -{file.deletions}</td>
                        <td>
                          <span className={`risk-tag ${file.risk}`}>{file.risk}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      )}

      {/* TAB 6: EVALUATION BENCHMARK SUITE */}
      {activeTab === "evaluation" && (
        <section className="panel">
          <div className="panel-title">
            <span>Independent Evaluation Suite (15 Scenarios)</span>
            <button onClick={runEvaluations} disabled={evalBusy}>
              {evalBusy ? "Evaluating 15 Scenarios..." : "Run Evaluation Harness"}
            </button>
          </div>
          <p className="hint">
            The agent does NOT grade itself. A separate independent evaluator assesses task completion, policy adherence,
            truthfulness (refusal to claim false success), crash recovery, idempotency, timeouts, and prompt injection defense.
          </p>

          {!evalReport ? (
            <div className="empty">
              Click &quot;Run Evaluation Harness&quot; to execute the 15 benchmark scenarios against fresh isolated workspaces.
            </div>
          ) : (
            <div style={{ marginTop: 20 }}>
              <div className="eval-grid">
                <div className="eval-metric-card">
                  <div className="eval-metric-value">{Math.round(evalReport.pass_rate * 100)}%</div>
                  <div className="eval-metric-label">Pass Rate ({evalReport.passed_scenarios}/{evalReport.total_scenarios})</div>
                </div>
                <div className="eval-metric-card">
                  <div className="eval-metric-value" style={{ color: "#60a5fa" }}>
                    {Math.round(evalReport.policy_adherence_rate * 100)}%
                  </div>
                  <div className="eval-metric-label">Policy Adherence</div>
                </div>
                <div className="eval-metric-card">
                  <div className="eval-metric-value" style={{ color: "#a78bfa" }}>
                    {Math.round(evalReport.truthfulness_rate * 100)}%
                  </div>
                  <div className="eval-metric-label">Truthfulness (No False Success)</div>
                </div>
              </div>

              <h4 style={{ fontSize: 13, textTransform: "uppercase", color: "#64748b", margin: "24px 0 10px" }}>
                Scenario Breakdown ({evalReport.scenarios.length})
              </h4>
              <table className="tool-table">
                <thead>
                  <tr>
                    <th>Scenario ID</th>
                    <th>Category</th>
                    <th>Title</th>
                    <th>Result</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {evalReport.scenarios.map((sc) => (
                    <tr key={sc.scenario_id}>
                      <td><code>{sc.scenario_id}</code></td>
                      <td style={{ textTransform: "capitalize" }}>{sc.category.replace(/_/g, " ")}</td>
                      <td>{sc.title}</td>
                      <td>
                        <span className={`risk-tag ${sc.passed ? "low" : "high"}`}>
                          {sc.passed ? "PASSED" : "FAILED"}
                        </span>
                      </td>
                      <td style={{ fontSize: 11, color: "#94a3b8" }}>{sc.details[0] ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
