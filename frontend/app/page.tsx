"use client";

import { useMemo, useState, useEffect } from "react";
import useSWR from "swr";
import * as Dialog from "@radix-ui/react-dialog";

import { JobCard } from "@/components/JobCard";
import { JobTimeline } from "@/components/JobTimeline";
import {
  createJobs,
  deleteJob,
  fetchJobEvents,
  fetchJobs,
  fetchTranscript,
  fetchTranscripts,
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

const AUDIO_EXTENSIONS = new Set([".mp3",".m4a",".aac",".wav",".ogg",".opus",".flac"]);

function formatBytes(bytes?: number | null) {
  if (!bytes) return "Unknown"; const units=["B","KB","MB","GB"]; let v=bytes, i=0; while(v>=1024&&i<units.length-1){v/=1024;i++} return `${v.toFixed(1)} ${units[i]}`;
}
function formatDuration(s?: number | null){ if(!s) return "—"; const m=Math.floor(s/60), r=Math.floor(s%60); return `${m}m ${r}s`; }
function isAudioFile(p?: string | null){ if(!p) return false; const e=p.toLowerCase().slice(p.lastIndexOf(".")); return AUDIO_EXTENSIONS.has(e); }
function formatOptionLabel(o: DownloadFormatOption){ const parts=[o.format_id,o.ext?.toUpperCase()??"unknown",o.resolution??o.format_note??""].filter(Boolean); const size=formatBytes(o.filesize??o.filesize_approx??undefined); const codecs=[o.vcodec,o.acodec].filter(c=>c&&c!=="none").join(" + "); return `${parts.join(" · ")} · ${size}${codecs?` · ${codecs}`:""}`; }

export default function HomePage(){
  const { data, error, isLoading, mutate } = useSWR("jobs", fetchJobs, { refreshInterval: REFRESH_INTERVAL });
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [previewedUrl, setPreviewedUrl] = useState<string | null>(null);
  const [formatOptions, setFormatOptions] = useState<DownloadFormatOption[]>([]);
  const [selectedFormatId, setSelectedFormatId] = useState("best");
  const [previewMeta, setPreviewMeta] = useState<{title?:string|null,uploader?:string|null,duration?:number|null}|null>(null);
  const [previewState, setPreviewState] = useState<{status:"idle"|"loading"|"success"|"error",message?:string}>({status:"idle"});
  const [submitState, setSubmitState] = useState<{status:"idle"|"loading"|"success"|"error",message?:string}>({status:"idle"});
  const [dragOver, setDragOver] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number|null>(null);
  const [showVersions, setShowVersions] = useState(false);
  const [versions, setVersions] = useState<TranscriptVersion[]>([]);
  const [deleteOpts, setDeleteOpts] = useState({ purgeMedia:false, purgeTranscript:false });

  const jobs = useMemo(()=>data?.jobs??[],[data]);
  const selectedJob = jobs.find(j=>j.id===selectedJobId) ?? jobs[0];
  const { data: events } = useSWR(selectedJob?.id?["events",selectedJob.id]:null, ()=>fetchJobEvents(selectedJob!.id), { refreshInterval: REFRESH_INTERVAL });
  const { data: transcript, error: transcriptError, isLoading: transcriptLoading } = useSWR(selectedJob?.transcript_path?["transcript",selectedJob.id]:null, ()=>fetchTranscript(selectedJob!.id), { refreshInterval: selectedJob?.status==="completed"?0:REFRESH_INTERVAL });
  useEffect(()=>{ if(previewedUrl && previewedUrl!==url){ setPreviewedUrl(null); setFormatOptions([]); setSelectedFormatId("best"); setPreviewMeta(null); setPreviewState({status:"idle"});} },[previewedUrl,url]);
  const stats = useMemo(()=>{ const total=jobs.length; const active=jobs.filter(j=>["downloading","transcribing"].includes(j.status)).length; const completed=jobs.filter(j=>j.status==="completed").length; const failed=jobs.filter(j=>j.status==="failed").length; return {total,active,completed,failed}; },[jobs]);
  const mediaUrl = selectedJob?.download_path?getMediaUrl(selectedJob.id):null;
  const transcriptUrl = selectedJob?.transcript_path?getTranscriptUrl(selectedJob.id):null;
  const showAudioPlayer = isAudioFile(selectedJob?.download_path);

  const handleSubmit = async (e:React.FormEvent)=>{ e.preventDefault(); if(!url.trim()) return; setSubmitState({status:"loading"}); try{ const fid=selectedFormatId==="best"?null:selectedFormatId; const r=await createJobs(url.trim(),fid); setSubmitState({status:"success",message:r.message}); setUrl(""); setSelectedFormatId("best"); setPreviewedUrl(null); setFormatOptions([]); setPreviewMeta(null); setPreviewState({status:"idle"}); mutate(); }catch(err){ setSubmitState({status:"error",message:(err as Error).message}); } };
  const handlePreview = async ()=>{ if(!url.trim())return; setPreviewState({status:"loading"}); try{ const p=await previewFormats(url.trim()); setPreviewedUrl(url.trim()); setFormatOptions(p.formats); setPreviewMeta({title:p.title,uploader:p.uploader,duration:p.duration}); setPreviewState({status:"success"}); }catch(err){ setPreviewState({status:"error",message:(err as Error).message}); } };
  const handleRemove = async (jid:string)=>{ const opts={purgeMedia:deleteOpts.purgeMedia,purgeTranscript:deleteOpts.purgeTranscript}; if(!window.confirm(`Remove? media:${opts.purgeMedia} transcript:${opts.purgeTranscript}`)) return; try{ await deleteJob(jid,opts); if(selectedJobId===jid) setSelectedJobId(null); mutate(); }catch(err){ setSubmitState({status:"error",message:(err as Error).message}); } };
  const handleRerun = async (jid:string)=>{ try{ await rerunJob(jid); mutate(); setSubmitState({status:"success",message:"Rerun queued"});}catch(err){ setSubmitState({status:"error",message:(err as Error).message}); } };
  const handleCancel = async (jid:string)=>{ try{ await cancelJob(jid); mutate(); }catch(err){ setSubmitState({status:"error",message:(err as Error).message}); } };
  const handleUpload = async (file:File)=>{ try{ setSubmitState({status:"loading",message:"Uploading..."}); if(file.size>5*1024*1024) await uploadChunked(file,(pct)=>setUploadProgress(pct)); else await uploadFile(file); setSubmitState({status:"success",message:"Upload queued → pt-BR"}); setUploadProgress(null); mutate(); }catch(err){ setSubmitState({status:"error",message:(err as Error).message}); setUploadProgress(null); } };
  const openVersions = async (jid:string)=>{ try{ const v=await fetchTranscripts(jid); setVersions(v); setShowVersions(true);}catch(err){ setSubmitState({status:"error",message:(err as Error).message}); } };

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebar__brand">
          <span className="sidebar__eyebrow">ZimaOS · NAS</span>
          <span className="sidebar__title" style={{fontFamily:"var(--font-serif)"}}>transcribeme</span>
          <span className="sidebar__subtitle">Fila FIFO 1× · whisper small int8 → NLLB 600M → pt-BR</span>
        </div>

        <div className="sidebar__section">
          <span className="sidebar__label">Queue</span>
          <div className="stats-tight">
            <div className="stat-tight"><span className="stat-tight__label">Total</span><span className="stat-tight__value">{stats.total}</span></div>
            <div className="stat-tight"><span className="stat-tight__label">Active</span><span className="stat-tight__value">{stats.active}</span></div>
            <div className="stat-tight"><span className="stat-tight__label">Done</span><span className="stat-tight__value">{stats.completed}</span></div>
            <div className="stat-tight"><span className="stat-tight__label">Failed</span><span className="stat-tight__value">{stats.failed}</span></div>
          </div>
          <span className="panel-meta">Polling 2.5s · 280px workbench</span>
        </div>

        <div className="sidebar__section">
          <span className="sidebar__label">Delete options</span>
          <label className="toggle-row"><span>purge media</span><input type="checkbox" checked={deleteOpts.purgeMedia} onChange={e=>setDeleteOpts(s=>({...s,purgeMedia:e.target.checked}))}/></label>
          <label className="toggle-row"><span>purge transcript</span><input type="checkbox" checked={deleteOpts.purgeTranscript} onChange={e=>setDeleteOpts(s=>({...s,purgeTranscript:e.target.checked}))}/></label>
        </div>

        <div className="sidebar__section">
          <span className="sidebar__label">System</span>
          <div style={{display:"flex", gap:8, flexWrap:"wrap"}}>
            <span className="status-chip">small cpu int8</span>
            <span className="status-chip">NLLB 600M</span>
            <span className="status-chip">1.5×</span>
          </div>
        </div>
      </aside>

      <main className="main">
        <div style={{display:"flex", justifyContent:"space-between", alignItems:"baseline"}}>
          <h1 className="wordmark">transcribeme <span>— pt-BR</span></h1>
          <span className="panel-meta">{jobs.length} jobs</span>
        </div>

        <form className="deck-slot" onSubmit={handleSubmit} onDragOver={e=>{e.preventDefault(); setDragOver(true);}} onDragLeave={()=>setDragOver(false)} onDrop={async e=>{e.preventDefault(); setDragOver(false); const f=e.dataTransfer.files?.[0]; if(f) await handleUpload(f);}}>
          <div className={`deck-slot__drop ${dragOver?"active":""}`} onClick={()=>document.getElementById("file-input")?.click()}>
            {uploadProgress!==null?`Uploading ${uploadProgress}%`:"Drop mp4/mp3 here or click — 5MB chunked · YouTube or direct mp4 URL"}
            <input id="file-input" type="file" accept=".mp4,.mp3" style={{display:"none"}} onChange={async e=>{ const f=e.target.files?.[0]; if(f) await handleUpload(f); e.target.value=""; }} />
          </div>
          <div className="input-row">
            <input id="url" className="input" placeholder="https://www.youtube.com/watch?v=... or https://.../video.mp4" value={url} onChange={e=>setUrl(e.target.value)} />
            <button className="button" type="submit" disabled={submitState.status==="loading"}>{submitState.status==="loading"?"Queueing...":"Add to queue"}</button>
          </div>
          <div style={{display:"flex", gap:8, alignItems:"flex-end", flexWrap:"wrap"}}>
            <button type="button" className="button secondary" onClick={handlePreview} disabled={!url.trim()||previewState.status==="loading"}>{previewState.status==="loading"?"Checking...":"Check formats"}</button>
            <select className="select" value={selectedFormatId} onChange={e=>setSelectedFormatId(e.target.value)} disabled={!formatOptions.length} style={{minWidth:200, flex:1}}>
              <option value="best">Default (best)</option>
              {formatOptions.map(o=><option key={o.format_id} value={o.format_id}>{formatOptionLabel(o)}</option>)}
            </select>
          </div>
          {previewMeta && <div style={{fontSize:11, color:"var(--ink-muted)"}}><b style={{color:"var(--ink)"}}>{previewMeta.title??"Untitled"}</b> · {previewMeta.uploader??"Unknown"} · {formatDuration(previewMeta.duration)}</div>}
          {previewState.status==="error"&&previewState.message&&<p className="form-message error">{previewState.message}</p>}
          {submitState.message&&<p className={`form-message ${submitState.status}`}>{submitState.message}</p>}
        </form>

        <div className="grid">
          <section className="panel">
            <div className="panel-header"><h2>Queue</h2><span className="panel-meta">{isLoading?"Loading…":`${jobs.length} total`}</span></div>
            {error && <p className="panel-empty" style={{color:"#e88a7a"}}>Failed to load queue</p>}
            {!isLoading && !jobs.length && <div className="panel-empty"><b>No jobs yet</b><br/>Add YouTube / mp4 link or drop file</div>}
            <div className="job-list">
              {jobs.map(job=> <JobCard key={job.id} job={job} isActive={selectedJob?.id===job.id} onSelect={setSelectedJobId} onRemove={handleRemove} />)}
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <h2>Detail</h2>
              <div style={{display:"flex", gap:6, alignItems:"center"}}>
                {selectedJob && <span className={`status-pill status-${selectedJob.status}`}>{statusLabels[selectedJob.status]}{selectedJob.source_lang?` · ${selectedJob.source_lang}→pt-BR`:""}</span>}
                {selectedJob && <>
                  <button className="button secondary" style={{padding:"6px 10px", fontSize:11}} onClick={()=>openVersions(selectedJob.id)}>Versions</button>
                  <button className="button secondary" style={{padding:"6px 10px", fontSize:11}} onClick={()=>handleRerun(selectedJob.id)}>Rerun</button>
                  {["queued","downloading"].includes(selectedJob.status) && <button className="button secondary" style={{padding:"6px 10px", fontSize:11}} onClick={()=>handleCancel(selectedJob.id)}>Cancel</button>}
                </>}
              </div>
            </div>
            {selectedJob ? (
              <div className="detail-body">
                <div className="detail-summary"><h3>{selectedJob.title??"Untitled"}</h3><p>{selectedJob.uploader??selectedJob.source_url}</p></div>
                {selectedJob.error && <div className="detail-error"><b>Last error</b><p>{selectedJob.error}</p></div>}
                <div className="detail-grid">
                  <div><span className="detail-label">Progress</span><span className="detail-value">{Math.round(selectedJob.progress)}%<div className="vu-bar"><div className="vu-bar__fill" style={{width:`${selectedJob.progress}%`}}/></div></span></div>
                  <div><span className="detail-label">Job ID</span><span className="detail-value mono">{selectedJob.id.slice(0,12)}</span></div>
                  <div><span className="detail-label">Source</span><span className="detail-value mono">{selectedJob.video_url??selectedJob.source_url}</span></div>
                  <div><span className="detail-label">Format</span><span className="detail-value">{selectedJob.requested_format??"best"}</span></div>
                </div>
                <div className="detail-media">
                  <div className="media-panel">
                    <div className="media-header"><h4>Media</h4>{mediaUrl&&<a className="link-button" href={mediaUrl} target="_blank" rel="noreferrer">Open file</a>}</div>
                    {mediaUrl? (showAudioPlayer? <audio className="media-player" controls src={mediaUrl}/>: <video className="media-player" controls src={mediaUrl}/>): <div className="media-empty">No media yet</div>}
                  </div>
                  <div className="media-panel transcript-paper">
                    <div className="media-header"><h4>Transcript — pt-BR</h4>{transcriptUrl&&<a className="link-button" href={transcriptUrl} target="_blank" rel="noreferrer">Open text</a>}</div>
                    <div className="spool-header"><span>SPOOL</span><span>{selectedJob.source_lang?`${selectedJob.source_lang}→pt-BR`:"pt-BR"} · {selectedJob.progress>=100?"READY":"…"}</span></div>
                    {transcriptLoading&&<p style={{fontSize:12, color:"var(--paper-muted)"}}>Loading…</p>}
                    {transcriptError&&<p style={{fontSize:12, color:"#7a1b12"}}>Not available yet</p>}
                    {transcript?<pre className="transcript-viewer">{transcript}</pre>:(!transcriptLoading&&!transcriptError&&<div className="media-empty" style={{color:"var(--paper-muted)", borderColor:"rgba(0,0,0,0.1)"}}>No transcript yet</div>)}
                  </div>
                </div>
                <div><h4 style={{fontSize:12, margin:"0 0 8px"}}>Timeline</h4><JobTimeline events={events??[]} /></div>
              </div>
            ) : <div className="panel-empty">Select a job</div>}
          </section>
        </div>
      </main>

      <Dialog.Root open={showVersions} onOpenChange={setShowVersions}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="dialog-content">
            <Dialog.Title style={{margin:0, fontSize:14, fontWeight:600}}>Transcriptions — {selectedJob?.id.slice(0,8)}</Dialog.Title>
            <div style={{marginTop:12, display:"flex", flexDirection:"column", gap:8}}>
              {versions.length===0? <p style={{fontSize:12, color:"var(--ink-muted)"}}>No versions yet</p> : versions.map(v=>(
                <div key={v.id} style={{display:"flex", justifyContent:"space-between", alignItems:"center", borderBottom:"1px solid var(--stroke-soft)", padding:"8px 0", fontSize:12}}>
                  <span>v{v.version} — {v.source_lang??"?"}→pt-BR — {v.model_name} — {new Date(v.created_at).toLocaleString()}</span>
                  <span style={{display:"flex", gap:6}}>
                    <a className="link-button" href={`${process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"}/jobs/${v.job_id}/transcript/${v.version}`} target="_blank" rel="noreferrer">View</a>
                    <button className="button secondary" style={{padding:"6px 10px", fontSize:11}} onClick={async()=>{ await deleteTranscriptVersion(v.job_id, v.version); const nv=await fetchTranscripts(v.job_id); setVersions(nv); }}>Delete</button>
                  </span>
                </div>
              ))}
            </div>
            <Dialog.Close asChild><button className="button" style={{marginTop:12}}>Close</button></Dialog.Close>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
