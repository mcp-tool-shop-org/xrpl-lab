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
}

export interface ModuleDetail extends ModuleSummary {
  prerequisites: string[];
  steps: string[];
  artifacts: string[];
}

export interface Status {
  version: string;
  wallet_configured: boolean;
  network: string;
  modules_completed: number;
  modules_total: number;
  last_run?: {
    module: string;
    timestamp: string;
    success: boolean;
  };
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
  id: string;
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
