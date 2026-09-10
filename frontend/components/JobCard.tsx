import { useEffect, useState } from "react";
import type { Job } from "@/lib/types";

interface JobCardProps {
  job: Job;
  isActive: boolean;
  onSelect: (jobId: string) => void;
  onRemove?: (jobId: string) => void;
}

function formatElapsed(ms: number): string {
  const clamped = Math.max(0, ms);
  const s = Math.floor(clamped / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`;
  return `${m}:${String(sec).padStart(2,"0")}`;
}

function formatTitle(job: Job) {
  if (job.title) return job.title;
  if (job.video_id) return `Video ${job.video_id}`;
  return job.source_url;
}

function formatSubtitle(job: Job) {
  if (job.uploader) return job.uploader;
  if (job.video_url) return job.video_url;
  return job.source_url;
}

function parseISO(s: string | null): number | null {
  if (!s) return null;
  const t = new Date(s.endsWith("Z") || s.includes("+") ? s : s + "Z").getTime();
  return isNaN(t) ? null : t;
}

export function JobCard({ job, isActive, onSelect, onRemove }: JobCardProps) {
  const canRemove = Boolean(onRemove && ["completed","failed","canceled","queued"].includes(job.status));
  const [now, setNow] = useState<number>(Date.now());
  const isProcessing = ["downloading","transcribing"].includes(job.status);
  const startedAt = parseISO(job.started_at);
  useEffect(() => {
    if (!isProcessing || !startedAt) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [isProcessing, startedAt]);
  const elapsedMs = (() => {
    if (!startedAt) return null;
    if (["completed","failed","canceled"].includes(job.status) && job.finished_at) {
      const fin = parseISO(job.finished_at);
      if (fin === null) return null;
      return Math.max(0, fin - startedAt);
    }
    if (isProcessing) return Math.max(0, now - startedAt);
    return null;
  })();

  return (
    <div
      role="button"
      tabIndex={0}
      className={`job-card ${isActive ? "active" : ""}`}
      onClick={() => onSelect(job.id)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(job.id);
        }
      }}
    >
      <div className="job-card__header">
        <span className={`status-pill status-${job.status}`}>{job.status}</span>
        <div className="job-card__actions">
          <span className="job-meta">{(() => { const t = parseISO(job.created_at); return t ? new Date(t).toLocaleString() : new Date(job.created_at).toLocaleString(); })()}</span>
          {canRemove && (
            <button
              type="button"
              className="job-remove"
              onClick={(event) => {
                event.stopPropagation();
                onRemove?.(job.id);
              }}
            >
              Remove
            </button>
          )}
        </div>
      </div>
      <div className="job-title">{formatTitle(job)}</div>
      <div className="job-subtitle">{formatSubtitle(job)}</div>
      <div className="job-progress">
        <div className="job-progress__bar" style={{ width: `${job.progress}%` }} />
      </div>
      <div className="job-progress__meta">
        <span>{Math.round(job.progress)}%{elapsedMs !== null ? ` · ⏱ ${formatElapsed(elapsedMs)}` : ""}</span>
        <span>{job.batch_id ? `Batch ${job.batch_id.slice(0, 8)}` : "Single"}</span>
      </div>
    </div>
  );
}
