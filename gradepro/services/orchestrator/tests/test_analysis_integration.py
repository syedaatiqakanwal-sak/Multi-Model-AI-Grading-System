"""Additive integrity-analysis tests — grading_queue dispatch shape is unchanged."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.analysis_dispatch import compute_review_required, integrity_fields
from app.celery_app import celery_app


def test_analysis_queue_is_routed_independently():
    routes = celery_app.conf.task_routes
    assert routes["app.tasks.analysis_tasks.*"]["queue"] == "analysis_queue"
    assert routes["workers.grading.*"]["queue"] == "grading_queue"
    assert "app.tasks.analysis_tasks" in celery_app.conf.include


def test_review_required_does_not_imply_auto_fail():
    assert compute_review_required({"score": 0.9, "flagged": True}, {"overall_similarity_pct": 5}) is True
    assert compute_review_required({"score": 0.2, "flagged": False}, {"overall_similarity_pct": 35}) is True
    assert compute_review_required({"score": 0.2, "flagged": False}, {"overall_similarity_pct": 5}) is False


def test_integrity_fields_passthrough():
    fields = integrity_fields({
        "ai_detection": {"score": 0.81, "flagged": True},
        "plagiarism": {"overall_similarity_pct": 12.0, "top_matches": []},
        "review_required": True,
    })
    assert fields["review_required"] is True
    assert fields["ai_detection"]["flagged"] is True
    assert fields["review_roles"] == ["ADMIN", "MAIN_ASSESSOR"]


def test_plagiarism_empty_corpus_skips_model():
    pytest = __import__("pytest")
    try:
        from app.services.plagiarism_service import check_plagiarism
    except ModuleNotFoundError:
        pytest.skip("sentence-transformers not installed in this environment")

    result = check_plagiarism("student text", [])
    assert result["overall_similarity_pct"] == 0.0
    assert result["top_matches"] == []
    assert result.get("corpus_empty") is True


def test_thresholds_env_defaults():
    assert float(os.getenv("AI_DETECTION_REFER_THRESHOLD", "0.7")) == 0.7
    assert float(os.getenv("PLAGIARISM_REFER_THRESHOLD", "20")) == 20.0
