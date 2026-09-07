import os
import sys

# Ensure /app and root directory are in Python path
sys.path.insert(0, "/app")
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import asyncio
import json
import logging
import httpx
import redis.asyncio as aioredis
from app.celery_app import celery_app
from app.config import settings
from pipeline.reasoning_rotator import RoundRobinKeyRotator
from pipeline.security import DocxSecurityPipeline
from pipeline.parser import UniversalAssignmentParser, TaskSection
from app.analysis_dispatch import dispatch_integrity_analysis, await_integrity_results, integrity_fields as build_integrity_fields
from app.persistence import ensure_grading_job

logger = logging.getLogger(__name__)


# ── Redis helpers ──────────────────────────────────────────────────────────────

async def _emit_progress(redis_client, job_id: str, stage: str, progress: int, data: dict = None):
    payload = {
        "job_id": job_id,
        "stage": stage,
        "progress": str(progress),
        "data": json.dumps(data or {}),
    }
    await redis_client.xadd(f"job:{job_id}:events", payload, maxlen=100)
    await redis_client.expire(f"job:{job_id}:events", 86400)


async def _fetch_active_api_keys(redis_client) -> list:
    try:
        keys_json = await redis_client.get("gradepro:configured_api_keys")
        if keys_json:
            keys = json.loads(keys_json)
            return [k for k in keys if k.get("active", True)]
    except Exception:
        pass
    return []


async def _load_rubric(redis_client, unit_code: str) -> dict:
    """
    Load the rubric JSON for a unit from Redis cache first, then from disk.
    Returns a dict with 'learning_outcomes', 'word_count_min', 'referencing', etc.
    """
    try:
        data = await redis_client.get(f"gradepro:rubric:{unit_code.upper()}")
        if data:
            return json.loads(data)
    except Exception:
        pass

    here = os.path.dirname(os.path.abspath(__file__))
    orchestrator_dir = os.path.dirname(here)
    gradepro_dir = os.path.dirname(os.path.dirname(orchestrator_dir))
    rubric_paths = [
        f"/app/shared/rubrics/{unit_code.upper()}_rubric.json",
        f"/app/rubrics/{unit_code.upper()}_rubric.json",
        os.path.join(gradepro_dir, "shared", "rubrics", f"{unit_code.upper()}_rubric.json"),
        os.path.join(orchestrator_dir, "shared", "rubrics", f"{unit_code.upper()}_rubric.json"),
        os.path.join(orchestrator_dir, "rubrics", f"{unit_code.upper()}_rubric.json"),
    ]
    for path in rubric_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    rubric = json.load(f)
                await redis_client.set(
                    f"gradepro:rubric:{unit_code.upper()}", json.dumps(rubric)
                )
                return rubric
            except Exception:
                pass

    return {}


def _get_task_criteria(rubric: dict, task_number: int) -> list:
    """
    Extract criteria dicts for a given task number from the rubric.
    Returns list of {
        "id", "description", "key_topics", "guidance", "refer_if",
        "action_verb", "action_verb_definition"
    }
    action_verb_definition is resolved from rubric grading_guidance.action_verbs —
    never invented; absent if the rubric does not define it.
    """
    task_label = f"Task {task_number}"
    action_verbs = rubric.get("grading_guidance", {}).get("action_verbs", {})
    criteria = []
    for lo in rubric.get("learning_outcomes", []):
        for c in lo.get("criteria", []):
            if c.get("task", "").strip().lower() == task_label.lower():
                av = c.get("action_verb", "")
                criteria.append({
                    "id": c.get("id", ""),
                    "description": c.get("description", ""),
                    "key_topics": c.get("key_topics", []),
                    "guidance": c.get("guidance", ""),
                    "refer_if": c.get("refer_if", ""),
                    "action_verb": av,
                    "action_verb_definition": action_verbs.get(av, ""),
                })
    return criteria


def _get_all_rubric_task_numbers(rubric: dict) -> list:
    """Return all unique task numbers referenced in the rubric."""
    task_nums = set()
    for lo in rubric.get("learning_outcomes", []):
        for c in lo.get("criteria", []):
            task_str = c.get("task", "")
            import re
            m = re.search(r'\d+', task_str)
            if m:
                task_nums.add(int(m.group()))
    return sorted(task_nums)


def _resolve_content_for_task(
    task_number: int,
    parsed_tasks: list,
    rubric: dict,
) -> tuple:
    """
    Smart content resolver: finds the best source of student content for a given task number.

    Strategy:
    1. Exact match — student wrote a "Task N" heading.
    2. Shared task — student wrote "Task N and Task M" heading (both use same content).
    3. Semantic match — check which task's content has the most rubric key_topic matches.
    4. Fallback — use full body or last task's content.

    Returns (content_text, task_heading, is_inferred)
    """
    # Strategy 1: Exact match
    for t in parsed_tasks:
        if t.task_number == task_number:
            return t.student_content, t.heading, False

    # Strategy 2: Find a task that is shared and covers this task number
    for t in parsed_tasks:
        if t.is_shared and t.original_heading:
            import re
            nums_in_heading = [int(m) for m in re.findall(r'\d+', t.original_heading[:60])]
            if task_number in nums_in_heading:
                return t.student_content, t.original_heading, False

    # Strategy 3: Semantic topic match
    task_criteria = _get_task_criteria(rubric, task_number)
    if task_criteria and parsed_tasks:
        key_topics_flat = []
        for c in task_criteria:
            key_topics_flat.extend(t.lower() for t in c.get("key_topics", []))

        best_task = None
        best_score = -1
        for t in parsed_tasks:
            if not t.student_content:
                continue
            text_lower = t.student_content.lower()
            score = sum(1 for topic in key_topics_flat if topic in text_lower)
            if score > best_score:
                best_score = score
                best_task = t

        if best_task and best_score > 0:
            return (
                best_task.student_content,
                f"{best_task.heading} [inferred for Task {task_number}]",
                True,
            )

    # Strategy 4: Last resort — concatenate ALL available task content so the LLM
    # can search the entire submission for evidence, rather than being anchored to
    # only the last task section (which may be completely unrelated).
    if parsed_tasks:
        combined = "\n\n".join(t.student_content for t in parsed_tasks if t.student_content)
        return (
            combined,
            f"Full Submission [inferred for Task {task_number}]",
            True,
        )

    return "", f"Task {task_number}", True


# ── Main Pipeline ──────────────────────────────────────────────────────────────

async def _execute_grading_pipeline(job_id: str, file_bytes_hex: str, unit_code: str, college: str):
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    file_bytes = bytes.fromhex(file_bytes_hex)

    try:
        # ── STEP 1: Security & Sanitisation ──
        await _emit_progress(r, job_id, "SECURITY_SCAN", 10, {
            "status": "Scanning DOCX for macros, ActiveX, and malicious payloads",
            "bytes_scanned": len(file_bytes),
        })
        pipeline = DocxSecurityPipeline()
        sanitized_bytes = pipeline.run(file_bytes)

        # ── STEP 2: Parse & Boundary Extraction ──
        await _emit_progress(r, job_id, "PARSING", 20, {
            "status": "Extracting clean academic body (Intro to Conclusion), citations, and metadata"
        })
        parser = UniversalAssignmentParser()
        parsed = parser.parse(sanitized_bytes)

        format_warnings = []
        if not parsed.header.learner_name:
            format_warnings.append("Learner name is missing from the document header table")
        if not parsed.header.qualification:
            format_warnings.append("Qualification / Course title is missing from header")
        if not parsed.header.unit_code:
            format_warnings.append(f"Unit code not found in header (using: {unit_code})")

        # Note any merged/shared task headings
        shared_tasks = [t for t in parsed.tasks if t.is_shared]
        if shared_tasks:
            for t in shared_tasks:
                format_warnings.append(
                    f"Learner combined tasks in one section: '{t.original_heading}'. "
                    f"All relevant criteria have been evaluated against this combined content."
                )

        active_unit = parsed.header.unit_code or unit_code or "HSC301"

        # If truly no tasks detected, treat full clean body as one task section
        if not parsed.tasks:
            all_text = parsed.clean_academic_body
            if not all_text:
                import docx as _docx, io as _io
                doc_raw = _docx.Document(_io.BytesIO(sanitized_bytes))
                all_text = "\n\n".join(p.text.strip() for p in doc_raw.paragraphs if p.text.strip())
            parsed.tasks = [TaskSection(
                task_number=1,
                heading="Submission Content",
                student_content=all_text,
                word_count=len(all_text.split()),
            )]
            format_warnings.append(
                "Standard task headings were not detected — evaluating full body content across all criteria."
            )

        clean_words = parsed.clean_word_count
        extracted_metadata = {
            "learner_name":     parsed.header.learner_name or "Not Specified",
            "learner_id":       parsed.header.learner_id or "N/A",
            "centre_name":      parsed.header.centre_name or college,
            "qualification":    parsed.header.qualification or "Not Specified",
            "awarding_body":    parsed.header.awarding_body or "QUALIFI",
            "unit_code":        active_unit,
            "unit_name":        parsed.header.unit_name or "Unit",
            "submission_date":  parsed.header.submission_date or "N/A",
            "college":          parsed.college or college,
            "tasks_count":      len(parsed.tasks),
            "has_intro":        bool(parsed.introduction),
            "has_conclusion":   bool(parsed.conclusion),
            "has_bibliography": parsed.citation_stats.has_bibliography,
            "clean_word_count": clean_words,
            "in_text_citations": parsed.citation_stats.in_text_count,
            "citation_stats": {
                "in_text_count": parsed.citation_stats.in_text_count,
                "bibliography_count": parsed.citation_stats.bibliography_count,
                "has_bibliography": parsed.citation_stats.has_bibliography,
            },
            "format_warnings": format_warnings,
        }

        await _emit_progress(r, job_id, "PARSING", 30, {
            "status": (
                f"Parsed: {extracted_metadata['learner_name']} | {active_unit} | "
                f"{clean_words} body words | {parsed.citation_stats.in_text_count} citations"
            ),
            "metadata": extracted_metadata,
            "tasks_found": [
                {
                    "task_number": t.task_number,
                    "heading": t.heading,
                    "word_count": t.word_count,
                    "is_shared": t.is_shared,
                }
                for t in parsed.tasks
            ],
        })

        student_text = parsed.clean_academic_body or " ".join(
            t.student_content for t in parsed.tasks if t.student_content
        )
        try:
            await ensure_grading_job(
                job_id,
                student_name=extracted_metadata["learner_name"],
                file_hash=job_id,
                file_path_r2=f"local/{job_id}.docx",
                status="evaluating",
            )
        except Exception:
            pass
        dispatch_integrity_analysis(job_id, student_text)
        await _emit_progress(r, job_id, "INTEGRITY_DISPATCH", 35, {
            "status": "AI detection and plagiarism checks running in parallel with evaluation",
        })

        # ── STEP 3: Format & Citation Validation ──
        citation_warning = None
        if not parsed.citation_stats.has_bibliography:
            citation_warning = "No Bibliography / Reference section detected in the submission."
            format_warnings.append(citation_warning)
        elif parsed.citation_stats.in_text_count == 0:
            citation_warning = "No Harvard in-text citations detected in the body text."
            format_warnings.append(citation_warning)

        await _emit_progress(r, job_id, "FORMAT_VALIDATION", 40, {
            "status": (
                f"Font: {parsed.format_summary.get('primary_font', 'N/A')} "
                f"({parsed.format_summary.get('body_font_size_pt', '?')}pt) | "
                f"Citations: {parsed.citation_stats.in_text_count} found"
            ),
            "format": parsed.format_summary,
            "citation_stats": extracted_metadata["citation_stats"],
            "format_warnings": format_warnings,
        })

        # ── STEP 4: Load Dynamic Rubric + API keys ──
        rubric = await _load_rubric(r, active_unit)

        # Hard fail — no rubric means no grading. Never fall back to keyword guessing.
        if not rubric or not rubric.get("learning_outcomes"):
            error_msg = (
                f"Rubric for unit '{active_unit}' could not be loaded or is empty. "
                f"Grading cannot proceed without a valid rubric. "
                f"Please upload the rubric JSON for this unit and retry."
            )
            await _emit_progress(r, job_id, "FAILED", 0, {"error": error_msg})
            raise RuntimeError(error_msg)

        active_keys = await _fetch_active_api_keys(r)

        # ── STEP 5: Dynamic Rubric Word Count Gating (Fast-Fail Early Exit) ──
        min_words_required = rubric.get("word_count_min", 0)
        tolerance_min = int(min_words_required * 0.90) if min_words_required > 0 else 0

        # If word count is severely below dynamic minimum requirement, early exit with REFER
        if min_words_required > 0 and clean_words < tolerance_min and clean_words > 0:
            word_count_fail_msg = (
                f"Word count requirement not met: The submission contains {clean_words} body words "
                f"(excluding references and header tables), which falls significantly below the mandatory "
                f"minimum of {min_words_required} words for Unit {active_unit}."
            )
            format_warnings.append(word_count_fail_msg)

            await _emit_progress(r, job_id, "WORD_COUNT_GATE", 60, {
                "status": f"Word count below minimum ({clean_words} / {min_words_required} words) — issuing refer",
                "clean_words": clean_words,
                "min_required": min_words_required,
                "verdict": "refer",
            })

            # Build fast referral task results
            rubric_task_numbers = _get_all_rubric_task_numbers(rubric) or [1]
            task_results = []
            all_per_criterion = {}
            for tn in rubric_task_numbers:
                task_crits = _get_task_criteria(rubric, tn)
                per_crit = {}
                for c in task_crits:
                    cid = c.get("id", str(tn))
                    per_crit[cid] = {
                        "verdict": "refer",
                        "confidence": 1.0,
                        "feedback": (
                            f"Criterion {cid} cannot be fully verified due to substantial word count deficit. "
                            f"The overall submission ({clean_words} words) is below the minimum required "
                            f"({min_words_required} words). Please expand with detailed analysis and examples upon resubmission."
                        ),
                        "evidence_quote": "Insufficient length to demonstrate criteria depth.",
                    }
                    all_per_criterion[cid] = per_crit[cid]

                task_results.append({
                    "task_number": tn,
                    "task_heading": f"Task {tn}",
                    "content_inferred": False,
                    "verdict": "refer",
                    "confidence": 1.0,
                    "feedback_text": (
                        f"Task {tn} requires resubmission due to overall word count deficit. "
                        f"Please ensure all required learning outcomes are developed in full paragraphs."
                    ),
                    "per_criterion": per_crit,
                    "word_count": clean_words // len(rubric_task_numbers),
                    "provider": "Word Count Gatekeeper",
                    "criteria": task_crits,
                })

            overall_comment = (
                f"{extracted_metadata['learner_name']}'s submission for Unit {active_unit} "
                f"({extracted_metadata['unit_name']}) requires resubmission. "
                f"The submission total of {clean_words} words is significantly below the minimum requirement "
                f"of {min_words_required} words specified in the unit brief. "
                f"To achieve a Pass, please expand all task responses with supporting academic literature, "
                f"relevant legislation, and practical workplace examples, ensuring all assessment criteria are fully met."
            )

            integrity = await await_integrity_results(r, job_id)
            integrity_fields = build_integrity_fields(integrity)

            # Generate PDF and finish
            pdf_url = f"/api/v1/jobs/{job_id}/pdf"
            docx_url = f"/api/v1/jobs/{job_id}/docx"
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    pdf_resp = await client.post(
                        f"{settings.PDF_SERVICE_URL}/generate",
                        json={
                            "job_id":          job_id,
                            "unit_code":       active_unit,
                            "student_name":    extracted_metadata["learner_name"],
                            "student_id":      extracted_metadata["learner_id"],
                            "college":         extracted_metadata["college"],
                            "verdict":         "refer",
                            "tasks":           task_results,
                            "per_criterion":   all_per_criterion,
                            "overall_comment": overall_comment,
                            "format_warnings": format_warnings,
                            "rubric":          rubric,
                            **integrity_fields,
                        },
                    )
                    if pdf_resp.status_code == 200:
                        pdf_data = pdf_resp.json()
                        pdf_url = pdf_data.get("pdf_url", pdf_url)
                        docx_url = pdf_data.get("docx_url", docx_url)
            except Exception as e:
                logger.warning(f"PDF generation error: {e}")

            await _emit_progress(r, job_id, "COMPLETE", 100, {
                "status": "Grading complete (Refer due to word count deficit)",
                "verdict": "refer",
                "pdf_url": pdf_url,
                "docx_url": docx_url,
                "tasks": task_results,
                "per_criterion": all_per_criterion,
                "metadata": extracted_metadata,
                "overall_comment": overall_comment,
                "format_warnings": format_warnings,
                **integrity_fields,
            })
            return

        # Determine which task numbers the rubric expects
        rubric_task_numbers = _get_all_rubric_task_numbers(rubric)
        detected_task_numbers = [t.task_number for t in parsed.tasks]

        missing_rubric_tasks = [n for n in rubric_task_numbers if n not in detected_task_numbers]
        if missing_rubric_tasks:
            for n in missing_rubric_tasks:
                format_warnings.append(
                    f"Task {n} heading was not explicitly found — criteria evaluated against matching body content."
                )

        await _emit_progress(r, job_id, "EVALUATION", 50, {
            "status": (
                f"Activating deterministic evaluator for {active_unit} (Temp: 0.0) | "
                f"{len(active_keys)} key(s) in rotation | "
                f"Rubric: {'loaded (' + str(len(rubric_task_numbers)) + ' tasks)' if rubric else 'not found'}"
            ),
            "rubric_tasks": rubric_task_numbers,
            "detected_tasks": detected_task_numbers,
        })

        rotator = RoundRobinKeyRotator(redis_url=settings.REDIS_URL)

        # ── STEP 6: Deterministic Evidence-First Task Evaluation ──
        eval_task_numbers = rubric_task_numbers if rubric_task_numbers else detected_task_numbers
        if not eval_task_numbers:
            eval_task_numbers = [t.task_number for t in parsed.tasks]

        async def evaluate_rubric_task(task_number: int, eval_idx: int) -> dict:
            content_text, heading_used, was_inferred = _resolve_content_for_task(
                task_number, parsed.tasks, rubric
            )
            task_criteria = _get_task_criteria(rubric, task_number)

            if not task_criteria:
                matching_tasks = [t for t in parsed.tasks if t.task_number == task_number]
                if matching_tasks and matching_tasks[0].sub_criteria:
                    task_criteria = [
                        {"id": "", "description": c, "key_topics": []}
                        for c in matching_tasks[0].sub_criteria
                    ]

            eval_res = await rotator.evaluate_task_with_rotation(
                task_text=content_text,
                task_heading=heading_used,
                criteria_list=task_criteria,
                unit_code=active_unit,
                active_keys=active_keys,
                citation_context=extracted_metadata["citation_stats"],
            )

            prog = 50 + int((eval_idx + 1) / max(len(eval_task_numbers), 1) * 30)

            await _emit_progress(r, job_id, f"TASK_{task_number}", prog, {
                "status": (
                    f"Task {task_number}: {eval_res['verdict'].upper()} "
                    f"({eval_res.get('provider', 'Engine')}) "
                    + ("[inferred content]" if was_inferred else "")
                ),
                "task": task_number,
                "heading": heading_used,
                "content_inferred": was_inferred,
                "word_count": len(content_text.split()),
                "verdict": eval_res["verdict"],
                "confidence": eval_res.get("confidence", 0.0),
                "provider": eval_res.get("provider", "Engine"),
                "feedback": eval_res["feedback"],
                "per_criterion": eval_res.get("per_criterion", {}),
                "criteria_evaluated": len(task_criteria),
            })

            return {
                "task_number":     task_number,
                "task_heading":    heading_used,
                "content_inferred": was_inferred,
                "verdict":         eval_res["verdict"],
                "confidence":      eval_res.get("confidence", 0.0),
                "feedback_text":   eval_res["feedback"],
                "per_criterion":   eval_res.get("per_criterion", {}),
                "word_count":      len(content_text.split()),
                "provider":        eval_res.get("provider", ""),
                "criteria":        task_criteria,
            }

        task_results = list(
            await asyncio.gather(
                *[
                    evaluate_rubric_task(task_number, eval_idx)
                    for eval_idx, task_number in enumerate(eval_task_numbers)
                ]
            )
        )

        # ── STEP 7: Final Verdict ──
        overall_pass = all(t["verdict"] == "pass" for t in task_results)
        final_verdict = "pass" if overall_pass else "refer"

        all_per_criterion: dict = {}
        for task_result in task_results:
            task_num = task_result.get("task_number", 0)
            for cid, cval in task_result.get("per_criterion", {}).items():
                # Namespace by task number on collision so no criterion is silently overwritten
                key = cid if cid not in all_per_criterion else f"T{task_num}_{cid}"
                all_per_criterion[key] = cval

        await _emit_progress(r, job_id, "DECISION", 82, {
            "status": f"Final decision: {final_verdict.upper()}",
            "verdict": final_verdict,
            "tasks": task_results,
            "per_criterion": all_per_criterion,
            "format_warnings": format_warnings,
        })

        # ── STEP 8: Generate Authentic UK Assessor Overall Comment ──
        await _emit_progress(r, job_id, "OVERALL_COMMENT", 88, {
            "status": "Generating official assessor overall summary",
        })
        overall_comment = await rotator.generate_overall_comment(
            student_name=extracted_metadata["learner_name"],
            unit_code=active_unit,
            unit_name=extracted_metadata["unit_name"],
            task_results=task_results,
            final_verdict=final_verdict,
            active_keys=active_keys,
            citation_context=extracted_metadata["citation_stats"],
        )

        # ── STEP 9: Wait for parallel integrity chord, then render report ──
        integrity = await await_integrity_results(r, job_id)
        integrity_fields = build_integrity_fields(integrity)
        if integrity_fields["review_required"]:
            format_warnings.append(
                "Academic integrity warning: MAIN_ASSESSOR review is required before this verdict is finalised. "
                "AI-generated content and/or plagiarism similarity crossed the configured threshold. "
                "The academic Pass/Refer decision was not auto-failed."
            )

        await _emit_progress(r, job_id, "PDF_GENERATION", 92, {
            "status": "Rendering official assessor feedback report",
            **integrity_fields,
        })

        pdf_url = f"/api/v1/jobs/{job_id}/pdf"
        docx_url = f"/api/v1/jobs/{job_id}/docx"
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                pdf_resp = await client.post(
                    f"{settings.PDF_SERVICE_URL}/generate",
                    json={
                        "job_id":          job_id,
                        "unit_code":       active_unit,
                        "student_name":    extracted_metadata["learner_name"],
                        "student_id":      extracted_metadata["learner_id"],
                        "college":         extracted_metadata["college"],
                        "verdict":         final_verdict,
                        "tasks":           task_results,
                        "per_criterion":   all_per_criterion,
                        "overall_comment": overall_comment,
                        "format_warnings": format_warnings,
                        "rubric":          rubric,
                        **integrity_fields,
                    },
                )
                if pdf_resp.status_code == 200:
                    pdf_data = pdf_resp.json()
                    pdf_url = pdf_data.get("pdf_url", pdf_url)
                    docx_url = pdf_data.get("docx_url", docx_url)
        except Exception as e:
            logger.warning(f"PDF generation error: {e}")

        await _emit_progress(r, job_id, "COMPLETE", 100, {
            "status": "Grading complete — MAIN_ASSESSOR review required" if integrity_fields["review_required"] else "Grading complete",
            "verdict": final_verdict,
            "pdf_url": pdf_url,
            "docx_url": docx_url,
            "tasks": task_results,
            "per_criterion": all_per_criterion,
            "metadata": extracted_metadata,
            "overall_comment": overall_comment,
            "format_warnings": format_warnings,
            **integrity_fields,
        })

    except Exception as e:
        logger.exception("Grading pipeline failure")
        await _emit_progress(r, job_id, "FAILED", 0, {"error": str(e)})
        raise
    finally:
        await r.close()


@celery_app.task(bind=True, acks_late=True, queue="grading_queue", max_retries=3)
def process_grading_job(self, job_id: str, file_bytes_hex: str, unit_code: str, college: str):
    asyncio.run(_execute_grading_pipeline(job_id, file_bytes_hex, unit_code, college))
