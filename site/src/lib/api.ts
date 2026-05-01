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

export interface ModuleDetail extends ModuleSummary {
  prerequisites: string[];
  artifacts: string[];
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

// --- Run API (Wave 2) ---

export interface RunResult {
  run_id: string;
  status: string;
}

export interface RunHandlers {
  onStep?: (data: { action: string; index: number; total: number }) => void;
  onOutput?: (data: { text: string }) => void;
  onStepComplete?: (data: { action: string; success: boolean }) => void;
  onTx?: (data: { txid: string; result_code: string }) => void;
  onError?: (data: { message: string }) => void;
  onComplete?: (data: { success: boolean; txids: string[]; report_path?: string }) => void;
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

export function connectRunWebSocket(id: string, runId: string, handlers: RunHandlers): WebSocket {
  const wsBase = API_BASE.replace(/^http/, 'ws');
  const ws = new WebSocket(`${wsBase}/api/run/${id}/ws?run_id=${runId}`);

  ws.addEventListener('message', (event) => {
    try {
      const msg = JSON.parse(event.data);
      switch (msg.type) {
        case 'step':
          handlers.onStep?.(msg);
          break;
        case 'output':
          handlers.onOutput?.(msg);
          break;
        case 'step_complete':
          handlers.onStepComplete?.(msg);
          break;
        case 'tx':
          handlers.onTx?.(msg);
          break;
        case 'error':
          handlers.onError?.(msg);
          break;
        case 'complete':
          handlers.onComplete?.(msg);
          break;
      }
    } catch {
      // ignore malformed messages
    }
  });

  return ws;
}
