import os
import json
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
import redis.asyncio as aioredis
from app.config import settings

router = APIRouter(prefix="/rubrics", tags=["unit_rubrics"])

def _resolve_rubrics_dir() -> Path:
    docker_dir = Path("/app/shared/rubrics")
    local_dir = Path(__file__).resolve().parents[4] / "shared" / "rubrics"
    if docker_dir.exists() and any(docker_dir.glob("*.json")):
        return docker_dir
    if local_dir.exists():
        return local_dir
    target = docker_dir if Path("/app").exists() else local_dir
    target.mkdir(parents=True, exist_ok=True)
    return target


SHARED_RUBRICS_DIR = _resolve_rubrics_dir()


class RubricListItem(BaseModel):
    id: str
    unit_code: str
    unit_name: str
    qualification: str
    awarding_body: str
    word_count_min: int
    word_count_max: int
    criteria_count: int
    active: bool
    filename: str
    created_at: str


@router.get("/", response_model=Dict[str, List[RubricListItem]])
async def list_rubrics():
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        data = await r.get("gradepro:registered_unit_rubrics")
        if data:
            return {"rubrics": json.loads(data)}

        # Seed from disk rubrics
        seeded = []
        rubric_files = list(SHARED_RUBRICS_DIR.glob("*.json"))
        # Also check local shared path if in dev
        if not rubric_files:
            local_dir = Path(__file__).resolve().parent.parent.parent.parent.parent / "shared" / "rubrics"
            if local_dir.exists():
                rubric_files = list(local_dir.glob("*.json"))

        for rf in rubric_files:
            try:
                with open(rf, "r", encoding="utf-8") as f:
                    rdata = json.load(f)
                uc = rdata.get("unit_code", rf.stem.replace("_rubric", "")).upper()
                crits = sum(len(lo.get("criteria", [])) for lo in rdata.get("learning_outcomes", []))
                seeded.append({
                    "id": f"{uc.lower()}-rubric",
                    "unit_code": uc,
                    "unit_name": rdata.get("unit_title", "Unit"),
                    "qualification": rdata.get("qualification", "UK Qualification"),
                    "awarding_body": rdata.get("awarding_body", "QUALIFI"),
                    "word_count_min": rdata.get("word_count_min", 1850),
                    "word_count_max": rdata.get("word_count_max", 2150),
                    "criteria_count": crits,
                    "active": True,
                    "filename": rf.name,
                    "created_at": "20 Aug 2026",
                })
                # Cache to redis
                await r.set(f"gradepro:rubric:{uc}", json.dumps(rdata))
            except Exception:
                pass

        if not seeded:
            seeded.append({
                "id": "hsc301-rubric",
                "unit_code": "HSC301",
                "unit_name": "An Introduction to Health and Social Care",
                "qualification": "QUALIFI Level 3 Diploma in Health and Social Care",
                "awarding_body": "QUALIFI",
                "word_count_min": 1850,
                "word_count_max": 2150,
                "criteria_count": 7,
                "active": True,
                "filename": "HSC301_rubric.json",
                "created_at": "20 Aug 2026",
            })

        await r.set("gradepro:registered_unit_rubrics", json.dumps(seeded))
        return {"rubrics": seeded}
    finally:
        await r.close()


@router.post("/upload")
async def upload_rubric(
    rubric_file: UploadFile = File(...),
    unit_code: Optional[str] = Form(None),
):
    if not rubric_file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Rubric file must be a JSON file (.json)")

    content = await rubric_file.read()
    try:
        rubric_data = json.loads(content.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON file: {e}")

    if "learning_outcomes" not in rubric_data:
        raise HTTPException(status_code=400, detail="Rubric JSON must contain a 'learning_outcomes' array")

    code = (unit_code or rubric_data.get("unit_code", "")).upper().strip()
    if not code:
        code = rubric_file.filename.replace("_rubric.json", "").replace(".json", "").upper()
    rubric_data["unit_code"] = code

    title = rubric_data.get("unit_title", rubric_data.get("unit_name", f"Unit {code}"))
    awarding_body = rubric_data.get("awarding_body", "QUALIFI")
    qual = rubric_data.get("qualification", "UK Diploma")
    min_w = int(rubric_data.get("word_count_min", 1850))
    max_w = int(rubric_data.get("word_count_max", 2150))
    criteria_count = sum(len(lo.get("criteria", [])) for lo in rubric_data.get("learning_outcomes", []))

    # Save to disk
    out_file = SHARED_RUBRICS_DIR / f"{code}_rubric.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(rubric_data, f, indent=2)

    # Save to Redis
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await r.set(f"gradepro:rubric:{code}", json.dumps(rubric_data))

        # Update registered list
        existing_data = await r.get("gradepro:registered_unit_rubrics")
        rubrics_list = json.loads(existing_data) if existing_data else []
        
        # Remove existing if any
        rubrics_list = [rb for rb in rubrics_list if rb.get("unit_code") != code]
        
        new_entry = {
            "id": f"{code.lower()}-rubric",
            "unit_code": code,
            "unit_name": title,
            "qualification": qual,
            "awarding_body": awarding_body,
            "word_count_min": min_w,
            "word_count_max": max_w,
            "criteria_count": criteria_count,
            "active": True,
            "filename": f"{code}_rubric.json",
            "created_at": time.strftime("%d %b %Y"),
        }
        rubrics_list.insert(0, new_entry)
        await r.set("gradepro:registered_unit_rubrics", json.dumps(rubrics_list))

        return {
            "status": "success",
            "message": f"Rubric for {code} successfully uploaded and activated",
            "rubric": new_entry,
        }
    finally:
        await r.close()


@router.get("/{unit_code}")
async def get_rubric(unit_code: str):
    unit_code = unit_code.upper().strip()
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        data = await r.get(f"gradepro:rubric:{unit_code}")
        if data:
            return json.loads(data)
    finally:
        await r.close()

    disk_path = SHARED_RUBRICS_DIR / f"{unit_code}_rubric.json"
    if disk_path.exists():
        with open(disk_path, "r", encoding="utf-8") as f:
            return json.load(f)

    raise HTTPException(status_code=404, detail=f"Rubric for unit {unit_code} not found")
