"""NLLB translation service: any language -> pt-BR (por_Latn)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from app.config import get_settings

# whisper lang -> NLLB code
WHISPER_TO_NLLB = {
    "en": "eng_Latn",
    "pt": "por_Latn",
    "es": "spa_Latn",
    "fr": "fra_Latn",
    "de": "deu_Latn",
    "it": "ita_Latn",
    "nl": "nld_Latn",
    "pl": "pol_Latn",
    "ru": "rus_Cyrl",
    "ja": "jpn_Jpan",
    "zh": "zho_Hans",
    "ko": "kor_Hang",
    "ar": "arb_Arab",
    "tr": "tur_Latn",
    "hi": "hin_Deva",
    "id": "ind_Latn",
    "vi": "vie_Latn",
    "uk": "ukr_Cyrl",
    "ro": "ron_Latn",
    "sv": "swe_Latn",
    "no": "nno_Latn",
    "da": "dan_Latn",
    "fi": "fin_Latn",
    "cs": "ces_Latn",
    "el": "ell_Grek",
    "he": "heb_Hebr",
    "th": "tha_Thai",
}

_tokenizer = None
_model = None

def _lazy_load():
    global _tokenizer, _model
    if _model is not None:
        return
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

    s = get_settings()
    model_id = s.translation_model
    cache_dir = Path(s.models_dir) / "nllb"
    cache_dir.mkdir(parents=True, exist_ok=True)
    print(f"Loading NLLB model '{model_id}' on {s.translation_device} ...")
    _tokenizer = AutoTokenizer.from_pretrained(model_id, cache_dir=str(cache_dir))
    _model = AutoModelForSeq2SeqLM.from_pretrained(model_id, cache_dir=str(cache_dir))
    if s.translation_device == "cpu":
        _model = _model.to("cpu")
    _model.eval()
    print("NLLB loaded")

def whisper_to_nllb(lang: Optional[str]) -> str:
    if not lang:
        return "eng_Latn"
    lang = lang.lower().strip()[:2]
    return WHISPER_TO_NLLB.get(lang, "eng_Latn")

def needs_translation(lang: Optional[str]) -> bool:
    if not lang:
        return True
    return not lang.lower().startswith("pt")

def _chunk_text(text: str, max_tokens: int = 400) -> list[str]:
    # simple sentence splitter + greedy token-length grouping
    # split by sentence end
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks: list[str] = []
    cur = ""
    for s in sentences:
        if not s.strip():
            continue
        # rough token estimate: words * 1.3
        if len((cur + " " + s).split()) * 1.3 > max_tokens and cur:
            chunks.append(cur.strip())
            cur = s
        else:
            cur = (cur + " " + s).strip() if cur else s
    if cur:
        chunks.append(cur.strip())
    return chunks if chunks else [text]

def translate(text: str, src_lang: Optional[str], tgt_code: Optional[str] = None) -> str:
    if not text.strip():
        return text
    s = get_settings()
    tgt = tgt_code or s.translation_target_lang_code
    # map short target like "pt" to NLLB code if needed
    if "_" not in tgt:
        short_map = {"pt": "por_Latn", "en": "eng_Latn", "es": "spa_Latn", "fr": "fra_Latn", "de": "deu_Latn"}
        tgt = short_map.get(tgt.lower(), "por_Latn")
    # skip if source already matches target language family
    if src_lang and tgt.lower().startswith(src_lang.lower()[:2]):
        # e.g. src pt + tgt por_Latn -> skip
        if src_lang.lower().startswith("pt") and tgt == "por_Latn":
            return text
    if not needs_translation(src_lang) and tgt == "por_Latn":
        return text
    _lazy_load()
    import torch

    src_code = whisper_to_nllb(src_lang)
    tgt_code = tgt

    # tokenizer src lang must be set
    assert _tokenizer is not None and _model is not None
    _tokenizer.src_lang = src_code

    s = get_settings()
    chunks = _chunk_text(text)
    outputs: list[str] = []
    for chunk in chunks:
        inputs = _tokenizer(chunk, return_tensors="pt", truncation=True, max_length=512)
        # move to device
        if s.translation_device == "cpu":
            inputs = {k: v.cpu() for k, v in inputs.items()}
        with torch.no_grad():
            generated = _model.generate(
                **inputs,
                forced_bos_token_id=_tokenizer.convert_tokens_to_ids(tgt_code),
                max_length=512,
                num_beams=1,  # greedy for CPU speed; use 4 for quality but slower
            )
        decoded = _tokenizer.batch_decode(generated, skip_special_tokens=True)[0]
        outputs.append(decoded.strip())
    return " ".join(outputs).strip()

# For testing without loading heavy model, allow mocking _lazy_load
