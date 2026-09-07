import io
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
import torch
from embedder import get_embedder
from registry import get_model_registry
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="GradePro ML Inference", version="1.0.0")

MODELS_DIR = Path("/app/models")
MODELS_DIR.mkdir(parents=True, exist_ok=True)


class InferRequest(BaseModel):
    unit_code: str = "HSC301"
    task_texts: List[str]


class InferResponse(BaseModel):
    unit_code: str
    pass_probability: float
    criterion_scores: List[float]


@app.on_event("startup")
async def startup():
    # Warm up shared embedder and registry
    get_model_registry()


@app.post("/infer", response_model=InferResponse)
async def infer(req: InferRequest):
    embedder = get_embedder()
    registry = get_model_registry()

    # 1. Embed each task using full sliding-window embedder
    task_embeddings = []
    for text in req.task_texts:
        emb_np = embedder.encode(text)
        task_embeddings.append(torch.tensor(emb_np, dtype=torch.float32))

    if not task_embeddings:
        task_embeddings = [torch.zeros(384, dtype=torch.float32)]

    # 2. Forward through unit head — num_criteria = number of tasks
    head = registry.get_head(req.unit_code, num_criteria=len(task_embeddings))
    with torch.no_grad():
        out = head(task_embeddings)

    return InferResponse(
        unit_code=req.unit_code,
        pass_probability=round(out["pass_probability"], 4),
        criterion_scores=[round(s, 4) for s in out["criterion_scores"]],
    )


@app.post("/upload-model")
async def upload_model(
    file: UploadFile = File(...),
    unit_code: str = Form(...),
):
    """
    Receives a .pt model file from the orchestrator and saves it to disk.
    Invalidates the registry cache so the next infer call reloads from new weights.
    """
    unit_code = unit_code.upper().strip()
    content = await file.read()

    # Validate it's a valid PyTorch state dict
    try:
        buf = io.BytesIO(content)
        torch.load(buf, map_location="cpu")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid PyTorch file: {e}")

    save_path = MODELS_DIR / f"{unit_code}_head.pt"
    save_path.write_bytes(content)

    # Evict from registry LRU so next request reloads fresh weights
    registry = get_model_registry()
    registry.evict(unit_code)

    return {
        "status": "saved",
        "unit_code": unit_code,
        "path": str(save_path),
        "size_kb": round(len(content) / 1024, 1),
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ml_inference"}


Instrumentator().instrument(app).expose(app)
