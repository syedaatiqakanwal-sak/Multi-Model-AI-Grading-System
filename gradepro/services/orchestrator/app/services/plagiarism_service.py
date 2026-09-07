import json
import os
from pathlib import Path

from sentence_transformers import SentenceTransformer, util

_model = None

MODEL_PATH = os.path.join(os.getenv("MODELS_DIR", "./models"), "plagiarism_detector_v1")
MODEL_VERSION = "plagiarism_v1"


def _load():
    global _model
    if _model is None:
        _model = SentenceTransformer(str(Path(MODEL_PATH)))
    return _model


def load_reference_corpus(unit_code: str = "") -> list:
    """
    Load comparison texts. Prefer a local corpus dir; Postgres prior-submission
    text is not stored yet, so this stays caller-overridable via the task param.
    """
    bases = [
        Path(os.getenv("MODELS_DIR", "./models")) / "plagiarism_corpus",
        Path(__file__).resolve().parents[4] / "shared" / "corpus",
    ]
    corpus = []
    for base in bases:
        if not base.exists():
            continue
        for path in sorted(base.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                items = data if isinstance(data, list) else data.get("documents", [])
                for item in items:
                    if unit_code and item.get("unit_code") and item["unit_code"] != unit_code:
                        continue
                    text = item.get("text") or item.get("content") or ""
                    if text.strip():
                        corpus.append({
                            "source": item.get("source") or path.name,
                            "text": text,
                        })
            except Exception:
                continue
        for path in sorted(base.glob("*.txt")):
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
            if text:
                corpus.append({"source": path.name, "text": text})
    return corpus


def check_plagiarism(text: str, reference_corpus: list) -> dict:
    if not reference_corpus:
        return {
            "overall_similarity_pct": 0.0,
            "top_matches": [],
            "model_version": MODEL_VERSION,
            "corpus_empty": True,
        }
    model = _load()
    query_emb = model.encode(text or "", convert_to_tensor=True)
    corpus_embs = model.encode([r["text"] for r in reference_corpus], convert_to_tensor=True)
    similarities = util.cos_sim(query_emb, corpus_embs)[0]
    top_k = similarities.topk(min(5, len(reference_corpus)))
    top_matches = [
        {"source": reference_corpus[int(idx)]["source"], "similarity": float(score)}
        for score, idx in zip(top_k.values, top_k.indices)
    ]
    overall = float(top_k.values[0]) * 100 if top_matches else 0.0
    return {
        "overall_similarity_pct": overall,
        "top_matches": top_matches,
        "model_version": MODEL_VERSION,
        "corpus_empty": False,
    }
