export type DashboardKey = "gold" | "forecast";
export type ScriptKey = "gold_links" | "gold_status" | "forecast_links";
export type Job = {
  id: string; kind: "sources" | "data"; target: string;
  status: "queued" | "running" | "completed" | "failed";
  stage: string; error_message?: string | null; completed_at?: string | null;
  results: Partial<Record<ScriptKey, { completed_at: string; message: string }>>;
};
export type FastTrackStatus = {
  enabled: boolean; configured: boolean; active: boolean; source_user: string;
  sources: { updated_at?: string; dashboards: Partial<Record<DashboardKey, { available: boolean; updated_at: string; sha256: string }>>; job?: Job | null };
  data: { updated_at?: string; scripts: Partial<Record<ScriptKey, { completed_at: string }>>; job?: Job | null };
  dashboards: Record<DashboardKey, { label: string; available?: boolean; url?: string | null; pending_sources: boolean; updated_at?: string; clients?: number; run?: string }>;
};

// In production use the SWA authenticated same-origin gateway. The development backend is separate.
export const fastTrackBaseUrl = ["localhost", "127.0.0.1"].includes(window.location.hostname)
  ? process.env.REACT_APP_BACKEND_URL || "" : "";

export async function readFastTrackStatus(): Promise<FastTrackStatus> {
  return request("/settings");
}

export async function refreshFastTrack(kind: "sources" | "data", target: string): Promise<FastTrackStatus> {
  return request(`/settings/${kind}/refresh`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ target }) });
}

async function request(path: string, options?: RequestInit): Promise<FastTrackStatus> {
  const response = await fetch(`${fastTrackBaseUrl}/api/fast-track${path}`, { credentials: "same-origin", ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof data?.detail === "string" ? data.detail : "Operazione Fast Track non riuscita");
  return data;
}

export function formatUpdate(value?: string | null) {
  if (!value) return "Mai eseguito";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("it-IT");
}
