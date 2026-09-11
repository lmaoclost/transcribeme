"""Audio tools for processing audio files (ffmpeg CLI only, no numpy/torch)."""
from pathlib import Path


def accelerate_audio(input_path: Path, factor: float = 1.5) -> Path:
    """Accelerate audio with ffmpeg atempo (pitch-preserving). Returns new temp path or original if factor==1.0."""
    if factor == 1.0 or factor is None:
        return input_path
    # clamp to allowed global values 1.0-1.5
    if not 1.0 <= factor <= 1.5:
        raise ValueError("transcription_speed must be 1.0 or 1.5")
    import subprocess
    import tempfile

    # create temp file in same dir for cleanup tracking
    tmp = Path(tempfile.mktemp(suffix=input_path.suffix, prefix=f"acc{factor}_"))
    try:
        # single atempo for 1.5 (max 2.0, no chain needed); keep 16k mono for whisper
        result = subprocess.run(
            ["ffmpeg", "-y", "-nostdin", "-i", str(input_path), "-filter:a", f"atempo={factor}", "-ar", "16000", "-ac", "1", str(tmp)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
            return input_path
        return tmp
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return input_path


def split_audio_for_transcription(
    input_path: Path, chunk_minutes: int = 20, overlap_seconds: int = 2
) -> list[Path]:
    """Split long audio via ffmpeg segment. Returns chunk paths."""
    import subprocess
    import tempfile

    tmpdir = Path(tempfile.mkdtemp(prefix="split_"))
    # Use ffmpeg segment muxer
    chunk_sec = chunk_minutes * 60
    pattern = str(tmpdir / "chunk_%03d" / ".ext")
    # Simpler: use ffmpeg to split
    try:
        # Get duration first
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(input_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        import json

        duration = 0
        if result.returncode == 0:
            data = json.loads(result.stdout)
            duration = float(data.get("format", {}).get("duration", 0))
        if duration == 0 or duration <= chunk_sec:
            return [input_path]

        chunks: list[Path] = []
        n_chunks = int((duration + chunk_sec - 1) // chunk_sec)
        for i in range(n_chunks):
            start = i * chunk_sec
            # overlap except first
            if i > 0:
                start = max(0, start - overlap_seconds)
            out = tmpdir / f"chunk_{i:03d}{input_path.suffix}"
            dur = chunk_sec + (overlap_seconds if i > 0 else 0)
            subprocess.run(
                ["ffmpeg", "-nostdin", "-y", "-ss", str(start), "-i", str(input_path), "-t", str(dur), "-c", "copy", str(out)],
                capture_output=True,
                timeout=30,
            )
            if out.exists():
                chunks.append(out)
        return chunks if chunks else [input_path]
    except Exception:
        return [input_path]
