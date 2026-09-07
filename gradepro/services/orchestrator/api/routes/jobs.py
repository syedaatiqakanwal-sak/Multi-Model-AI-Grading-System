import hashlib
import json
import uuid
from typing import Optional, List
from fastapi import APIRouter, Header, UploadFile, File, Form, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx
import redis.asyncio as aioredis
from app.config import settings
from app.persistence import ensure_grading_job
from workers.grading import process_grading_job

router = APIRouter(prefix="/jobs", tags=["grading_jobs"])


class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str


@router.post("/upload", response_model=JobResponse)
async def upload_assignment(
    file: UploadFile = File(...),
    unit_code: Optional[str] = Form("HSC301"),
    college: Optional[str] = Form("UKPDA"),
):
    if not file.filename.endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx assignment submissions are supported")

    content = await file.read()
    job_id = str(uuid.uuid4())
    file_hash = hashlib.sha256(content).hexdigest()
    await ensure_grading_job(
        job_id,
        student_name="Pending parse",
        file_hash=file_hash,
        file_path_r2=f"assignments/{job_id}.docx",
        status="pending",
    )

    # Queue grading job via Celery
    process_grading_job.delay(
        job_id=job_id,
        file_bytes_hex=content.hex(),
        unit_code=unit_code or "HSC301",
        college=college or "UKPDA",
    )

    return JobResponse(
        job_id=job_id,
        status="pending",
        message="Assignment uploaded and queued for processing",
    )


@router.get("/{job_id}/events")
async def get_job_events(job_id: str):
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        events = await r.xrange(f"job:{job_id}:events", count=100)
        return {"job_id": job_id, "events": [e[1] for e in events]}
    finally:
        await r.close()


@router.get("/{job_id}/pdf")
async def download_job_pdf(job_id: str):
    """Download the official generated PDF or DOCX assessment feedback report."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{settings.PDF_SERVICE_URL}/download/{job_id}/pdf")
            if resp.status_code == 200:
                media_type = resp.headers.get("content-type", "application/pdf")
                cd_header = resp.headers.get("content-disposition")
                headers = {}
                if cd_header:
                    headers["Content-Disposition"] = cd_header
                else:
                    headers["Content-Disposition"] = f'attachment; filename="Assessment_Feedback_{job_id[:8]}.pdf"'
                return Response(
                    content=resp.content,
                    media_type=media_type,
                    headers=headers,
                )
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="Assessment feedback report is not ready yet or was not found.")


@router.get("/{job_id}/docx")
async def download_job_docx(job_id: str):
    """Download the filled official DOCX assessment marking sheet."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{settings.PDF_SERVICE_URL}/download/{job_id}/docx")
            if resp.status_code == 200:
                media_type = resp.headers.get("content-type", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                cd_header = resp.headers.get("content-disposition")
                headers = {}
                if cd_header:
                    headers["Content-Disposition"] = cd_header
                else:
                    headers["Content-Disposition"] = f'attachment; filename="Assessment_Feedback_{job_id[:8]}.docx"'
                return Response(
                    content=resp.content,
                    media_type=media_type,
                    headers=headers,
                )
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="DOCX assessment marking sheet not found.")


@router.get("/{job_id}/integrity")
async def get_job_integrity(job_id: str):
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        raw = await r.get(f"job:{job_id}:integrity")
        if not raw:
            return {"job_id": job_id, "status": "pending"}
        return {"job_id": job_id, **json.loads(raw)}
    finally:
        await r.close()


class IntegrityReviewRequest(BaseModel):
    action: str
    reason: str
    role: Optional[str] = "MAIN_ASSESSOR"


@router.post("/{job_id}/integrity-review")
async def review_job_integrity(
    job_id: str,
    payload: IntegrityReviewRequest,
    x_user_role: Optional[str] = Header(default=None),
):
    """MAIN_ASSESSOR / ADMIN only — matches existing grade:override RBAC."""
    role = (x_user_role or payload.role or "").upper()
    if role not in ("ADMIN", "MAIN_ASSESSOR"):
        raise HTTPException(status_code=403, detail="MAIN_ASSESSOR or ADMIN role required to finalise integrity review")
    if payload.action not in ("approve", "hold"):
        raise HTTPException(status_code=400, detail="action must be approve or hold")
    if not (payload.reason or "").strip():
        raise HTTPException(status_code=400, detail="A review reason is required")

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        raw = await r.get(f"job:{job_id}:integrity")
        bundle = json.loads(raw) if raw else {}
        bundle["review_required"] = payload.action == "hold"
        bundle["review"] = {
            "action": payload.action,
            "reason": payload.reason.strip(),
            "role": role,
        }
        await r.set(f"job:{job_id}:integrity", json.dumps(bundle), ex=86400)
        await r.xadd(
            f"job:{job_id}:events",
            {
                "job_id": job_id,
                "stage": "INTEGRITY_REVIEW",
                "progress": "100",
                "data": json.dumps(bundle["review"]),
            },
            maxlen=100,
        )
        return {"job_id": job_id, **bundle}
    finally:
        await r.close()
