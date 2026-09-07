import os
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

_model = None
_tokenizer = None

MODEL_PATH = os.path.join(os.getenv("MODELS_DIR", "./models"), "ai_detector_v2")
MODEL_VERSION = "ai_detector_v2"


def _load():
    global _model, _tokenizer
    if _model is None:
        path = str(Path(MODEL_PATH))
        _tokenizer = AutoTokenizer.from_pretrained(path)
        _model = AutoModelForSequenceClassification.from_pretrained(path)
        _model.eval()
    return _model, _tokenizer


def _score_chunk(text: str, model, tokenizer) -> float:
    inputs = tokenizer(text, truncation=True, max_length=512, return_tensors="pt")
    with torch.no_grad():
        logits = model(**inputs).logits
        probs = torch.softmax(logits, dim=-1)
    return probs[0][1].item()  # CONFIRMED: index 1 = "ai_generated", index 0 = "human"


def detect_ai_content(text: str) -> dict:
    model, tokenizer = _load()
    words = (text or "").split()
    chunk_size = 400
    chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)] or [text or ""]
    scores = [_score_chunk(c, model, tokenizer) for c in chunks if c.strip()]
    if not scores:
        scores = [0.0]
    avg_score = sum(scores) / len(scores)
    threshold = float(os.getenv("AI_DETECTION_REFER_THRESHOLD", "0.7"))
    return {
        "score": avg_score,
        "flagged": avg_score > threshold,
        "model_version": MODEL_VERSION,
        "chunks_scored": len(scores),
    }
