"use client";

import { FormEvent, useEffect, useState } from "react";

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

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Home() {
  const [activeTab, setActiveTab] = useState<"execution" | "repository" | "diff" | "evaluation">("execution");
  
  // Task input state
  const [title, setTitle] = useState("Implement guarded logging");
  const [description, setDescription] = useState("Add an auditable execution logger with path verification and evidence collection.");
  const [repository, setRepository] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [autoApprove, setAutoApprove] = useState(false);
  const [busy, setBusy] = useState(false);
  
  // Execution result state
  const [result, setResult] = useState<RunResult | null>(null);
  const [recentRuns, setRecentRuns] = useState<Array<{ run_id: string; title: string; status: string; updated_at: string }>>([]);

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
      const res = await fetch(`${API}/api/v1/evaluations/run`, { method: "POST" });
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
        <div className="eyebrow">AUTONOMOUS SOFTWARE ENGINEERING · CONTROL PLANE</div>
        <h1>Observe. Plan. Guard. Verify.</h1>
        <p className="lede">
          Deterministic execution boundary, independent verification gates, durable Operation Journal, and
          fail-closed tool safety.
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
          Repository Context
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
              <label htmlFor="dry-run" style={{ margin: 0, cursor: "pointer" }}>
                Dry-run mode (default; preview changes without modifying files)
              </label>
            </div>

            <div className="checkbox-row">
              <input
                type="checkbox"
                id="auto-approve"
                checked={autoApprove}
                onChange={(e) => setAutoApprove(e.target.checked)}
              />
              <label htmlFor="auto-approve" style={{ margin: 0, cursor: "pointer" }}>
                Auto-approve real mutations (bypass operator pause gate)
              </label>
            </div>

            <button type="submit" disabled={busy}>
              {busy ? "Running guarded agent..." : "Dispatch Guarded Task"}
            </button>

            <p className="hint">
              Tools execute shell-free (`shell=False`) with strict timeouts, SQLite WAL journaling, and idempotency guarantees.
            </p>

            {/* Recent runs list */}
            {recentRuns.length > 0 && (
              <div style={{ marginTop: 24 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8", marginBottom: 8 }}>
                  Recent Runs ({recentRuns.length})
                </div>
                <div style={{ display: "grid", gap: 6, maxHeight: 150, overflowY: "auto" }}>
                  {recentRuns.slice(0, 5).map((r) => (
                    <div
                      key={r.run_id}
                      style={{
                        fontSize: 11,
                        padding: "6px 8px",
                        background: "#090e16",
                        borderRadius: 6,
                        border: "1px solid #1a2433",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      <span style={{ color: "#cbd5e1", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 220 }}>
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
              {result?.status && <span className={`status ${result.status}`}>{result.status}</span>}
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
                      <strong>Operator Approval Required</strong>
                      <p>
                        A mutating workspace action has been proposed and halted at the execution boundary. Operator approval will execute bounded changes. Rejection leaves repository unmodified.
                      </p>
                    </div>
                    <div className="approval-actions">
                      <button type="button" onClick={approveAndResume} disabled={busy}>
                        {busy ? "Applying..." : "Approve & Execute"}
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

                {/* Planned Steps */}
                {result.plan && result.plan.length > 0 && (
                  <div>
                    <h3 style={{ fontSize: 13, textTransform: "uppercase", color: "#64748b", margin: "16px 0 8px" }}>
                      Plan Steps ({result.plan.length})
                    </h3>
                    <div className="step-list">
                      {result.plan.map((step) => (
                        <div key={step.id} className="step-card">
                          <div className="step-header">
                            <span className="step-id">Step: {step.id}</span>
                            <span className={`status ${step.status ?? "pending"}`}>{step.status ?? "pending"}</span>
                          </div>
                          <p className="step-desc">{step.description}</p>
                          <div className="step-meta">
                            {step.tool && <span>Tool: <code>{step.tool}</code></span>}
                            {step.requires_approval && <span style={{ color: "#fbbf24" }}>Approval Gated</span>}
                            {step.validation_criteria && step.validation_criteria.length > 0 && (
                              <span>Validation: {step.validation_criteria[0]}</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Durable Operation Journal */}
                {result.operations && result.operations.length > 0 && (
                  <div>
                    <h3 style={{ fontSize: 13, textTransform: "uppercase", color: "#64748b", margin: "24px 0 8px" }}>
                      Durable Operation Journal ({result.operations.length})
                    </h3>
                    <table className="tool-table">
                      <thead>
                        <tr>
                          <th>Operation ID</th>
                          <th>Step</th>
                          <th>Tool</th>
                          <th>State</th>
                          <th>Attempt</th>
                          <th>Recovery / Idempotency</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.operations.map((op) => (
                          <tr key={op.operation_id}>
                            <td><code>{op.operation_id}</code></td>
                            <td>{op.step_id}</td>
                            <td><code>{op.tool}</code></td>
                            <td><span className={`status ${op.state}`}>{op.state}</span></td>
                            <td>#{op.execution_attempt}</td>
                            <td style={{ fontSize: 11, color: "#94a3b8" }}>
                              {op.recovery_status ? (
                                <span style={{ color: "#38bdf8" }}>{op.recovery_status}</span>
                              ) : (
                                <code>key:{op.idempotency_key.slice(0, 8)}</code>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Independent Verification Checks */}
                {result.verification && result.verification.length > 0 && (
                  <div>
                    <h3 style={{ fontSize: 13, textTransform: "uppercase", color: "#64748b", margin: "24px 0 8px" }}>
                      Independent Verification Checks ({result.verification.length})
                    </h3>
                    <div className="checks">
                      {result.verification.map((v) => (
                        <div key={v.check} className={`check ${v.passed ? "pass" : "fail"}`}>
                          <div className="check-icon">{v.passed ? "✓" : "×"}</div>
                          <div className="check-body">
                            <b>{v.check}</b>
                            <small>{v.detail}</small>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Tool Execution Records */}
                {result.evidence_records && result.evidence_records.length > 0 && (
                  <div>
                    <h3 style={{ fontSize: 13, textTransform: "uppercase", color: "#64748b", margin: "24px 0 8px" }}>
                      Tool Audit Trail & Bounded Execution ({result.evidence_records.length})
                    </h3>
                    <table className="tool-table">
                      <thead>
                        <tr>
                          <th>Tool Source</th>
                          <th>Summary</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.evidence_records.map((rec, i) => (
                          <tr key={i}>
                            <td><code>{rec.source}</code></td>
                            <td>{rec.summary}</td>
                            <td>
                              <span className={`risk-tag ${rec.passed ? "low" : "high"}`}>
                                {rec.passed ? "PASSED" : "FAILED"}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Event Timeline */}
                {result.events && result.events.length > 0 && (
                  <div>
                    <h3 style={{ fontSize: 13, textTransform: "uppercase", color: "#64748b", margin: "24px 0 8px" }}>
                      Lifecycle Timeline ({result.events.length})
                    </h3>
                    <div className="timeline">
                      {result.events.map((e, idx) => (
                        <div key={idx} className="timeline-event">
                          <span className="timeline-seq">#{e.sequence}</span>
                          <span className="timeline-status">{e.status}</span>
                          <span className="timeline-msg">{e.message}</span>
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

      {/* TAB 2: REPOSITORY CONTEXT */}
      {activeTab === "repository" && (
        <section className="panel">
          <div className="panel-title">Repository Intelligence & Context Index</div>
          {result?.repository ? (
            <div>
              <p style={{ color: "#94a3b8", fontSize: 13 }}>
                Root: <code>{result.repository.root ?? "Workspace root"}</code> | Total files:{" "}
                <b>{result.repository.file_count ?? 0}</b>
              </p>

              {/* Detected Frameworks */}
              {result.repository.frameworks && result.repository.frameworks.length > 0 && (
                <div style={{ margin: "16px 0" }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8", marginBottom: 8 }}>
                    DETECTED FRAMEWORKS & RUNNERS
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {result.repository.frameworks.map((fw) => (
                      <span
                        key={fw}
                        style={{
                          background: "rgba(56, 189, 248, 0.15)",
                          color: "#38bdf8",
                          border: "1px solid rgba(56, 189, 248, 0.3)",
                          borderRadius: 6,
                          padding: "4px 10px",
                          fontSize: 12,
                          fontWeight: 700,
                        }}
                      >
                        {fw}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Language breakdown */}
              {result.repository.languages && (
                <div style={{ display: "flex", gap: 10, margin: "14px 0", flexWrap: "wrap" }}>
                  {Object.entries(result.repository.languages).map(([lang, count]) => (
                    <div
                      key={lang}
                      style={{
                        background: "#090e16",
                        border: "1px solid #1f2b3b",
                        borderRadius: 8,
                        padding: "8px 12px",
                        fontSize: 12,
                      }}
                    >
                      <span style={{ color: "#60a5fa", textTransform: "capitalize", fontWeight: 700 }}>
                        {lang}
                      </span>
                      : {count}
                    </div>
                  ))}
                </div>
              )}

              {/* Dependency Manifests */}
              {result.repository.manifests && Object.keys(result.repository.manifests).length > 0 && (
                <div style={{ margin: "20px 0" }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8", marginBottom: 8 }}>
                    DISCOVERED DEPENDENCY MANIFESTS
                  </div>
                  <div style={{ display: "grid", gap: 10 }}>
                    {Object.entries(result.repository.manifests).map(([manifestFile, info]) => (
                      <div
                        key={manifestFile}
                        style={{
                          background: "#090e16",
                          border: "1px solid #1a2433",
                          borderRadius: 8,
                          padding: 12,
                        }}
                      >
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

              {/* Test-to-Source Mappings */}
              {result.repository.test_mappings && Object.keys(result.repository.test_mappings).length > 0 && (
                <div style={{ margin: "20px 0" }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8", marginBottom: 8 }}>
                    TEST-TO-SOURCE RELATIONSHIPS
                  </div>
                  <table className="tool-table" style={{ margin: 0 }}>
                    <thead>
                      <tr>
                        <th>Source File</th>
                        <th>Associated Test Files</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(result.repository.test_mappings).map(([src, tests]) => (
                        <tr key={src}>
                          <td><code>{src}</code></td>
                          <td>
                            {tests.map((t) => (
                              <code key={t} style={{ marginRight: 6, color: "#34d399" }}>{t}</code>
                            ))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* File list */}
              {result.repository.files && (
                <div style={{ maxHeight: 350, overflowY: "auto", border: "1px solid #1a2433", borderRadius: 8, marginTop: 16 }}>
                  <table className="tool-table" style={{ margin: 0 }}>
                    <thead>
                      <tr>
                        <th>Path</th>
                        <th>Language</th>
                        <th>Size (Bytes)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.repository.files.map((f) => (
                        <tr key={f.path}>
                          <td><code>{f.path}</code></td>
                          <td>{f.language}</td>
                          <td>{f.size}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : (
            <div className="empty">
              No repository inspected in the current run. Specify a repository path in the Execution Control tab to
              extract repository intelligence.
            </div>
          )}
        </section>
      )}

      {/* TAB 3: DIFF & RISK ANALYSIS */}
      {activeTab === "diff" && (
        <section className="grid">
          <div className="panel">
            <div className="panel-title">Unified Diff Input</div>
            <label htmlFor="diff-content">Git Diff Content</label>
            <textarea
              id="diff-content"
              style={{ minHeight: 280, fontFamily: "monospace", fontSize: 12 }}
              value={diffInput}
              onChange={(e) => setDiffInput(e.target.value)}
            />
            <button onClick={analyzeDiff} disabled={diffBusy}>
              {diffBusy ? "Analyzing..." : "Analyze Diff & Score Risk"}
            </button>
            <p className="hint">
              Detects file sensitivity (auth, infra, migrations), line additions/deletions, and structural risk score.
            </p>
          </div>

          <div className="panel">
            <div className="panel-title">
              <span>Risk Assessment</span>
              {diffAnalysis && <span className={`risk-tag ${diffAnalysis.risk}`}>{diffAnalysis.risk} RISK</span>}
            </div>

            {!diffAnalysis ? (
              <div className="empty">Paste a unified diff and click Analyze to review risk classifications.</div>
            ) : (
              <div>
                <div style={{ display: "flex", gap: 16, margin: "12px 0 20px" }}>
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

      {/* TAB 4: EVALUATION BENCHMARK SUITE */}
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
