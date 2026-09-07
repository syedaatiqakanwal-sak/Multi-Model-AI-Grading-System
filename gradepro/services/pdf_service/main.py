import io
import os
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from generator import GotenbergPDFGenerator
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="GradePro PDF Service", version="1.0.0")
generator = GotenbergPDFGenerator()

_BASE = Path(__file__).resolve().parent
GENERATED_DIR = Path(os.getenv("PDF_GENERATED_DIR", str(_BASE / "generated")))
TEMPLATES_DIR = Path(os.getenv("PDF_TEMPLATES_DIR", str(_BASE / "templates")))
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_filename_part(text: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", str(text)).strip()
    return cleaned or "Learner"


class GeneratePDFRequest(BaseModel):
    job_id: str
    unit_code: str = "HSC301"
    student_name: str = "Student"
    student_id: Optional[str] = ""
    college: str = "UKPDA"
    verdict: str = "pass"
    tasks: List[Dict[str, Any]] = []
    per_criterion: Optional[Dict[str, Any]] = {}   # keyed by criterion ID e.g. "1.1"
    overall_comment: Optional[str] = ""
    format_warnings: Optional[List[str]] = []
    rubric: Optional[Dict[str, Any]] = {}
    ai_detection: Optional[Dict[str, Any]] = {}
    plagiarism: Optional[Dict[str, Any]] = {}
    review_required: Optional[bool] = False


class GeneratePDFResponse(BaseModel):
    job_id: str
    pdf_url: str
    docx_url: str
    status: str


@app.post("/generate", response_model=GeneratePDFResponse)
async def generate_pdf(req: GeneratePDFRequest):
    # 1. Locate template
    template_path = TEMPLATES_DIR / f"{req.unit_code.upper()}_feedback_template.docx"
    if not template_path.exists():
        fallback_templates = list(TEMPLATES_DIR.glob("*.docx"))
        template_path = fallback_templates[0] if fallback_templates else None

    if template_path and template_path.exists():
        with open(template_path, "rb") as f:
            template_bytes = f.read()

        filled_docx = generator.fill_feedback_template(
            template_bytes=template_bytes,
            student_name=req.student_name,
            student_id=req.student_id or "",
            unit_code=req.unit_code,
            verdict=req.verdict,
            tasks=req.tasks,
            overall_comment=req.overall_comment or "",
            format_warnings=req.format_warnings or [],
            rubric=req.rubric or {},
            per_criterion=req.per_criterion or {},
            ai_detection=req.ai_detection or {},
            plagiarism=req.plagiarism or {},
            review_required=bool(req.review_required),
        )
    else:
        # No template: build a basic DOCX
        doc = __import__("docx").Document()
        doc.add_heading(f"Assessment Feedback Report — Unit {req.unit_code}", 0)
        doc.add_paragraph(f"Learner: {req.student_name}")
        doc.add_paragraph(f"Overall Result: {req.verdict.upper()}")
        for t in req.tasks:
            doc.add_heading(f"Task {t.get('task_number', 1)}: {t.get('task_heading', '')}", level=1)
            doc.add_paragraph(f"Result: {t.get('verdict', '').upper()}")
            doc.add_paragraph(f"Assessor Comments: {t.get('feedback_text', '')}")
        if req.overall_comment:
            doc.add_heading("Overall Assessor Comments", level=1)
            doc.add_paragraph(req.overall_comment)
        generator._append_integrity_section(
            doc,
            req.ai_detection or {},
            req.plagiarism or {},
            bool(req.review_required),
        )
        out = io.BytesIO()
        doc.save(out)
        filled_docx = out.getvalue()

    # Save filled DOCX
    docx_out_path = GENERATED_DIR / f"{req.job_id}.docx"
    with open(docx_out_path, "wb") as f:
        f.write(filled_docx)

    # 2. Convert to PDF via Gotenberg
    pdf_bytes = await generator.convert_docx_to_pdf(filled_docx)
    pdf_out_path = GENERATED_DIR / f"{req.job_id}.pdf"
    if pdf_bytes:
        with open(pdf_out_path, "wb") as f:
            f.write(pdf_bytes)

    # Save human-readable filename metadata e.g. "Bilal HSC301 Feedback.pdf"
    clean_name = sanitize_filename_part(req.student_name)
    clean_unit = sanitize_filename_part(req.unit_code.upper())
    pdf_filename = f"{clean_name} {clean_unit} Feedback.pdf"
    docx_filename = f"{clean_name} {clean_unit} Feedback.docx"

    meta_path = GENERATED_DIR / f"{req.job_id}.meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "student_name": req.student_name,
            "unit_code": req.unit_code,
            "pdf_filename": pdf_filename,
            "docx_filename": docx_filename,
        }, f)

    return GeneratePDFResponse(
        job_id=req.job_id,
        pdf_url=f"/api/v1/jobs/{req.job_id}/pdf",
        docx_url=f"/api/v1/jobs/{req.job_id}/docx",
        status="generated",
    )


@app.get("/download/{job_id}/pdf")
async def download_pdf(job_id: str):
    pdf_path = GENERATED_DIR / f"{job_id}.pdf"
    meta_path = GENERATED_DIR / f"{job_id}.meta.json"
    
    filename = f"Assessment_Feedback_{job_id[:8]}.pdf"
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                filename = meta.get("pdf_filename", filename)
        except Exception:
            pass

    if pdf_path.exists():
        return FileResponse(
            path=str(pdf_path),
            media_type="application/pdf",
            filename=filename,
        )
    
    docx_path = GENERATED_DIR / f"{job_id}.docx"
    if docx_path.exists():
        docx_filename = filename.replace(".pdf", ".docx")
        return FileResponse(
            path=str(docx_path),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=docx_filename,
        )
    raise HTTPException(status_code=404, detail="Feedback report not found")


@app.get("/download/{job_id}/docx")
async def download_docx(job_id: str):
    docx_path = GENERATED_DIR / f"{job_id}.docx"
    meta_path = GENERATED_DIR / f"{job_id}.meta.json"
    
    filename = f"Assessment_Feedback_{job_id[:8]}.docx"
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                filename = meta.get("docx_filename", filename)
        except Exception:
            pass

    if docx_path.exists():
        return FileResponse(
            path=str(docx_path),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=filename,
        )
    raise HTTPException(status_code=404, detail="DOCX report not found")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "pdf_service"}


Instrumentator().instrument(app).expose(app)
