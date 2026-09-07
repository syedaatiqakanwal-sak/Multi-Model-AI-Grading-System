import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from celery import chord, group

logger = logging.getLogger(__name__)


def compute_review_required(
    ai_result: Dict[str, Any],
    plag_result: Dict[str, Any],
    ai_threshold: float = 0.7,
    plagiarism_threshold: float = 20.0,
) -> bool:
    """Thresholds flag review only — they never auto-fail the academic verdict."""
    flagged_ai = bool(ai_result.get("flagged") or float(ai_result.get("score") or 0) > ai_threshold)
    flagged_plag = float(plag_result.get("overall_similarity_pct") or 0) > plagiarism_threshold
    return flagged_ai or flagged_plag


def integrity_fields(integrity: dict) -> Dict[str, Any]:
    integrity = integrity or {}
    return {
        "ai_detection": integrity.get("ai_detection") or {},
        "plagiarism": integrity.get("plagiarism") or {},
        "review_required": bool(integrity.get("review_required")),
        "review_roles": integrity.get("review_roles") or ["ADMIN", "MAIN_ASSESSOR"],
    }


def dispatch_integrity_analysis(
    job_id: str,
    student_text: str,
    reference_corpus: Optional[List[Dict[str, Any]]] = None,
):
    """
    Fan out AI detection + plagiarism on analysis_queue in parallel with
    grading_queue evaluation. Report generation waits on the chord callback.
    """
    from app.tasks.analysis_tasks import (
        ai_detection_task,
        finalize_integrity_task,
        plagiarism_task,
    )

    header = group(
        ai_detection_task.s(job_id, student_text),
        plagiarism_task.s(job_id, student_text, reference_corpus or []),
    )
    return chord(header, finalize_integrity_task.s(job_id)).apply_async()


async def await_integrity_results(redis_client, job_id: str, timeout_seconds: float = 180) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        raw = await redis_client.get(f"job:{job_id}:integrity")
        if raw:
            try:
                bundle = json.loads(raw)
            except Exception:
                bundle = {}
            if bundle.get("ai_detection") is not None and bundle.get("plagiarism") is not None:
                if "review_required" in bundle:
                    return bundle
                # Partial writes from individual tasks — keep waiting for chord callback
        await asyncio.sleep(0.4)
    logger.warning("Integrity analysis timed out for job %s", job_id)
    return {
        "ai_detection": {"score": 0.0, "flagged": False, "model_version": "ai_detector_v2", "timed_out": True},
        "plagiarism": {"overall_similarity_pct": 0.0, "top_matches": [], "model_version": "plagiarism_v1", "timed_out": True},
        "review_required": False,
        "timed_out": True,
    }
