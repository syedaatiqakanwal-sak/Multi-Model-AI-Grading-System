import asyncio
import json
import logging
from typing import List, Dict, Any, Optional

import httpx
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# ── Pass/Refer thresholds ──────────────────────────────────────────────────────
# A criterion is PASS if confidence >= 0.50 and verdict is 'pass'.
# A task is PASS only if ALL criteria in that task pass (strict UK awarding body policy).
# The overall submission is PASS only if all tasks pass.
CRITERION_PASS_THRESHOLD = 0.50


class LLMProviderClient:
    """
    Unified multi-provider LLM client supporting OpenAI, Anthropic, Gemini,
    Groq, DeepSeek, and custom OpenAI-compatible endpoints with deterministic
    zero-temperature execution.
    """

    SYSTEM_PROMPT = (
        "You are an experienced, professional UK Higher Education & Further Education "
        "academic assessor grading qualification assignments according to strict UK "
        "Awarding Body standards (e.g. Qualifi, OTHM, NOCN). You assess learner submissions "
        "with academic rigor, fairness, and constructive precision. Never mention word counts. "
        "When a criterion is met, acknowledge the specific concepts, legislation, and models applied. "
        "When a criterion requires resubmission, provide clear, actionable guidance on what "
        "academic theory, evidence, or legislation is needed. Be fair: if a learner has addressed "
        "the key points of a criterion with valid explanation, that is a PASS. Only give REFER if "
        "the required criterion content is genuinely absent, factually incorrect, or superficial."
    )

    @staticmethod
    async def call_llm(
        provider: str,
        api_key: str,
        model_name: str,
        prompt: str,
        system_prompt: str = None,
        timeout_seconds: float = 40.0,
        is_json: bool = True,
    ) -> Dict[str, Any]:
        provider = provider.lower().strip()
        sys_prompt = system_prompt or LLMProviderClient.SYSTEM_PROMPT

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:

            # 1. OpenAI / Groq / DeepSeek / Custom (OpenAI-compatible)
            if provider in ["openai", "groq", "deepseek", "custom"]:
                base_url = "https://api.openai.com/v1"
                if provider == "groq":
                    base_url = "https://api.groq.com/openai/v1"
                elif provider == "deepseek":
                    base_url = "https://api.deepseek.com/v1"

                default_model = {
                    "openai": "gpt-4o",
                    "groq": "llama-3.3-70b-versatile",
                    "deepseek": "deepseek-chat",
                    "custom": "gpt-4o",
                }.get(provider, "gpt-4o")

                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }
                body: Dict[str, Any] = {
                    "model": model_name or default_model,
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.0,  # Strictly deterministic
                }
                if is_json and provider in ["openai", "groq"]:
                    body["response_format"] = {"type": "json_object"}

                resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=body)
                if resp.status_code != 200:
                    raise Exception(f"{provider.upper()} API Error ({resp.status_code}): {resp.text[:300]}")
                text = resp.json()["choices"][0]["message"]["content"]
                return {"text": text, "provider": provider, "model": model_name or default_model}

            # 2. Anthropic Claude
            elif provider == "anthropic":
                default_model = "claude-3-5-sonnet-20241022"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                }
                body = {
                    "model": model_name or default_model,
                    "max_tokens": 4096,
                    "system": sys_prompt,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,  # Strictly deterministic
                }
                resp = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=body)
                if resp.status_code != 200:
                    raise Exception(f"Anthropic API Error ({resp.status_code}): {resp.text[:300]}")
                text = resp.json()["content"][0]["text"]
                return {"text": text, "provider": "anthropic", "model": model_name or default_model}

            # 3. Google Gemini
            elif provider == "gemini":
                model = model_name or "gemini-1.5-pro"
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:generateContent?key={api_key}"
                )
                body = {
                    "system_instruction": {"parts": [{"text": sys_prompt}]},
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.0,  # Strictly deterministic
                    },
                }
                if is_json:
                    body["generationConfig"]["response_mime_type"] = "application/json"

                resp = await client.post(url, json=body)
                if resp.status_code != 200:
                    raise Exception(f"Gemini API Error ({resp.status_code}): {resp.text[:300]}")
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                return {"text": text, "provider": "gemini", "model": model}

            else:
                raise ValueError(f"Unsupported LLM provider: {provider}")


class RoundRobinKeyRotator:
    """
    Manages dynamic API key pool with atomic Round-Robin dispatch and
    automatic circuit-breaker failover.
    """

    def __init__(self, redis_url: str = "redis://redis:6379/0"):
        self.redis_url = redis_url

    async def get_next_key(self, active_keys: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Atomically picks the next active key via Redis counter."""
        if not active_keys:
            return None
        try:
            r = aioredis.from_url(self.redis_url, decode_responses=True)
            counter = await r.incr("gradepro:api_rotation_idx")
            await r.close()
            return active_keys[counter % len(active_keys)]
        except Exception:
            return active_keys[0]

    # ── Core Per-Task Evaluation ───────────────────────────────────────────────

    async def evaluate_task_with_rotation(
        self,
        task_text: str,
        task_heading: str,
        criteria_list: List[Dict[str, Any]],
        unit_code: str,
        active_keys: List[Dict[str, Any]],
        citation_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluates a task against all its rubric criteria using deterministic evidence-first
        LLM reasoning.

        The task verdict is PASS only if ALL criteria in that task pass (strict rule).
        A single criterion refer causes the whole task to refer — all learning
        outcomes must be met per UK awarding body policy.
        """
        word_count = len(str(task_text).split())
        clean_content = str(task_text).strip()

        # Hard reject: genuinely empty submission
        if word_count < 40 or len(clean_content) < 150:
            empty_feedback = {
                c.get("id", str(i)): {
                    "student_evidence_quote": "None found — section is empty.",
                    "verdict": "refer",
                    "confidence": 1.0,
                    "feedback": (
                        f"Criterion {c.get('id', '')} requires resubmission. The learner has not provided "
                        f"a substantive response for this criterion. A detailed academic discussion addressing "
                        f"the required concepts is required."
                    ),
                }
                for i, c in enumerate(criteria_list)
            } if criteria_list else {}

            return {
                "verdict": "refer",
                "confidence": 1.0,
                "feedback": (
                    f"This task requires resubmission. The learner has not provided a substantive response for "
                    f"{task_heading}. A comprehensive academic submission addressing all criteria is required."
                ),
                "per_criterion": empty_feedback,
                "provider": "Academic Validator",
            }

        # Dummy text detector
        dummy_markers = {"test", "testing", "asdf", "lorem ipsum", "sample text", "dummy", "n/a", "no answer"}
        if clean_content.lower().strip() in dummy_markers:
            return {
                "verdict": "refer",
                "confidence": 1.0,
                "feedback": "Placeholder or dummy text detected. The required assessment criteria were not addressed.",
                "per_criterion": {},
                "provider": "Academic Validator",
            }

        # LLM evaluation with per-criterion breakdown
        if active_keys and criteria_list:
            result = await self._llm_evaluate_per_criterion(
                task_text=task_text,
                task_heading=task_heading,
                criteria_list=criteria_list,
                unit_code=unit_code,
                active_keys=active_keys,
                citation_context=citation_context,
            )
            if result:
                return result

        # Fallback: rule-based per-criterion keyword matching when no LLM keys are configured
        return self._fallback_evaluate(
            task_text=task_text,
            task_heading=task_heading,
            criteria_list=criteria_list,
            unit_code=unit_code,
        )

    async def _llm_evaluate_per_criterion(
        self,
        task_text: str,
        task_heading: str,
        criteria_list: List[Dict[str, Any]],
        unit_code: str,
        active_keys: List[Dict[str, Any]],
        citation_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Deterministic, Evidence-First LLM evaluation.
        Forces the LLM to extract direct evidence quotes from the student's text
        before rendering each criterion verdict.
        """
        criteria_block = ""
        criterion_ids = []
        for c in criteria_list:
            cid = c.get("id", "")
            desc = c.get("description", "")
            topics = c.get("key_topics", [])
            guidance = c.get("guidance", "")
            refer_triggers = c.get("refer_if", "")
            action_verb = c.get("action_verb", "")
            action_verb_def = c.get("action_verb_definition", "")
            topics_str = ", ".join(topics) if topics else "N/A"

            criteria_block += f'  • Criterion {cid}: "{desc}"\n'
            if action_verb and action_verb_def:
                # Rubric-defined meaning — tells the LLM exactly what the awarding body
                # expects for this action verb, not the LLM's own interpretation.
                criteria_block += f'    Action Verb ({action_verb.upper()}): {action_verb_def}\n'
            criteria_block += f'    Key Concepts & Legislation: {topics_str}\n'
            if guidance:
                criteria_block += f'    Assessor Guidance: {guidance}\n'
            if refer_triggers:
                criteria_block += f'    Refer Triggers: {refer_triggers}\n'
            criteria_block += "\n"
            criterion_ids.append(cid)

        example_json = json.dumps({
            cid: {
                "student_evidence_quote": "1-2 sentence verbatim quote from the student text demonstrating where this was answered (or 'None found' if absent)",
                "verdict": "pass or refer",
                "confidence": 0.95,
                "feedback": "2-3 sentences of professional UK academic assessor feedback referencing the specific theories, concepts, or legislation discussed."
            }
            for cid in criterion_ids
        }, indent=2)

        citation_info = ""
        if citation_context:
            citation_info = (
                f"CITATION & REFERENCE METADATA:\n"
                f"- In-text citations found across assignment: {citation_context.get('in_text_count', 0)}\n"
                f"- Bibliography present: {'Yes' if citation_context.get('has_bibliography') else 'No'}\n\n"
            )

        prompt = (
            f"You are grading a UK qualification assignment submission for Unit {unit_code}.\n\n"
            f"TASK: {task_heading}\n\n"
            f"ASSESSMENT CRITERIA FOR THIS TASK:\n{criteria_block}"
            f"{citation_info}"
            f"STUDENT SUBMISSION CONTENT:\n\"\"\"\n{task_text}\n\"\"\"\n\n"
            f"GRADING INSTRUCTIONS:\n"
            f"1. Read the student submission carefully against the criteria.\n"
            f"2. For EACH criterion listed above:\n"
            f"   a. First, locate and quote the exact sentence(s) in the student submission that address this criterion ('student_evidence_quote'). If the student genuinely did not address this criterion, write 'None found'.\n"
            f"   b. Decide verdict: 'pass' or 'refer'. Apply fair UK awarding body standards: if the learner has addressed the key points and concepts (even with minor imperfections), that is a PASS. Only give REFER if the criterion content is genuinely absent, factually incorrect, or purely superficial.\n"
            f"   c. Write 2–3 sentences of specific, constructive assessor feedback ('feedback') that directly references what the student wrote — mention specific concepts, legislation, or theories. Do NOT copy the criterion description verbatim. Do NOT mention word counts.\n"
            f"   d. Assign confidence between 0.0 and 1.0.\n\n"
            f"Return ONLY valid JSON matching this exact structure (no markdown formatting, no extra keys):\n"
            f"{example_json}"
        )

        for attempt in range(len(active_keys)):
            key_info = await self.get_next_key(active_keys)
            if not key_info:
                break
            try:
                res = await LLMProviderClient.call_llm(
                    provider=key_info["provider"],
                    api_key=key_info["key"],
                    model_name=key_info.get("model", ""),
                    prompt=prompt,
                    is_json=True,
                )
                raw_text = res["text"]

                json_start = raw_text.find("{")
                json_end = raw_text.rfind("}") + 1
                if json_start == -1 or json_end == 0:
                    raise ValueError("No JSON object found in response")

                parsed: Dict[str, Dict] = json.loads(raw_text[json_start:json_end])
                provider_label = f"{key_info['provider'].title()} ({key_info.get('model', '')})"

                per_criterion: Dict[str, Dict] = {}
                for cid in criterion_ids:
                    crit_data = parsed.get(cid, {})
                    raw_verdict = str(crit_data.get("verdict", "")).lower().strip()
                    confidence = float(crit_data.get("confidence", 0.90))

                    if raw_verdict not in ("pass", "refer"):
                        raw_verdict = "pass" if confidence >= CRITERION_PASS_THRESHOLD else "refer"

                    feedback = str(crit_data.get("feedback", "")).strip()
                    if not feedback:
                        crit_desc = next(
                            (c["description"] for c in criteria_list if c.get("id") == cid), cid
                        )
                        feedback = self._minimal_criterion_feedback(
                            raw_verdict, crit_desc, task_heading
                        )

                    evidence_quote = str(crit_data.get("student_evidence_quote", "")).strip()

                    per_criterion[cid] = {
                        "verdict": raw_verdict,
                        "confidence": round(confidence, 4),
                        "feedback": feedback,
                        "evidence_quote": evidence_quote,
                    }

                task_verdict, task_confidence, task_feedback = self._aggregate_task_verdict(
                    per_criterion, criteria_list, task_heading
                )

                return {
                    "verdict": task_verdict,
                    "confidence": task_confidence,
                    "feedback": task_feedback,
                    "per_criterion": per_criterion,
                    "provider": provider_label,
                }

            except Exception as err:
                logger.warning(
                    f"Key [{key_info.get('name', '?')}] failed on attempt {attempt + 1}: {err}"
                )
                continue

        return None

    def _aggregate_task_verdict(
        self,
        per_criterion: Dict[str, Dict],
        criteria_list: List[Dict[str, Any]],
        task_heading: str,
    ) -> tuple:
        """
        Derive the task-level verdict from per-criterion results.
        Strict rule: a task is PASS only if ALL criteria pass.
        Even a single criterion with verdict 'refer' causes the whole task to refer.
        """
        if not per_criterion:
            return "refer", 0.5, "No criteria were evaluated."

        total = len(per_criterion)
        passed = sum(1 for v in per_criterion.values() if v.get("verdict") == "pass")
        avg_confidence = (
            sum(v.get("confidence", 0.5) for v in per_criterion.values()) / total
        )

        task_verdict = "pass" if passed == total else "refer"

        passing_ids = [cid for cid, v in per_criterion.items() if v.get("verdict") == "pass"]
        referring_ids = [cid for cid, v in per_criterion.items() if v.get("verdict") == "refer"]

        if task_verdict == "pass":
            task_feedback = (
                f"The learner has satisfactorily addressed all assessment criteria for {task_heading}. "
                f"The submission demonstrates sound knowledge, clear academic structure, and appropriate "
                f"engagement with the required learning outcomes."
            )
        else:
            pass_str = (", ".join(passing_ids)) if passing_ids else "none"
            refer_str = ", ".join(referring_ids)
            task_feedback = (
                f"This task requires resubmission. {len(referring_ids)} of {total} criteria "
                f"require further development for {task_heading}. "
                f"Criteria achieved: {pass_str}. "
                f"Criteria requiring resubmission: {refer_str}. "
                f"Please ensure each referred criterion is directly expanded with relevant academic concepts, "
                f"supporting evidence, and referenced examples."
            )

        return task_verdict, round(avg_confidence, 4), task_feedback

    def _fallback_evaluate(
        self,
        task_text: str,
        task_heading: str,
        criteria_list: List[Dict[str, Any]],
        unit_code: str,
    ) -> Dict[str, Any]:
        """
        Deterministic rule-based fallback when no LLM API keys are configured.
        Uses keyword-matching against rubric key_topics to produce per-criterion verdicts.
        """
        text_lower = task_text.lower()
        per_criterion: Dict[str, Dict] = {}

        for c in criteria_list:
            cid = c.get("id", "")
            desc = c.get("description", "")
            topics = c.get("key_topics", [])

            topic_hits = sum(1 for t in topics if t.lower() in text_lower) if topics else 0
            topic_total = len(topics) if topics else 1
            coverage = topic_hits / topic_total

            criterion_confidence = round(coverage, 4)
            criterion_verdict = "pass" if coverage >= CRITERION_PASS_THRESHOLD else "refer"

            if criterion_verdict == "pass":
                feedback = (
                    f"The learner's submission demonstrates satisfactory coverage for criterion {cid}: {desc}. "
                    f"Key concepts and relevant frameworks have been appropriately addressed."
                )
            else:
                missing_topics = [t for t in topics if t.lower() not in text_lower][:3]
                missing_str = "; ".join(missing_topics) if missing_topics else desc
                feedback = (
                    f"Criterion {cid} requires resubmission. The submission does not sufficiently address: "
                    f"{missing_str}. Ensure this criterion is explicitly covered with supporting evidence."
                )

            per_criterion[cid] = {
                "verdict": criterion_verdict,
                "confidence": criterion_confidence,
                "feedback": feedback,
                "evidence_quote": "Rule-based keyword scan",
            }

        task_verdict, task_confidence, task_feedback = self._aggregate_task_verdict(
            per_criterion, criteria_list, task_heading
        )

        return {
            "verdict": task_verdict,
            "confidence": task_confidence,
            "feedback": task_feedback,
            "per_criterion": per_criterion,
            "provider": f"Rule Validator ({unit_code})",
        }

    def _minimal_criterion_feedback(
        self, verdict: str, description: str, task_heading: str
    ) -> str:
        if verdict == "pass":
            return (
                f"The learner has satisfactorily addressed this criterion. "
                f"The submission demonstrates adequate engagement with: {description}."
            )
        else:
            return (
                f"This criterion requires further development upon resubmission. "
                f"The submission does not sufficiently address: {description}."
            )

    # ── Overall Assessor Comment Generation ────────────────────────────────────

    async def generate_overall_comment(
        self,
        student_name: str,
        unit_code: str,
        unit_name: str,
        task_results: List[Dict[str, Any]],
        final_verdict: str,
        active_keys: List[Dict[str, Any]],
        citation_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generates an authentic, professional UK academic assessor overall comment.
        When passing: Warm, appreciative, acknowledging learner's strengths and engagement.
        When referring: Constructive, supportive, clearly specifying areas for resubmission.
        """
        if active_keys:
            summary_lines = []
            for t in task_results:
                verdict_label = t.get("verdict", "refer").upper()
                per_crit = t.get("per_criterion", {})
                if per_crit:
                    crit_summary = "; ".join(
                        f"{cid}: {v.get('verdict', 'refer').upper()}"
                        for cid, v in per_crit.items()
                    )
                    summary_lines.append(
                        f"  Task {t['task_number']} ({t['task_heading']}): {verdict_label} — Criteria: {crit_summary}"
                    )
                else:
                    summary_lines.append(
                        f"  Task {t['task_number']} ({t['task_heading']}): {verdict_label}"
                    )
            task_summary = "\n".join(summary_lines)

            citation_note = ""
            if citation_context:
                citation_note = (
                    f"Citations: {citation_context.get('in_text_count', 0)} in-text citations found. "
                    f"Bibliography: {'Present' if citation_context.get('has_bibliography') else 'Missing'}.\n"
                )

            tone_guidance = (
                "The submission has PASSED. Write a warm, encouraging, and appreciative assessor summary (3–5 sentences) "
                "commending the learner's knowledge, academic structure, and effective engagement with the subject matter."
                if final_verdict.lower() == "pass" else
                "The submission requires RESUBMISSION (Refer). Write a supportive, professional, and clear assessor summary "
                "(3–5 sentences) acknowledging the work submitted while clearly highlighting the specific criteria that "
                "need further development and how to achieve a Pass."
            )

            prompt = (
                f"Write a genuine UK Academic Assessor Overall Comment for a qualification submission.\n\n"
                f"Learner: {student_name}\n"
                f"Unit: {unit_code} — {unit_name}\n"
                f"Overall Result: {final_verdict.upper()}\n"
                f"{citation_note}"
                f"Task Breakdown:\n{task_summary}\n\n"
                f"Assessor Guidelines:\n"
                f"- {tone_guidance}\n"
                f"- Follow official UK Awarding Body standards (professional, constructive, personalized tone).\n"
                f"- Reference specific strengths or areas of improvement observed.\n"
                f"- Never mention word counts.\n"
                f"- Return ONLY the final assessor comment text (no markdown formatting, no extra labels)."
            )

            for attempt in range(min(len(active_keys), 2)):
                key_info = await self.get_next_key(active_keys)
                if not key_info:
                    break
                try:
                    res = await LLMProviderClient.call_llm(
                        provider=key_info["provider"],
                        api_key=key_info["key"],
                        model_name=key_info.get("model", ""),
                        prompt=prompt,
                        timeout_seconds=25.0,
                        is_json=False,
                    )
                    comment = res["text"].strip().strip('"')
                    if comment and len(comment) > 40:
                        return comment
                except Exception as err:
                    logger.warning(f"Overall comment generation failed (attempt {attempt + 1}): {err}")
                    continue

        # Structured fallback comment
        if final_verdict.lower() == "pass":
            return (
                f"{student_name} has produced a well-structured and comprehensive submission for Unit {unit_code} "
                f"({unit_name}). The learner has demonstrated a sound understanding of the core concepts, frameworks, "
                f"and relevant legislation across all learning outcomes. The work meets the required UK qualification "
                f"standard and reflects commendable academic engagement."
            )
        else:
            refer_tasks = [t for t in task_results if t.get("verdict") == "refer"]
            refer_details = []
            for t in refer_tasks:
                per_crit = t.get("per_criterion", {})
                refer_crits = [cid for cid, v in per_crit.items() if v.get("verdict") == "refer"]
                if refer_crits:
                    refer_details.append(f"Task {t['task_number']} (Criteria: {', '.join(refer_crits)})")

            refer_str = "; ".join(refer_details) if refer_details else "the highlighted criteria"
            return (
                f"{student_name} has demonstrated good effort in this submission for Unit {unit_code} ({unit_name}). "
                f"However, further development is required to meet the full assessment criteria, particularly in {refer_str}. "
                f"Please review the detailed feedback for each criterion, expand your answers with relevant academic evidence "
                f"and examples, and resubmit for assessment."
            )
