/**
 * API type definitions — mirrors xrpl_lab/api/schemas.py exactly.
 * DO NOT edit these interfaces without updating the Python models first.
 * Drift is caught by tests/test_schema_drift.py.
 */

/**
 * Base URL for the xrpl-lab API — the SINGLE source of truth (F-cb775026).
 * Previously this constant was copy-pasted verbatim into 10 files (this one
 * plus DashboardLayout.astro and every page under site/src/pages/app/**), so
 * changing the port meant editing 10 places and inevitably drifting. Every
 * caller now imports this constant — or, better, one of the typed fetch*
 * functions below, which use it internally — instead of declaring its own
 * copy.
 *
 * Configurable at BUILD time via the public env var PUBLIC_XRPL_LAB_API
 * (Astro/Vite inlines `PUBLIC_`-prefixed vars into the client bundle — see
 * https://docs.astro.build/en/guides/environment-variables/). Defaults to
 * the port `xrpl-lab serve` binds by default when unset.
 *
 * IMPORTANT: this default is only ever reachable from a loopback-family
 * origin. site/astro.config.mjs builds ALL of app/** (including this file's
 * consumers) into the GitHub Pages-hosted copy of the dashboard, which runs
 * on https://mcp-tool-shop-org.github.io — an origin the backend's CORS +
 * WebSocket origin allow-list (xrpl_lab/api/runner_ws.py _ALLOWED_ORIGINS)
 * can never include. So on that hosted origin, this URL is unreachable no
 * matter what the visitor runs locally. See isLocalOrigin() below and
 * hostedPreviewMessage() in ./dashboard-ui for the honest messaging that
 * covers this case instead of implying a refresh will help.
 */
export const API_BASE: string =
  (import.meta.env.PUBLIC_XRPL_LAB_API as string | undefined) || 'http://localhost:8321';

/**
 * True when the page's own origin is loopback-family (localhost / 127.0.0.1 /
 * the IPv6 loopback). `xrpl-lab serve` always mounts the dashboard on a
 * loopback-family origin (or is proxied to one via the Astro dev server on
 * :4321/:3000); a non-loopback origin is a static host — the GitHub
 * Pages-hosted copy, in practice — which can never reach API_BASE regardless
 * of what is running locally (see the CORS note on API_BASE above). Returns
 * true outside the browser (SSR/build) so build-time evaluation defaults to
 * the common case rather than false-alarming.
 */
export function isLocalOrigin(): boolean {
  if (typeof window === 'undefined') return true;
  const h = window.location.hostname;
  return h === 'localhost' || h === '127.0.0.1' || h === '::1';
}

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
    // F-ec3beb79: tag the status so callers can distinguish "server responded
    // with an error" (HTTP 4xx/5xx) from "couldn't reach the server at all"
    // (TypeError) — mirrors the httpStatus-tagging every page already does by
    // hand around its own inline fetches, so migrating a page to call these
    // typed functions instead doesn't lose that distinction.
    const e = new Error(`API ${path} returned ${res.status}: ${res.statusText}`);
    (e as any).httpStatus = res.status;
    throw e;
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
  // FT-002 — on-ledger verification status of a COMPLETED module. False when the
  // module's verify step failed on-ledger; True (default) for a proven or a
  // not-completed module. Lets the dashboard flag a completed-but-unverified
  // module instead of an all-green "done" that proof-verify would contradict.
  verified: boolean;
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
  // FT-002 — True iff every completed module passed its on-ledger verification.
  // False when a completed module's verify step failed; the dashboard shows an
  // "unverified" indicator so an all-green status can't mask a failed proof.
  all_verified: boolean;
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
  // F-e4e193c5: present on the Python VerifyResponse model (schemas.py) since
  // the FT-002 simulated-mode work but missing here until now — verify.astro
  // reads both at runtime (r.simulated drives the SIMULATED banner,
  // r.all_verified === false drives the UNVERIFIED banner) but only compiled
  // because that call site typed its param `any`, so the compiler never got
  // the chance to flag them as absent from this interface.
  simulated: boolean;
  all_verified: boolean;
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
  const res = await fetchWithTimeout(`${API_BASE}/api/runs/${encodeURIComponent(runId)}`, {
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
