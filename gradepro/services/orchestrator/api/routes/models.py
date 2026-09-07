import os
import io
import time
import json
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
import httpx
import redis.asyncio as aioredis
from app.config import settings

router = APIRouter(prefix="/models", tags=["unit_models"])


class UnitModelItem(BaseModel):
    id: str
    awarding_body: str
    course_name: str
    unit_code: str
    unit_name: str
    version: int
    active: bool
    filename: str
    file_size_kb: float
    rubric_filename: Optional[str] = None
    criteria_count: Optional[int] = None
    created_at: str


@router.get("/")
async def list_models():
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        data = await r.get("gradepro:registered_unit_models")
        if data:
            return {"models": json.loads(data)}
        # Default seeded model for HSC301
        default_models = [
            {
                "id": "hsc301-v1",
                "awarding_body": "QUALIFI",
                "course_name": "Diploma in Health and Social Care",
                "unit_code": "HSC301",
                "unit_name": "An Introduction to Health and Social Care",
                "version": 1,
                "active": True,
                "filename": "HSC301_head.pt",
                "file_size_kb": 420.5,
                "rubric_filename": "HSC301_rubric.json",
                "criteria_count": 7,
                "created_at": "20 Aug 2026",
            }
        ]
        return {"models": default_models}
    finally:
        await r.close()


@router.post("/upload")
async def upload_model(
    model_file: Optional[UploadFile] = File(None),
    rubric_file: Optional[UploadFile] = File(None),
    awarding_body: str = Form("QUALIFI"),
    course_name: str = Form(""),
    unit_code: str = Form(...),
    unit_name: str = Form(...),
):
    unit_code = unit_code.upper().strip()
    model_id = f"{unit_code.lower()}-v{int(time.time())}"
    criteria_count = 0
    rubric_filename = None

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    # ── 1. Save rubric JSON to Redis (so grading pipeline can load it) ──
    if rubric_file:
        rubric_bytes = await rubric_file.read()
        try:
            rubric_data = json.loads(rubric_bytes.decode("utf-8"))
            # Validate it has the expected structure
            if "learning_outcomes" not in rubric_data:
                raise ValueError("Rubric JSON must contain 'learning_outcomes'")

            # Count criteria
            for lo in rubric_data.get("learning_outcomes", []):
                criteria_count += len(lo.get("criteria", []))

            # Store rubric in Redis keyed by unit_code
            await r.set(
                f"gradepro:rubric:{unit_code}",
                json.dumps(rubric_data),
            )
            rubric_filename = rubric_file.filename
        except (json.JSONDecodeError, ValueError) as e:
            await r.close()
            raise HTTPException(status_code=400, detail=f"Invalid rubric JSON: {e}")

    # ── 2. Push model .pt file to ml_inference service ──
    model_size_kb = 0.0
    model_filename = f"{unit_code}_head.pt"

    if model_file:
        model_bytes = await model_file.read()
        model_size_kb = round(len(model_bytes) / 1024.0, 1)
        model_filename = model_file.filename or model_filename

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{settings.ML_INFERENCE_URL}/upload-model",
                    files={"file": (model_filename, io.BytesIO(model_bytes), "application/octet-stream")},
                    data={"unit_code": unit_code},
                )
                if resp.status_code != 200:
                    await r.close()
                    raise HTTPException(
                        status_code=502,
                        detail=f"ML inference rejected model file: {resp.text[:300]}"
                    )
        except httpx.RequestError as e:
            await r.close()
            raise HTTPException(status_code=502, detail=f"Could not reach ML inference service: {e}")

    # ── 3. Register model metadata in Redis ──
    new_model = {
        "id": model_id,
        "awarding_body": awarding_body.upper(),
        "course_name": course_name or "Standard Qualification",
        "unit_code": unit_code,
        "unit_name": unit_name,
        "version": 1,
        "active": True,
        "filename": model_filename,
        "file_size_kb": model_size_kb,
        "rubric_filename": rubric_filename,
        "criteria_count": criteria_count,
        "created_at": time.strftime("%d %b %Y"),
    }

    try:
        existing = await r.get("gradepro:registered_unit_models")
        models_list = json.loads(existing) if existing else []
        # Replace existing entry for this unit_code
        models_list = [m for m in models_list if m.get("unit_code") != unit_code]
        models_list.append(new_model)
        await r.set("gradepro:registered_unit_models", json.dumps(models_list))
    finally:
        await r.close()

    return {"status": "uploaded", "model": new_model}


@router.post("/{unit_code}/test")
async def test_submodel(unit_code: str):
    """
    Tests loading the sub-model in ML inference service,
    executes sample vector forward pass, and measures real latency.
    """
    import time as _time
    start_time = _time.perf_counter()
    sample_text = ["Sample assignment task content assessing health and social care principles."]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.ML_INFERENCE_URL}/infer",
                json={
                    "unit_code": unit_code.upper(),
                    "task_texts": sample_text,
                },
            )
            latency_ms = round((_time.perf_counter() - start_time) * 1000.0, 1)

            if resp.status_code == 200:
                data = resp.json()
                return {
                    "success": True,
                    "unit_code": unit_code.upper(),
                    "latency_ms": latency_ms,
                    "pass_probability": data.get("pass_probability", 0.0),
                    "criterion_scores": data.get("criterion_scores", []),
                    "message": f"Sub-model {unit_code.upper()} loaded & verified in {latency_ms}ms.",
                }
            else:
                return {
                    "success": False,
                    "unit_code": unit_code.upper(),
                    "latency_ms": latency_ms,
                    "message": f"Inference engine returned status {resp.status_code}: {resp.text[:200]}",
                }
    except Exception as e:
        latency_ms = round((_time.perf_counter() - start_time) * 1000.0, 1)
        return {
            "success": False,
            "unit_code": unit_code.upper(),
            "latency_ms": latency_ms,
            "message": f"Could not reach ML inference service: {str(e)[:200]}",
        }
