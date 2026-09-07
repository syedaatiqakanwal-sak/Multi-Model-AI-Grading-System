import json
import logging
import os
from typing import Any, Dict, List, Optional

import redis as sync_redis
from app.analysis_dispatch import compute_review_required
from app.celery_app import celery_app
from app.config import settings
from app.persistence import persist_ai_detection_sync, persist_plagiarism_sync

logger = logging.getLogger(__name__)


def _emit(job_id: str, stage: str, progress: int, data: dict) -> None:
    r = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        r.xadd(
            f"job:{job_id}:events",
            {
                "job_id": job_id,
                "stage": stage,
                "progress": str(progress),
                "data": json.dumps(data or {}),
            },
            maxlen=100,
        )
        r.expire(f"job:{job_id}:events", 86400)
    finally:
        r.close()


def _store_integrity_partial(job_id: str, key: str, payload: dict) -> dict:
    r = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        raw = r.get(f"job:{job_id}:integrity")
        bundle = json.loads(raw) if raw else {}
        bundle[key] = payload
        r.set(f"job:{job_id}:integrity", json.dumps(bundle), ex=86400)
        return bundle
    finally:
        r.close()


@celery_app.task(bind=True, acks_late=True, queue="analysis_queue", name="app.tasks.analysis_tasks.ai_detection_task")
def ai_detection_task(self, job_id: str, student_text: str) -> Dict[str, Any]:
    from app.services.ai_detection_service import detect_ai_content

    _emit(job_id, "AI_DETECTION", 55, {"status": "Running AI-content detector"})
    try:
        result = detect_ai_content(student_text or "")
    except Exception as exc:
        logger.exception("AI detection failed")
        result = {
            "score": 0.0,
            "flagged": False,
            "model_version": "ai_detector_v2",
            "error": str(exc),
        }
    persist_ai_detection_sync(job_id, result)
    _store_integrity_partial(job_id, "ai_detection", result)
    _emit(job_id, "AI_DETECTION", 70, {
        "status": f"AI detection score {result.get('score', 0):.2f}",
        **result,
    })
    return result


@celery_app.task(bind=True, acks_late=True, queue="analysis_queue", name="app.tasks.analysis_tasks.plagiarism_task")
def plagiarism_task(
    self,
    job_id: str,
    student_text: str,
    reference_corpus: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    from app.services.plagiarism_service import check_plagiarism, load_reference_corpus

    _emit(job_id, "PLAGIARISM_CHECK", 55, {"status": "Running plagiarism similarity check"})
    corpus = reference_corpus or load_reference_corpus()
    try:
        result = check_plagiarism(student_text or "", corpus)
    except Exception as exc:
        logger.exception("Plagiarism check failed")
        result = {
            "overall_similarity_pct": 0.0,
            "top_matches": [],
            "model_version": "plagiarism_v1",
            "error": str(exc),
        }
    persist_plagiarism_sync(job_id, result)
    _store_integrity_partial(job_id, "plagiarism", result)
    _emit(job_id, "PLAGIARISM_CHECK", 70, {
        "status": f"Plagiarism similarity {result.get('overall_similarity_pct', 0):.1f}%",
        **result,
    })
    return result


@celery_app.task(bind=True, queue="analysis_queue", name="app.tasks.analysis_tasks.finalize_integrity_task")
def finalize_integrity_task(self, header_results, job_id: str) -> Dict[str, Any]:
    """Chord callback: header_results is [ai_detection_dict, plagiarism_dict]."""
    ai_result: Dict[str, Any] = {}
    plag_result: Dict[str, Any] = {}
    if isinstance(header_results, (list, tuple)):
        for item in header_results:
            if not isinstance(item, dict):
                continue
            if "score" in item and "flagged" in item:
                ai_result = item
            if "overall_similarity_pct" in item:
                plag_result = item

    ai_threshold = float(os.getenv("AI_DETECTION_REFER_THRESHOLD", "0.7"))
    plag_threshold = float(os.getenv("PLAGIARISM_REFER_THRESHOLD", "20"))
    review_required = compute_review_required(ai_result, plag_result, ai_threshold, plag_threshold)

    bundle = {
        "ai_detection": ai_result,
        "plagiarism": plag_result,
        "review_required": review_required,
        "review_roles": ["ADMIN", "MAIN_ASSESSOR"],
        "thresholds": {
            "ai_detection": ai_threshold,
            "plagiarism_pct": plag_threshold,
        },
    }
    r = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        r.set(f"job:{job_id}:integrity", json.dumps(bundle), ex=86400)
    finally:
        r.close()

    _emit(job_id, "INTEGRITY", 75, {
        "status": "Integrity analysis complete — MAIN_ASSESSOR review required" if review_required else "Integrity analysis complete",
        **bundle,
    })
    return bundle
