import asyncio
import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _session_factory():
    from app.database import AsyncSessionFactory
    from sqlalchemy import text
    return AsyncSessionFactory, text


async def ensure_grading_job(
    job_id: str,
    student_name: str = "Pending parse",
    file_hash: str = "pending",
    file_path_r2: str = "pending",
    unit_code: str = "",
    college: str = "",
    status: str = "pending",
) -> None:
    try:
        AsyncSessionFactory, text = _session_factory()
        async with AsyncSessionFactory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO grading_jobs (id, student_name, file_hash, file_path_r2, status)
                    VALUES (CAST(:id AS uuid), :name, :hash, :path, :status)
                    ON CONFLICT (id) DO UPDATE SET
                        student_name = EXCLUDED.student_name,
                        status = EXCLUDED.status,
                        updated_at = NOW()
                    """
                ),
                {
                    "id": job_id,
                    "name": student_name or "Pending parse",
                    "hash": file_hash or "pending",
                    "path": file_path_r2 or f"local/{job_id}.docx",
                    "status": status,
                },
            )
            await session.commit()
    except Exception as exc:
        logger.warning("ensure_grading_job skipped (Postgres unavailable): %s", exc)


async def persist_ai_detection(job_id: str, result: Dict[str, Any]) -> None:
    try:
        await ensure_grading_job(job_id)
        AsyncSessionFactory, text = _session_factory()
        async with AsyncSessionFactory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO ai_detection_results (job_id, model_version, score, flagged)
                    VALUES (CAST(:job_id AS uuid), :model_version, :score, :flagged)
                    """
                ),
                {
                    "job_id": job_id,
                    "model_version": result.get("model_version", "ai_detector_v2"),
                    "score": float(result.get("score", 0.0)),
                    "flagged": bool(result.get("flagged", False)),
                },
            )
            await session.commit()
    except Exception as exc:
        logger.warning("persist_ai_detection skipped: %s", exc)


async def persist_plagiarism(job_id: str, result: Dict[str, Any]) -> None:
    try:
        await ensure_grading_job(job_id)
        AsyncSessionFactory, text = _session_factory()
        async with AsyncSessionFactory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO plagiarism_results
                        (job_id, model_version, overall_similarity_pct, top_matches)
                    VALUES
                        (CAST(:job_id AS uuid), :model_version, :pct, CAST(:matches AS jsonb))
                    """
                ),
                {
                    "job_id": job_id,
                    "model_version": result.get("model_version", "plagiarism_v1"),
                    "pct": float(result.get("overall_similarity_pct", 0.0)),
                    "matches": json.dumps(result.get("top_matches") or []),
                },
            )
            await session.commit()
    except Exception as exc:
        logger.warning("persist_plagiarism skipped: %s", exc)


def persist_ai_detection_sync(job_id: str, result: Dict[str, Any]) -> None:
    asyncio.run(persist_ai_detection(job_id, result))


def persist_plagiarism_sync(job_id: str, result: Dict[str, Any]) -> None:
    asyncio.run(persist_plagiarism(job_id, result))


def ensure_grading_job_sync(**kwargs) -> None:
    asyncio.run(ensure_grading_job(**kwargs))
