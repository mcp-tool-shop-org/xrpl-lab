const API_BASE = 'http://localhost:8321';

async function request<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API ${path} returned ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export interface ModuleSummary {
  id: string;
  title: string;
  level: 'beginner' | 'intermediate' | 'advanced';
  time_estimate: string;
  completed: boolean;
  description?: string;
  checks: string[];
  requires: string[];
  produces: string[];
}

export interface ModuleDetail extends ModuleSummary {
  checks: string[];
  prerequisites: string[];
  steps: string[];
  artifacts: string[];
}

export interface Status {
  wallet_configured: boolean;
  wallet_address: string | null;
  workspace: string;
  modules_completed: number;
  modules_total: number;
  last_run: {
    module: string;
    timestamp: string;
    success: boolean;
  } | null;
}

export interface DoctorResult {
  overall: 'healthy' | 'warning' | 'error';
  checks: Array<{
    name: string;
    status: 'ok' | 'warn' | 'fail';
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
  const res = await fetch(`${API_BASE}/api/run/${id}?dry_run=${dryRun}`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error(`Run API returned ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<RunResult>;
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
