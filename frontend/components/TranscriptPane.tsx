"use client";

import type { TranscriptSegment } from "@/lib/api";

/** Parse "MM:SS" (or "HH:MM:SS") to seconds. */
export function tsToSeconds(ts: string): number {
  const parts = ts.split(":").map(Number);
  if (parts.some(Number.isNaN)) return 0;
  return parts.length === 3 ? parts[0] * 3600 + parts[1] * 60 + parts[2] : parts[0] * 60 + parts[1];
}

/** YouTube-style seek URL: media endpoint (URL source) accepts ?t=<sec>. */
export function seekUrl(mediaUrl: string | null, seconds: number): string {
  if (!mediaUrl) return "#";
  const sep = mediaUrl.includes("?") ? "&" : "?";
  return `${mediaUrl}${sep}t=${seconds}s`;
}

/**
 * Transcript with optional timed blocks. Blocks render as clickable
 * [MM:SS] anchors (video embed in API handles ?t=); legacy transcripts
 * without a segments sidecar fall back to plain text.
 */
export function TranscriptPane({
  text,
  segments,
  mediaUrl,
}: {
  text: string;
  segments: TranscriptSegment[] | null;
  mediaUrl: string | null;
}) {
  if (!segments || segments.length === 0) {
    return <pre className="transcript-viewer">{text}</pre>;
  }
  return (
    <div className="transcript-viewer transcript-segments">
      {segments.map((s, i) => (
        <p key={i} className="transcript-segment">
          <a
            className="transcript-ts"
            href={seekUrl(mediaUrl, tsToSeconds(s.start))}
            target="_blank"
            rel="noreferrer"
          >
            [{s.start}]
          </a>{" "}
          {s.text}
        </p>
      ))}
    </div>
  );
}