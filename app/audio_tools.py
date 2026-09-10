"""Audio tools for processing audio files"""
import os
from pathlib import Path

import ffmpeg
import numpy as np

SAMPLE_RATE = 16000

NdArray = np.ndarray


def decode_audio(audio_file: Path) -> bytes:
    """Decode audio from a file"""
    try:
        audio_data, _ = (
            ffmpeg.input(str(audio_file), threads=0)
            .output("-", format="s16le", acodec="pcm_s16le", ac=1, ar=SAMPLE_RATE)
            .run(cmd=["ffmpeg", "-nostdin"], capture_stdout=True, capture_stderr=True)
        )
        return audio_data
    except ffmpeg.Error as ffmpeg_err:
        raise RuntimeError(
            f"Failed to load audio: {ffmpeg_err.stderr.decode()}"
        ) from ffmpeg_err


def convert_to_float_array(audio_data: bytes) -> NdArray:
    """Convert audio data to a float array"""
    int_array = np.frombuffer(audio_data, np.int16).flatten()
    float_array = int_array.astype(np.float32) / 32768.0
    return float_array


def convert_audio_format(
    input_file: str, output_file_name: str, audio_format: str
) -> str:
    """Convert an audio file to a different format"""
    try:
        output_file_path = os.path.join(os.getcwd(), "outputs", output_file_name)
        audio = ffmpeg.input(input_file)
        audio = audio.output(output_file_path, format=audio_format)
        audio.run()
        return output_file_path
    except Exception as err:
        raise RuntimeError(f"Error converting audio format: {err}") from err


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
