/**
 * API type definitions — mirrors xrpl_lab/api/schemas.py exactly.
 * DO NOT edit these interfaces without updating the Python models first.
 * Drift is caught by tests/test_schema_drift.py.
 */

const API_BASE = 'http://localhost:8321';

/**
 * fetch() with a hard timeout via AbortController.
 *
 * If `timeoutMs` elapses before the response begins, the fetch is aborted
 * and the returned promise rejects with a DOMException whose `name` is
 * `'AbortError'` — distinguishable from network failures (which surface as
 * `TypeError`). Default 10s; one knob, no per-call overrides.
 *
 * Smallest-correct-change resilience for dashboard fetches (F-FE-B-005):
 * a hung API server no longer locks the dashboard tab indefinitely. Retry
 * and backoff are intentionally NOT layered here — WS reconnect already
 * carries the resilience story for live runs.
 */
export async function fetchWithTimeout(
  url: string,
  init?: RequestInit,
  timeoutMs = 10000
): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(id);
  }
}

async function request<T>(path: string): Promise<T> {
  const res = await fetchWithTimeout(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API ${path} returned ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export interface ModuleSummary {
  id: string;
  title: string;
  track: string;
  summary: string;
  level: string;
  time_estimate: string;
  mode: string;
  requires: string[];
  produces: string[];
  checks: string[];
  completed: boolean;
  is_next: boolean;
}

// FRONTEND-A-002: standalone (does NOT extend ModuleSummary). The backend
// Pydantic ModuleDetail (xrpl_lab/api/schemas.py) sends ONLY these fields —
// it omits summary/track/mode/requires/produces/is_next that ModuleSummary
// carries. Mirror it field-for-field so the TS type can't promise data the
// /api/modules/{id} response never delivers.
export interface ModuleDetail {
  id: string;
  title: string;
  level: string;
  time_estimate: string;
  prerequisites: string[];
  artifacts: string[];
  checks: string[];
  completed: boolean;
  description: string;
  steps: string[];
}

export interface TrackProgressItem {
  track: string;
  completed: string[];
  remaining: string[];
  total: number;
  done: number;
  is_complete: boolean;
}

export interface Status {
  modules_completed: number;
  modules_total: number;
  wallet_configured: boolean;
  wallet_address: string | null;
  last_run: {
    module: string;
    timestamp: string;
    success: boolean;
  } | null;
  workspace: string;
  current_module: string | null;
  current_track: string | null;
  current_mode: string | null;
  blockers: string[];
  is_blocked: boolean;
  track_progress: TrackProgressItem[];
  has_proof_pack: boolean;
  has_certificate: boolean;
  report_count: number;
  // Active network ("dry-run" | "testnet" | "devnet" | "local" | "mainnet" |
  // "unknown") and tool version — rendered by the Network card and the footer.
  network: string;
  version: string;
}

export interface DoctorResult {
  overall: string;
  checks: Array<{
    name: string;
    status: 'pass' | 'warn' | 'fail';
    message: string;
  }>;
}

export interface ProofPack {
  version: string;
  generated: string;
  modules: Array<{
    id: string;
    completed: boolean;
    txids: string[];
  }>;
  integrity: string;
}

export interface Certificate {
  holder: string;
  issued: string;
  modules_completed: string[];
  hash: string;
}

export interface Report {
  title: string;
  generated: string;
  content: string;
}

export async function fetchModules(): Promise<ModuleSummary[]> {
  return request<ModuleSummary[]>('/api/modules');
}

export async function fetchStatus(): Promise<Status> {
  return request<Status>('/api/status');
}

export async function fetchModule(id: string): Promise<ModuleDetail> {
  return request<ModuleDetail>(`/api/modules/${id}`);
}

export async function fetchProofPack(): Promise<ProofPack> {
  return request<ProofPack>('/api/artifacts/proof-pack');
}

export async function fetchCertificate(): Promise<Certificate> {
  return request<Certificate>('/api/artifacts/certificate');
}

export async function fetchReports(): Promise<Report[]> {
  return request<Report[]>('/api/artifacts/reports');
}

export async function fetchDoctor(): Promise<DoctorResult> {
  return request<DoctorResult>('/api/doctor');
}

// --- Verify API (FT-PROOF-001 — browser proof verifier) ---
// Mirrors xrpl_lab/api/schemas.py: VerifyResponse / VerifyLiveResult /
// VerifyTxResult. The offline hash layer (hash_valid/hash_message) ALWAYS runs;
// `live` is present only when on-ledger verification was requested AND the hash
// passed (an edited artifact is untrustworthy regardless of its txids).

export interface VerifyTxResult {
  txid: string;
  network: string;
  status: string; // "PASS" | "FAIL" | "SKIPPED"
  reason: string;
  checks: string[];
  explorer_url: string;
}

export interface VerifyLiveResult {
  artifact_kind: string; // "proof_pack" | "certificate"
  overall_passed: boolean;
  no_onledger_txids: boolean;
  passed: number;
  failed: number;
  skipped: number;
  note: string;
  tx_results: VerifyTxResult[];
}

export interface VerifyResponse {
  artifact_kind: string; // "proof_pack" | "certificate"
  hash_valid: boolean;
  hash_message: string;
  overall_passed: boolean;
  live_requested: boolean;
  live: VerifyLiveResult | null;
  version: string;
  address: string;
  network: string;
}

/**
 * POST a pasted proof pack / certificate to /api/verify.
 *
 * `artifact` is the parsed JSON object (untrusted — the server re-validates and
 * never trusts its shape). `live` adds the on-ledger trust layer via `?live=`.
 * On a non-OK response the body is the structured {code,message,hint} envelope;
 * the caller surfaces it honestly rather than treating every failure as offline.
 */
export async function verifyArtifact(
  artifact: unknown,
  live: boolean
): Promise<VerifyResponse> {
  const res = await fetchWithTimeout(`${API_BASE}/api/verify?live=${live}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(artifact),
  });
  if (!res.ok) {
    // Tag the status (and any structured detail) so the page can report the
    // server's verdict — a 400 here is "bad artifact", not "API offline".
    let detail = '';
    try {
      const body = await res.json();
      detail = body?.detail?.message || body?.message || '';
    } catch { /* non-JSON error body */ }
    const e = new Error(`Verify API returned ${res.status}: ${res.statusText}`);
    (e as any).httpStatus = res.status;
    (e as any).detail = detail;
    throw e;
  }
  return res.json() as Promise<VerifyResponse>;
}

// --- Run API (Wave 2) ---

export interface RunResult {
  run_id: string;
  status: string;
}

export async function startModuleRun(id: string, dryRun: boolean): Promise<RunResult> {
  const res = await fetchWithTimeout(`${API_BASE}/api/run/${id}?dry_run=${dryRun}`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error(`Run API returned ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<RunResult>;
}

// --- Runs API (facilitator observability — Stage B wave 2 P1) ---

export interface RunInfo {
  run_id: string;
  module_id: string;
  status: string; // "running" | "completed" | "failed"
  created_at: string; // ISO 8601 UTC
  elapsed_seconds: number;
  queue_size: number;
  dry_run: boolean;
}

export interface RunListResponse {
  runs: RunInfo[];
  max_concurrent: number;
  active_count: number;
}

export async function fetchRuns(): Promise<RunListResponse> {
  return request<RunListResponse>('/api/runs');
}

export async function fetchRun(runId: string): Promise<RunInfo> {
  return request<RunInfo>(`/api/runs/${runId}`);
}

/**
 * Cancel an active run (DELETE /api/runs/{run_id}).
 *
 * Bridge agent ships this endpoint in parallel during Phase 7 wave 1;
 * if invoked before that lands, the API returns 404 and the caller
 * should surface the error gracefully rather than spin.
 */
export async function cancelRun(runId: string): Promise<{ ok: boolean; status: number; statusText: string }> {
  const res = await fetchWithTimeout(`${API_BASE}/api/runs/${runId}`, {
    method: 'DELETE',
  });
  return { ok: res.ok, status: res.status, statusText: res.statusText };
}

// NOTE: a `connectRunWebSocket` helper was removed in the 2026-06-22 re-swarm
// (B-FE-001). It was dead (no call sites) AND a resilience trap — a bare
// WebSocket with none of the reconnect / liveness-watchdog / close-code
// handling that the run page (run/[id].astro) inlines. If a shared WS client is
// ever wanted, promote that page's resilient `connectWS` here rather than
// reintroducing a defenseless duplicate.
