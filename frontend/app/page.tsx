"use client";

import { useMemo, useState, useEffect } from "react";
import useSWR from "swr";

import { JobCard } from "@/components/JobCard";
import { JobTimeline } from "@/components/JobTimeline";
import { StatPill } from "@/components/StatPill";
import {
  createJobs,
  deleteJob,
  fetchJobEvents,
  fetchJobs,
  fetchSettings,
  fetchTranscript,
  fetchTranscripts,
  fetchTranscriptVersion,
  deleteTranscriptVersion,
  rerunJob,
  cancelJob,
  uploadFile,
  uploadChunked,
  getMediaUrl,
  getTranscriptUrl,
  previewFormats
} from "@/lib/api";
import type { DownloadFormatOption, JobStatus, TranscriptVersion } from "@/lib/types";

const REFRESH_INTERVAL = 2500;

const statusLabels: Record<JobStatus, string> = {
  queued: "Queued",
  downloading: "Downloading",
  downloaded: "Downloaded",
  transcribing: "Transcribing",
  completed: "Completed",
  failed: "Failed",
  canceled: "Canceled"
};

const AUDIO_EXTENSIONS = new Set([
  ".mp3",
  ".m4a",
  ".aac",
  ".wav",
  ".ogg",
  ".opus",
  ".flac"
]);

function formatBytes(bytes?: number | null) {
  if (!bytes) return "Unknown size";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

function formatDuration(seconds?: number | null) {
  if (!seconds) return "Unknown duration";
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.floor(seconds % 60);
  return `${minutes}m ${remaining}s`;
}

function isAudioFile(path?: string | null) {
  if (!path) return false;
  const lower = path.toLowerCase();
  const ext = lower.slice(lower.lastIndexOf("."));
  return AUDIO_EXTENSIONS.has(ext);
}

function formatOptionLabel(option: DownloadFormatOption) {
  const parts = [
    option.format_id,
    option.ext?.toUpperCase() ?? "unknown",
    option.resolution ?? option.format_note ?? ""
  ].filter(Boolean);
  const size = formatBytes(option.filesize ?? option.filesize_approx ?? undefined);
  const codecs = [option.vcodec, option.acodec]
    .filter((codec) => codec && codec !== "none")
    .join(" + ");
  return `${parts.join(" · ")} · ${size}${codecs ? ` · ${codecs}` : ""}`;
}

export default function HomePage() {
  const { data, error, isLoading, mutate } = useSWR("jobs", fetchJobs, {
    refreshInterval: REFRESH_INTERVAL
  });
  const { data: settings } = useSWR("settings", fetchSettings);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [previewedUrl, setPreviewedUrl] = useState<string | null>(null);
  const [formatOptions, setFormatOptions] = useState<DownloadFormatOption[]>([]);
  const [selectedFormatId, setSelectedFormatId] = useState("best");
  const [previewMeta, setPreviewMeta] = useState<{
    title?: string | null;
    uploader?: string | null;
    duration?: number | null;
  } | null>(null);
  const [previewState, setPreviewState] = useState<{
    status: "idle" | "loading" | "success" | "error";
    message?: string;
  }>({ status: "idle" });
  const [submitState, setSubmitState] = useState<{
    status: "idle" | "loading" | "success" | "error";
    message?: string;
  }>({ status: "idle" });
  const [dragOver, setDragOver] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [showVersions, setShowVersions] = useState(false);
  const [versions, setVersions] = useState<TranscriptVersion[]>([]);
  const [deleteOpts, setDeleteOpts] = useState({ purgeMedia: false, purgeTranscript: false });

  const jobs = useMemo(() => data?.jobs ?? [], [data]);
  const selectedJob = jobs.find((job) => job.id === selectedJobId) ?? jobs[0];

  const { data: events } = useSWR(
    selectedJob?.id ? ["events", selectedJob.id] : null,
    () => fetchJobEvents(selectedJob!.id),
    { refreshInterval: REFRESH_INTERVAL }
  );

  const { data: transcript, error: transcriptError, isLoading: transcriptLoading } = useSWR(
    selectedJob?.transcript_path ? ["transcript", selectedJob.id] : null,
    () => fetchTranscript(selectedJob!.id),
    { refreshInterval: selectedJob?.status === "completed" ? 0 : REFRESH_INTERVAL }
  );

  useEffect(() => {
    if (previewedUrl && previewedUrl !== url) {
      setPreviewedUrl(null);
      setFormatOptions([]);
      setSelectedFormatId("best");
      setPreviewMeta(null);
      setPreviewState({ status: "idle" });
    }
  }, [previewedUrl, url]);

  const stats = useMemo(() => {
    const total = jobs.length;
    const active = jobs.filter((job) => ["downloading", "transcribing"].includes(job.status))
      .length;
    const completed = jobs.filter((job) => job.status === "completed").length;
    const failed = jobs.filter((job) => job.status === "failed").length;
    return { total, active, completed, failed };
  }, [jobs]);

  const cookiesStatus = settings?.cookies_configured
    ? "Enabled"
    : settings?.cookies_path
      ? "Missing file"
      : "Not configured";

  const mediaUrl = selectedJob?.download_path ? getMediaUrl(selectedJob.id) : null;
  const transcriptUrl = selectedJob?.transcript_path ? getTranscriptUrl(selectedJob.id) : null;
  const showAudioPlayer = isAudioFile(selectedJob?.download_path);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!url.trim()) return;

    setSubmitState({ status: "loading" });
    try {
      const formatId = selectedFormatId === "best" ? null : selectedFormatId;
      const response = await createJobs(url.trim(), formatId);
      setSubmitState({ status: "success", message: response.message });
      setUrl("");
      setSelectedFormatId("best");
      setPreviewedUrl(null);
      setFormatOptions([]);
      setPreviewMeta(null);
      setPreviewState({ status: "idle" });
      mutate();
    } catch (err) {
      setSubmitState({ status: "error", message: (err as Error).message });
    }
  };

  const handlePreview = async () => {
    if (!url.trim()) return;
    setPreviewState({ status: "loading" });
    try {
      const preview = await previewFormats(url.trim());
      setPreviewedUrl(url.trim());
      setFormatOptions(preview.formats);
      setPreviewMeta({
        title: preview.title,
        uploader: preview.uploader,
        duration: preview.duration
      });
      setPreviewState({ status: "success" });
    } catch (err) {
      setPreviewState({ status: "error", message: (err as Error).message });
    }
  };

  const handleRemove = async (jobId: string) => {
    const opts = { purgeMedia: deleteOpts.purgeMedia, purgeTranscript: deleteOpts.purgeTranscript };
    const confirmRemove = window.confirm(`Remove job? Media:${opts.purgeMedia} Transcript:${opts.purgeTranscript}`);
    if (!confirmRemove) return;
    try {
      await deleteJob(jobId, opts);
      if (selectedJobId === jobId) setSelectedJobId(null);
      mutate();
    } catch (err) {
      setSubmitState({ status: "error", message: (err as Error).message });
    }
  };

  const handleRerun = async (jobId: string) => {
    try { await rerunJob(jobId); mutate(); setSubmitState({ status: "success", message: "Rerun queued" }); } catch (err) { setSubmitState({ status: "error", message: (err as Error).message }); }
  };
  const handleCancel = async (jobId: string) => {
    try { await cancelJob(jobId); mutate(); } catch (err) { setSubmitState({ status: "error", message: (err as Error).message }); }
  };
  const handleUpload = async (file: File) => {
    try {
      setSubmitState({ status: "loading", message: "Uploading..." });
      if (file.size > 5*1024*1024) {
        await uploadChunked(file, (pct)=>setUploadProgress(pct));
      } else {
        await uploadFile(file);
      }
      setSubmitState({ status: "success", message: "Upload queued for pt-BR translation" });
      setUploadProgress(null);
      mutate();
    } catch (err) { setSubmitState({ status: "error", message: (err as Error).message }); setUploadProgress(null); }
  };
  const openVersions = async (jobId: string) => {
    try { const v = await fetchTranscripts(jobId); setVersions(v); setShowVersions(true); } catch (err) { setSubmitState({ status: "error", message: (err as Error).message }); }
  };

  return (
    <div className="page">
      <header className="hero">
        <div>
          <p className="hero__eyebrow">transcribeme — pt-BR</p>
          <h1 className="hero__title">
            transcribeme: queue any YouTube / mp4 link or mp4/mp3 file — auto-translate to pt-BR via faster-whisper small (CPU)
          </h1>
          <p className="hero__subtitle">
            Paste URL (YouTube or direct mp4/mp3) or drop file. Unlimited length auto-split. FIFO 1-concurrency on ZimaOS.
          </p>
        </div>
        <form className="hero__form" onSubmit={handleSubmit} onDragOver={(e)=>{e.preventDefault(); setDragOver(true);}} onDragLeave={()=>setDragOver(false)} onDrop={async (e)=>{e.preventDefault(); setDragOver(false); const f=e.dataTransfer.files?.[0]; if(f) await handleUpload(f);}}>
          <label className="input-label" htmlFor="url">
            YouTube / Direct URL or file (mp4, mp3) — drag & drop supported
          </label>
          <div className="input-row">
            <input
              id="url"
              className="input"
              placeholder="https://www.youtube.com/watch?v=... or https://.../video.mp4"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
            />
            <button className="button" type="submit" disabled={submitState.status === "loading"}>
              {submitState.status === "loading" ? "Queueing..." : "Add to queue"}
            </button>
          </div>
          <div className={`drop-zone ${dragOver ? "active" : ""}`} onClick={()=>document.getElementById("file-input")?.click()} style={{border:"1px dashed #ccc", padding:"12px", textAlign:"center", marginTop:"8px", cursor:"pointer"}}>
            {uploadProgress !== null ? `Uploading ${uploadProgress}%` : "Drag & drop mp4/mp3 here or click to select (chunked 5MB)"}
            <input id="file-input" type="file" accept=".mp4,.mp3" style={{display:"none"}} onChange={async (e)=>{ const f=e.target.files?.[0]; if(f) await handleUpload(f); e.target.value=""; }} />
          </div>
          <div className="format-row">
            <button
              type="button"
              className="button secondary"
              onClick={handlePreview}
              disabled={!url.trim() || previewState.status === "loading"}
            >
              {previewState.status === "loading" ? "Checking..." : "Check formats"}
            </button>
            <div className="select-stack">
              <label className="select-label" htmlFor="format">
                Download format
              </label>
              <select
                id="format"
                className="select"
                value={selectedFormatId}
                onChange={(event) => setSelectedFormatId(event.target.value)}
                disabled={!formatOptions.length}
              >
                <option value="best">Default (best)</option>
                {formatOptions.map((option) => (
                  <option key={option.format_id} value={option.format_id}>
                    {formatOptionLabel(option)}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {previewMeta && (
            <div className="preview-meta">
              <span className="preview-title">{previewMeta.title ?? "Untitled video"}</span>
              <span className="preview-subtitle">
                {previewMeta.uploader ?? "Unknown uploader"} · {formatDuration(previewMeta.duration)}
              </span>
            </div>
          )}
          {previewState.status === "error" && previewState.message && (
            <p className="form-message error">{previewState.message}</p>
          )}
          {submitState.message && (
            <p className={`form-message ${submitState.status}`}>
              {submitState.message}
            </p>
          )}
          <div className="form-status">
            <span className={`status-chip ${settings?.cookies_configured ? "enabled" : "disabled"}`}>Cookies: {cookiesStatus}</span>
            <span style={{marginLeft:"8px"}}>Model: small cpu int8 → pt-BR (translate)</span>
          </div>
        </form>
      </header>

      <section className="stats">
        <StatPill label="Total jobs" value={stats.total} />
        <StatPill label="Active" value={stats.active} />
        <StatPill label="Completed" value={stats.completed} />
        <StatPill label="Failed" value={stats.failed} />
        <StatPill label="Cookies" value={cookiesStatus} />
      </section>

      <main className="grid">
        <section className="panel">
          <div className="panel-header">
            <h2>Queue</h2>
            <span className="panel-meta">Polling every 2.5s — FIFO 1 at a time</span>
          </div>
          <div style={{display:"flex", gap:"8px", marginBottom:"8px"}}>
            <label><input type="checkbox" checked={deleteOpts.purgeMedia} onChange={e=>setDeleteOpts(s=>({...s, purgeMedia:e.target.checked}))}/> purge media</label>
            <label><input type="checkbox" checked={deleteOpts.purgeTranscript} onChange={e=>setDeleteOpts(s=>({...s, purgeTranscript:e.target.checked}))}/> purge transcript</label>
          </div>
          {isLoading && <p className="panel-state">Loading queue...</p>}
          {error && <p className="panel-state error">Failed to load queue.</p>}
          {!isLoading && !jobs.length && (
            <div className="panel-empty">
              <h3>No jobs yet</h3>
              <p>Add a YouTube URL to kick off the first transcription.</p>
            </div>
          )}
          <div className="job-list">
            {jobs.map((job) => (
              <JobCard
                key={job.id}
                job={job}
                isActive={selectedJob?.id === job.id}
                onSelect={setSelectedJobId}
                onRemove={handleRemove}
              />
            ))}
          </div>
        </section>

        <section className="panel detail">
          <div className="panel-header">
            <h2>Job detail</h2>
            {selectedJob && <span className={`status-pill status-${selectedJob.status}`}>{statusLabels[selectedJob.status]}{selectedJob.source_lang ? ` · ${selectedJob.source_lang}→pt-BR` : ""}</span>}
            {selectedJob && <div style={{display:"flex", gap:"6px"}}>
              <button className="button secondary" onClick={()=>openVersions(selectedJob.id)}>Versions</button>
              <button className="button secondary" onClick={()=>handleRerun(selectedJob.id)}>Rerun</button>
              {["queued","downloading"].includes(selectedJob.status) && <button className="button secondary" onClick={()=>handleCancel(selectedJob.id)}>Cancel</button>}
            </div>}
          </div>
          {selectedJob ? (
            <div className="detail-body">
              <div className="detail-summary">
                <h3>{selectedJob.title ?? "Untitled video"}</h3>
                <p>{selectedJob.uploader ?? selectedJob.source_url}</p>
              </div>
              {selectedJob.error && (
                <div className="detail-error">
                  <strong>Last error</strong>
                  <p>{selectedJob.error}</p>
                </div>
              )}
              <div className="detail-grid">
                <div>
                  <span className="detail-label">Progress</span>
                  <span className="detail-value">{Math.round(selectedJob.progress)}%</span>
                </div>
                <div>
                  <span className="detail-label">Job ID</span>
                  <span className="detail-value mono">{selectedJob.id.slice(0, 12)}</span>
                </div>
                <div>
                  <span className="detail-label">Batch</span>
                  <span className="detail-value mono">
                    {selectedJob.batch_id ? selectedJob.batch_id.slice(0, 12) : "-"}
                  </span>
                </div>
                <div>
                  <span className="detail-label">Source</span>
                  <span className="detail-value mono">
                    {selectedJob.video_url ?? selectedJob.source_url}
                  </span>
                </div>
                <div>
                  <span className="detail-label">Format</span>
                  <span className="detail-value">{selectedJob.requested_format ?? "best"}</span>
                </div>
              </div>
              <div className="detail-media">
                <div className="media-panel">
                  <div className="media-header">
                    <h4>Media</h4>
                    {mediaUrl && (
                      <a className="link-button" href={mediaUrl} target="_blank" rel="noreferrer">
                        Open file
                      </a>
                    )}
                  </div>
                  {mediaUrl ? (
                    showAudioPlayer ? (
                      <audio className="media-player" controls src={mediaUrl} />
                    ) : (
                      <video className="media-player" controls src={mediaUrl} />
                    )
                  ) : (
                    <div className="media-empty">No media yet.</div>
                  )}
                </div>
                <div className="media-panel transcript-panel">
                  <div className="media-header">
                    <h4>Transcript</h4>
                    {transcriptUrl && (
                      <a
                        className="link-button"
                        href={transcriptUrl}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open text
                      </a>
                    )}
                  </div>
                  {transcriptLoading && <p className="panel-state">Loading transcript...</p>}
                  {transcriptError && (
                    <p className="panel-state error">Transcript not available yet.</p>
                  )}
                  {transcript ? (
                    <pre className="transcript-viewer">{transcript}</pre>
                  ) : (
                    !transcriptLoading &&
                    !transcriptError && <div className="media-empty">No transcript yet.</div>
                  )}
                </div>
              </div>
              <div className="detail-events">
                <h4>Timeline</h4>
                <JobTimeline events={events ?? []} />
              </div>
            </div>
          ) : (
            <div className="panel-empty">
              <h3>Select a job</h3>
              <p>Pick a queue item to see its progress and timeline.</p>
            </div>
          )}
          {showVersions && (
            <div style={{position:"fixed", inset:0, background:"rgba(0,0,0,0.5)", display:"flex", alignItems:"center", justifyContent:"center", zIndex:1000}} onClick={()=>setShowVersions(false)}>
              <div style={{background:"white", padding:"16px", borderRadius:"8px", minWidth:"400px", maxHeight:"80vh", overflowY:"auto"}} onClick={e=>e.stopPropagation()}>
                <h3>Transcriptions — {selectedJob?.id.slice(0,8)}</h3>
                {versions.length===0 ? <p>No versions yet</p> : versions.map(v=>(
                  <div key={v.id} style={{display:"flex", justifyContent:"space-between", alignItems:"center", borderBottom:"1px solid #eee", padding:"6px 0"}}>
                    <span>v{v.version} — {v.source_lang ?? "?"}→pt-BR — {v.model_name} — {new Date(v.created_at).toLocaleString()}</span>
                    <span style={{display:"flex", gap:"6px"}}>
                      <a className="link-button" href={`${process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"}/jobs/${v.job_id}/transcript/${v.version}`} target="_blank" rel="noreferrer">View</a>
                      <button className="button secondary" onClick={async()=>{ await deleteTranscriptVersion(v.job_id, v.version); const nv=await fetchTranscripts(v.job_id); setVersions(nv); }}>Delete</button>
                    </span>
                  </div>
                ))}
                <button className="button" onClick={()=>setShowVersions(false)} style={{marginTop:"12px"}}>Close</button>
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
