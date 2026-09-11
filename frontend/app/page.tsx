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
  fetchSettings,
  updateSettings,
  fetchTranscript,
  fetchTranscripts,
  deleteTranscriptVersion,
  rerunJob,
  cancelJob,
  uploadFile,
  uploadChunked,
  getMediaUrl,
  getTranscriptUrl,
} from "@/lib/api";
import type { JobStatus, TranscriptVersion } from "@/lib/types";

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
function isAudioFile(p?: string | null){ if(!p) return false; const e=p.toLowerCase().slice(p.lastIndexOf(".")); return AUDIO_EXTENSIONS.has(e); }

const MODEL_OPTIONS = [
  { value: "small", label: "small — 1.3GB, 0.7× realtime (default)" },
  { value: "medium", label: "medium — 2.2GB, 0.3× realtime, better pt accuracy" },
  { value: "large-v3", label: "large-v3 — 3GB, slow, best accuracy" },
];

const LANG_OPTIONS = [
  { value: "por_Latn", label: "Português — por_Latn" },
  { value: "eng_Latn", label: "English — eng_Latn" },
  { value: "spa_Latn", label: "Español — spa_Latn" },
  { value: "fra_Latn", label: "Français — fra_Latn" },
  { value: "deu_Latn", label: "Deutsch — deu_Latn" },
  { value: "ita_Latn", label: "Italiano — ita_Latn" },
  { value: "nld_Latn", label: "Nederlands — nld_Latn" },
  { value: "pol_Latn", label: "Polski — pol_Latn" },
  { value: "ron_Latn", label: "Română — ron_Latn" },
  { value: "rus_Cyrl", label: "Русский — rus_Cyrl" },
  { value: "ukr_Cyrl", label: "Українська — ukr_Cyrl" },
  { value: "ell_Grek", label: "Ελληνικά — ell_Grek" },
  { value: "jpn_Jpan", label: "日本語 — jpn_Jpan" },
  { value: "zho_Hans", label: "中文 — zho_Hans" },
  { value: "kor_Hang", label: "한국어 — kor_Hang" },
  { value: "hin_Deva", label: "हिन्दी — hin_Deva" },
  { value: "arb_Arab", label: "العربية — arb_Arab" },
  { value: "heb_Hebr", label: "עברית — heb_Hebr" },
  { value: "tur_Latn", label: "Türkçe — tur_Latn" },
  { value: "vie_Latn", label: "Tiếng Việt — vie_Latn" },
  { value: "ind_Latn", label: "Bahasa Indonesia — ind_Latn" },
  { value: "tha_Thai", label: "ไทย — tha_Thai" },
];

export default function HomePage(){
  const { data, error, isLoading, mutate } = useSWR("jobs", fetchJobs, { refreshInterval: REFRESH_INTERVAL });
  const { data: settings, mutate: mutateSettings } = useSWR("settings", fetchSettings);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [submitState, setSubmitState] = useState<{status:"idle"|"loading"|"success"|"error",message?:string}>({status:"idle"});
  const [dragOver, setDragOver] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number|null>(null);
  const [showVersions, setShowVersions] = useState(false);
  const [versions, setVersions] = useState<TranscriptVersion[]>([]);
  const [deleteOpts, setDeleteOpts] = useState({ purgeMedia:false, purgeTranscript:false });
  const [showOptions, setShowOptions] = useState(false);
  const [optModel, setOptModel] = useState("small");
  const [optLang, setOptLang] = useState("por_Latn");
  const [optSpeed, setOptSpeed] = useState(1.5);
  const [filter, setFilter] = useState<"all"|"processing"|"done"|"failed">("all");

  const jobs = useMemo(()=>data?.jobs??[],[data]);
  const filteredJobs = useMemo(()=>{
    if(filter==="all") return jobs;
    if(filter==="done") return jobs.filter(j=>j.status==="completed");
    if(filter==="failed") return jobs.filter(j=>j.status==="failed");
    return jobs.filter(j=>["queued","downloading","downloaded","transcribing"].includes(j.status));
  },[jobs, filter]);
  const selectedJob = jobs.find(j=>j.id===selectedJobId) ?? jobs[0];
  const { data: events } = useSWR(selectedJob?.id?["events",selectedJob.id]:null, ()=>fetchJobEvents(selectedJob!.id), { refreshInterval: REFRESH_INTERVAL });
  const { data: transcript, error: transcriptError, isLoading: transcriptLoading } = useSWR(selectedJob?.transcript_path?["transcript",selectedJob.id]:null, ()=>fetchTranscript(selectedJob!.id), { refreshInterval: selectedJob?.status==="completed"?0:REFRESH_INTERVAL });

  useEffect(()=>{
    if(settings){
      setOptModel(settings.whisper_model);
      setOptLang(settings.translation_target_lang_code);
      setOptSpeed(settings.transcription_speed);
    }
  },[settings]);

  const handleSubmit = async (e:React.FormEvent)=>{ e.preventDefault(); if(!url.trim()) return; setSubmitState({status:"loading"}); try{ const r=await createJobs(url.trim(), null); setSubmitState({status:"success",message:r.message}); setUrl(""); mutate(); }catch(err){ setSubmitState({status:"error",message:(err as Error).message}); } };
  const handleRemove = async (jid:string)=>{ const opts={purgeMedia:deleteOpts.purgeMedia,purgeTranscript:deleteOpts.purgeTranscript}; if(!window.confirm(`Remove? media:${opts.purgeMedia} transcript:${opts.purgeTranscript}`)) return; try{ await deleteJob(jid,opts); if(selectedJobId===jid) setSelectedJobId(null); mutate(); }catch(err){ setSubmitState({status:"error",message:(err as Error).message}); } };
  const handleRerun = async (jid:string)=>{ try{ await rerunJob(jid); mutate(); setSubmitState({status:"success",message:"Rerun queued"});}catch(err){ setSubmitState({status:"error",message:(err as Error).message}); } };
  const handleCancel = async (jid:string)=>{ try{ await cancelJob(jid); mutate(); }catch(err){ setSubmitState({status:"error",message:(err as Error).message}); } };
  const handleUpload = async (file:File)=>{ try{ setSubmitState({status:"loading",message:"Uploading..."}); if(file.size>5*1024*1024) await uploadChunked(file,(pct)=>setUploadProgress(pct)); else await uploadFile(file); setSubmitState({status:"success",message:"Upload queued → pt-BR"}); setUploadProgress(null); mutate(); }catch(err){ setSubmitState({status:"error",message:(err as Error).message}); setUploadProgress(null); } };
  const openVersions = async (jid:string)=>{ try{ const v=await fetchTranscripts(jid); setVersions(v); setShowVersions(true);}catch(err){ setSubmitState({status:"error",message:(err as Error).message}); } };
  const handleSaveOptions = async ()=>{
    try{
      await updateSettings({ whisper_model: optModel, translation_target_lang_code: optLang, transcription_speed: optSpeed });
      mutateSettings();
      setShowOptions(false);
      setSubmitState({status:"success", message:"Options saved"});
    } catch(err){ setSubmitState({status:"error", message:(err as Error).message}); }
  };

  const mediaUrl = selectedJob?.download_path?getMediaUrl(selectedJob.id):null;
  const transcriptUrl = selectedJob?.transcript_path?getTranscriptUrl(selectedJob.id):null;
  const showAudioPlayer = isAudioFile(selectedJob?.download_path);

  return (
    <div className="shell">
      <main className="main">
        <div style={{display:"flex", justifyContent:"space-between", alignItems:"center"}}>
          <h1 className="wordmark">transcribeme <span>— {optLang.startsWith("por")?"pt-BR":optLang}</span></h1>
          <div style={{display:"flex", gap:8, alignItems:"center"}}>
            <span className="panel-meta">{jobs.length} jobs · {settings?.whisper_model ?? "small"} · {optSpeed}×</span>
            <Dialog.Root open={showOptions} onOpenChange={setShowOptions}>
              <Dialog.Trigger asChild><button className="button secondary" style={{padding:"8px 12px"}}>⚙ Options</button></Dialog.Trigger>
              <Dialog.Portal>
                <Dialog.Overlay className="dialog-overlay" />
                <Dialog.Content className="dialog-content">
                  <Dialog.Title style={{margin:0, fontSize:14, fontWeight:600}}>Options</Dialog.Title>
                  <div style={{display:"flex", flexDirection:"column", gap:14, marginTop:12}}>
                    <label style={{display:"flex", flexDirection:"column", gap:6}}>
                      <span className="detail-label">Default model</span>
                      <select className="select" value={optModel} onChange={e=>setOptModel(e.target.value)}>
                        {MODEL_OPTIONS.map(o=><option key={o.value} value={o.value}>{o.label}</option>)}
                      </select>
                    </label>
                    <label style={{display:"flex", flexDirection:"column", gap:6}}>
                      <span className="detail-label">Output language (.txt)</span>
                      <select className="select" value={optLang} onChange={e=>setOptLang(e.target.value)}>
                        {LANG_OPTIONS.map(o=><option key={o.value+o.label} value={o.value}>{o.label}</option>)}
                      </select>
                    </label>
                    <label style={{display:"flex", flexDirection:"column", gap:6}}>
                      <span className="detail-label">Transcription speed</span>
                      <select className="select" value={String(optSpeed)} onChange={e=>setOptSpeed(parseFloat(e.target.value))}>
                        <option value="1.0">1.0× — max accuracy</option>
                        <option value="1.5">1.5× — 33% faster (default)</option>
                      </select>
                    </label>
                    <div style={{display:"flex", flexDirection:"column", gap:8}}>
                      <span className="detail-label">Delete behavior</span>
                      <label className="toggle-row"><span>purge media by default</span><input type="checkbox" checked={deleteOpts.purgeMedia} onChange={e=>setDeleteOpts(s=>({...s,purgeMedia:e.target.checked}))}/></label>
                      <label className="toggle-row"><span>purge transcript by default</span><input type="checkbox" checked={deleteOpts.purgeTranscript} onChange={e=>setDeleteOpts(s=>({...s,purgeTranscript:e.target.checked}))}/></label>
                    </div>
                  </div>
                  <div style={{display:"flex", gap:8, justifyContent:"flex-end", marginTop:16}}>
                    <Dialog.Close asChild><button className="button secondary">Cancel</button></Dialog.Close>
                    <button className="button" onClick={handleSaveOptions}>Save</button>
                  </div>
                </Dialog.Content>
              </Dialog.Portal>
            </Dialog.Root>
          </div>
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
          {submitState.message&&<p className={`form-message ${submitState.status}`}>{submitState.message}</p>}
        </form>

        <div className="grid">
          <section className="panel">
            <div className="panel-header">
              <h2>Queue</h2>
              <span className="panel-meta">{isLoading?"Loading…":`${filteredJobs.length}/${jobs.length}`}</span>
            </div>
            <div role="tablist" style={{display:"flex", gap:6, marginBottom:12, flexWrap:"wrap"}}>
              {(["all","processing","done","failed"] as const).map(f=>{
                const labels={all:`All (${jobs.length})`, processing:`Processing (${jobs.filter(j=>["queued","downloading","downloaded","transcribing"].includes(j.status)).length})`, done:`Done (${jobs.filter(j=>j.status==="completed").length})`, failed:`Failed (${jobs.filter(j=>j.status==="failed").length})`} as const;
                const active = filter===f;
                return <button key={f} role="tab" aria-selected={active} onClick={()=>setFilter(f)} className={`button ${active?"":"secondary"}`} style={{padding:"6px 10px", fontSize:11, borderRadius:999, background: active?"var(--accent)":undefined, color: active?"white":undefined}}>{labels[f]}</button>;
              })}
            </div>
            {error && <p className="panel-empty" style={{color:"#e88a7a"}}>Failed to load queue</p>}
            {!isLoading && !jobs.length && <div className="panel-empty"><b>No jobs yet</b><br/>Add YouTube / mp4 link or drop file</div>}
            {!isLoading && jobs.length>0 && filteredJobs.length===0 && <div className="panel-empty">No {filter} jobs</div>}
            <div className="job-list">
              {filteredJobs.map(job=> <JobCard key={job.id} job={job} isActive={selectedJob?.id===job.id} onSelect={setSelectedJobId} onRemove={handleRemove} />)}
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <h2>Detail</h2>
              <div style={{display:"flex", gap:6, alignItems:"center"}}>
                {selectedJob && <span className={`status-pill status-${selectedJob.status}`}>{statusLabels[selectedJob.status]}{selectedJob.source_lang?` · ${selectedJob.source_lang}→${optLang.split("_")[0]}`:""}</span>}
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
                  <div><span className="detail-label">Format</span><span className="detail-value">{selectedJob.requested_format??"bv*+ba/b"}</span></div>
                </div>
                <div className="detail-media">
                  <div className="media-panel">
                    <div className="media-header"><h4>Media</h4>{mediaUrl&&<a className="link-button" href={mediaUrl} target="_blank" rel="noreferrer">Open file</a>}</div>
                    {mediaUrl? (showAudioPlayer? <audio className="media-player" controls src={mediaUrl}/>: <video className="media-player" controls src={mediaUrl}/>): <div className="media-empty">No media yet</div>}
                  </div>
                  <div className="media-panel transcript-paper">
                    <div className="media-header"><h4>Transcript — {optLang.split("_")[0].toUpperCase()}</h4>{transcriptUrl&&<a className="link-button" href={transcriptUrl} target="_blank" rel="noreferrer">Open text</a>}</div>
                    <div className="spool-header"><span>SPOOL</span><span>{selectedJob.source_lang?`${selectedJob.source_lang}→${optLang.split("_")[0]}`:optLang.split("_")[0]} · {selectedJob.progress>=100?"READY":"…"}</span></div>
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
                  <span>v{v.version} — {v.source_lang??"?"}→{optLang.split("_")[0]} — {v.model_name} — {new Date(v.created_at).toLocaleString()}</span>
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
