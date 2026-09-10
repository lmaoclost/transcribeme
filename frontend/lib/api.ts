import type {
  JobEvent,
  JobListResponse,
  PreviewResponse,
  SettingsResponse
} from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function createJobs(
  url: string,
  formatId?: string | null
): Promise<{ batch_id: string; message: string }> {
  const response = await fetch(`${API_BASE}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, format_id: formatId ?? undefined })
  });
  return handleResponse(response);
}

export async function fetchJobs(): Promise<JobListResponse> {
  const response = await fetch(`${API_BASE}/jobs?limit=100`);
  return handleResponse(response);
}

export async function fetchJobEvents(jobId: string): Promise<JobEvent[]> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/events`);
  return handleResponse(response);
}

export async function fetchSettings(): Promise<SettingsResponse> {
  const response = await fetch(`${API_BASE}/settings`);
  return handleResponse(response);
}

export async function previewFormats(url: string): Promise<PreviewResponse> {
  const response = await fetch(`${API_BASE}/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url })
  });
  return handleResponse(response);
}

export async function deleteJob(jobId: string, opts?: { purgeMedia?: boolean; purgeTranscript?: boolean }): Promise<{ job_id: string; message: string }> {
  const params = new URLSearchParams();
  if (opts?.purgeMedia) params.set("purge_media", "true");
  if (opts?.purgeTranscript) params.set("purge_transcript", "true");
  const qs = params.toString() ? `?${params}` : "";
  const response = await fetch(`${API_BASE}/jobs/${jobId}${qs}`, { method: "DELETE" });
  return handleResponse(response);
}

export async function rerunJob(jobId: string): Promise<{ message: string; job_id: string }> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/rerun`, { method: "POST" });
  return handleResponse(response);
}

export async function cancelJob(jobId: string): Promise<{ message: string; job_id: string }> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/cancel`, { method: "POST" });
  return handleResponse(response);
}

export async function fetchTranscripts(jobId: string): Promise<import("@/lib/types").TranscriptVersion[]> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/transcripts`);
  return handleResponse(response);
}

export async function fetchTranscriptVersion(jobId: string, version: number): Promise<string> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/transcript/${version}`);
  if (!response.ok) throw new Error(await response.text());
  return response.text();
}

export async function deleteTranscriptVersion(jobId: string, version: number): Promise<{ message: string }> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/transcript/${version}`, { method: "DELETE" });
  return handleResponse(response);
}

export async function uploadFile(file: File): Promise<{ id: string }> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE}/jobs/upload`, { method: "POST", body: form });
  return handleResponse(response);
}

export async function uploadChunked(file: File, onProgress?: (pct: number) => void): Promise<{ id: string }> {
  const initResp = await fetch(`${API_BASE}/uploads/init?filename=${encodeURIComponent(file.name)}&total_size=${file.size}`, { method: "POST" });
  const { upload_id } = await handleResponse<{ upload_id: string }>(initResp);
  const chunkSize = 5 * 1024 * 1024;
  let offset = 0;
  while (offset < file.size) {
    const chunk = file.slice(offset, Math.min(offset + chunkSize, file.size));
    const buf = await chunk.arrayBuffer();
    await fetch(`${API_BASE}/uploads/${upload_id}`, { method: "PATCH", body: buf, headers: { "Content-Type": "application/octet-stream" } });
    offset += chunkSize;
    if (onProgress) onProgress(Math.min(100, Math.round((offset / file.size) * 100)));
  }
  const completeResp = await fetch(`${API_BASE}/uploads/${upload_id}/complete?filename=${encodeURIComponent(file.name)}`, { method: "POST" });
  return handleResponse(completeResp);
}

export async function fetchTranscript(jobId: string): Promise<string> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/transcript`);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with ${response.status}`);
  }
  return response.text();
}

export function getMediaUrl(jobId: string): string {
  return `${API_BASE}/jobs/${jobId}/media`;
}

export function getTranscriptUrl(jobId: string): string {
  return `${API_BASE}/jobs/${jobId}/transcript`;
}
