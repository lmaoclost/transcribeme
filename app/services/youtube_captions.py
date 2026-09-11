"""YouTube caption download + clean to plain text."""

from __future__ import annotations

import re
from pathlib import Path
import tempfile

from yt_dlp import YoutubeDL

from app.config import get_settings
from app.download_processor import _base_ydl_params

# map caption lang codes to whisper-style short codes for NLLB
CAPTION_TO_SHORT = {
    "pt": "pt", "pt-BR": "pt", "pt-PT": "pt",
    "en": "en", "en-US": "en", "en-GB": "en",
    "es": "es", "es-US": "es", "es-ES": "es",
    "fr": "fr", "de": "de", "ja": "ja",
}

# reverse: NLLB target code -> YouTube subtitle lang (short codes are valid YT langs)
_NLLB_TO_SHORT = {v: k for k, v in {
    "en": "eng_Latn", "pt": "por_Latn", "es": "spa_Latn", "fr": "fra_Latn",
    "de": "deu_Latn", "it": "ita_Latn", "nl": "nld_Latn", "pl": "pol_Latn",
    "ru": "rus_Cyrl", "ja": "jpn_Jpan", "zh": "zho_Hans", "ko": "kor_Hang",
    "ar": "arb_Arab", "tr": "tur_Latn", "hi": "hin_Deva", "id": "ind_Latn",
    "vi": "vie_Latn", "uk": "ukr_Cyrl", "ro": "ron_Latn", "sv": "swe_Latn",
    "no": "nno_Latn", "da": "dan_Latn", "fi": "fin_Latn", "cs": "ces_Latn",
    "el": "ell_Grek", "he": "heb_Hebr", "th": "tha_Thai",
}.items()}


def nllb_to_youtube(tgt_code: str | None) -> str | None:
    """Map an NLLB target code (eng_Latn) to a YouTube subtitle lang (en)."""
    if not tgt_code:
        return None
    if tgt_code in _NLLB_TO_SHORT:
        return _NLLB_TO_SHORT[tgt_code]
    # fallback heuristic: first two letters of the language prefix
    return tgt_code.split("_")[0][:2].lower() or None

TIMESTAMP_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->.*$")
NUMERIC_RE = re.compile(r"^\d+$")
BRACKET_MUSIC_RE = re.compile(r"^\s*[\[\(].*?(music|laughter|applause|noise|inaudible|música|risos).*?[\]\)]\s*$", re.IGNORECASE)
SPEAKER_RE = re.compile(r"^\s*>>\s*[^:]+:\s*")
SPEAKER2_RE = re.compile(r"^\s*[A-Z][a-zA-Z]+\s*:\s*")
WEBVTT_HEADERS = {"WEBVTT", "Kind:", "Language:"}

def clean_vtt_text(raw: str) -> str:
    lines = raw.splitlines()
    cleaned: list[str] = []
    seen = set()
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s in WEBVTT_HEADERS or s.startswith("Kind:") or s.startswith("Language:"):
            continue
        if NUMERIC_RE.match(s):
            continue
        if TIMESTAMP_RE.match(s):
            continue
        if BRACKET_MUSIC_RE.match(s):
            continue
        # decode html entities like &gt; &lt;
        s = s.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
        # remove inline timestamp and style tags like <00:00:00.240> <c> </c>
        s = re.sub(r"<[^>]+>", "", s)
        # remove leading >> markers
        s = re.sub(r"^\s*>>\s*", "", s)
        s = re.sub(r"\s*>>\s*", " ", s)
        # remove speaker prefixes but keep text
        s = SPEAKER_RE.sub("", s)
        s = SPEAKER2_RE.sub("", s)
        # remove bracketed music inline
        s = re.sub(r"\[.*?music.*?\]", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\[.*?música.*?\]", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\[.*?applause.*?\]", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\[.*?risos.*?\]", "", s, flags=re.IGNORECASE)
        s = s.strip()
        if not s:
            continue
        # dedup consecutive duplicates
        if s in seen and cleaned and cleaned[-1] == s:
            continue
        seen.add(s)
        cleaned.append(s)
    # join with space, collapse whitespace
    text = " ".join(cleaned)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def _is_youtube_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url

def fetch_youtube_transcript(
    url: str, langs: list[str] | None = None, target_lang: str | None = None
) -> tuple[str, str] | None:
    """Try to download captions. Returns (clean_text, detected_lang) or None if no caption.

    The target output language goes first: native target captions (official,
    else auto — yt-dlp already prefers official per lang) win over any other
    language, so NLLB only runs when no target captions exist.
    """
    if not _is_youtube_url(url):
        return None
    if langs is None:
        langs = [s.strip() for s in get_settings().youtube_sub_langs.split(",") if s.strip()]
    if target_lang is None:
        try:
            target_lang = get_settings().translation_target_lang_code
        except Exception:
            target_lang = None
    ordered = list(langs)
    yt_target = nllb_to_youtube(target_lang)
    if yt_target and yt_target not in ordered:
        ordered.insert(0, yt_target)
    elif yt_target:
        ordered.remove(yt_target)
        ordered.insert(0, yt_target)
    # Try langs one by one to avoid 429 from requesting many at once
    for lang_try in ordered:
        tmpdir = Path(tempfile.mkdtemp(prefix="ytcap_"))
        ydl_params = {
            **_base_ydl_params(),
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": [lang_try],
            "subtitlesformat": "vtt/best",
            "outtmpl": str(tmpdir / "%(id)s.%(ext)s"),
        }
        ydl_params.pop("format", None)
        try:
            with YoutubeDL(ydl_params) as ydl:
                ydl.extract_info(url, download=True)
                candidates = list(tmpdir.glob("*.vtt"))
                if not candidates:
                    candidates = list(tmpdir.glob("*.srt"))
                if not candidates:
                    continue
                best = candidates[0]
                raw = best.read_text(encoding="utf-8", errors="ignore")
                # lang from filename
                parts = best.name.split(".")
                detected = parts[-2] if len(parts) >= 3 else lang_try
                short = CAPTION_TO_SHORT.get(detected, detected.split("-")[0].lower())
                cleaned = clean_vtt_text(raw)
                if not cleaned:
                    continue
                return cleaned, short
        except Exception:
            continue
        finally:
            try:
                for f in tmpdir.glob("*"):
                    f.unlink(missing_ok=True)
                tmpdir.rmdir()
            except Exception:
                pass
    return None
