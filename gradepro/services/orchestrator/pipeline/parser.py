import io
import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
import docx

logger = logging.getLogger(__name__)


@dataclass
class AssignmentHeader:
    centre_name: str = ""
    qualification: str = ""
    awarding_body: str = ""
    level: str = ""
    unit_code: str = ""
    unit_name: str = ""
    learner_name: str = ""
    learner_id: str = ""
    submission_date: str = ""


@dataclass
class TaskSection:
    task_number: int
    heading: str
    target_words: Optional[Tuple[int, int]] = None
    sub_criteria: List[str] = field(default_factory=list)
    student_content: str = ""
    word_count: int = 0
    is_shared: bool = False
    original_heading: str = ""
    detection_method: str = ""


@dataclass
class CitationStats:
    in_text_count: int = 0
    unique_authors: List[str] = field(default_factory=list)
    in_text_citations: List[str] = field(default_factory=list)
    bibliography_entries: List[str] = field(default_factory=list)
    bibliography_count: int = 0
    has_bibliography: bool = False


@dataclass
class ParsedAssignment:
    header: AssignmentHeader
    college: str
    format_summary: Dict[str, Any]
    tasks: List[TaskSection]
    introduction: str = ""
    conclusion: str = ""
    bibliography: str = ""
    citation_stats: CitationStats = field(default_factory=CitationStats)

    @property
    def clean_academic_body(self) -> str:
        """
        Returns strictly the academic submission body (Intro + Tasks + Conclusion),
        excluding document header table 0, boilerplate instructions, references, and appendices.
        """
        parts = []
        if self.introduction and self.introduction.strip():
            parts.append(self.introduction.strip())
        for t in self.tasks:
            if t.student_content and t.student_content.strip():
                parts.append(t.student_content.strip())
        if self.conclusion and self.conclusion.strip():
            parts.append(self.conclusion.strip())
        return "\n\n".join(parts)

    @property
    def clean_word_count(self) -> int:
        """Exact word count of the clean academic submission body."""
        return len(self.clean_academic_body.split())


_SINGLE_TASK_RE = re.compile(r'^task\s*(\d+)\b', re.IGNORECASE)
_MULTI_TASK_RE = re.compile(r'^tasks?\s*(\d+)\s*(?:and|&|/|,)\s*(?:task\s*)?(\d+)', re.IGNORECASE)
_LO_HEADING_RE = re.compile(r'^(?:learning\s+outcome|l\.?o\.?\s*)(\d+)\b', re.IGNORECASE)
_CRITERION_ID_RE = re.compile(r'^(\d+)\.(\d+)\s+\S', re.IGNORECASE)
_TEMPLATE_STYLES = {"worksheet text", "worksheet", "list paragraph"}

_SKIP_PATTERNS = [
    r'^\(your answer here\)',
    r'^\(write your',
    r'^\[your',
    r'^\(provide a brief',
    r'^\(type your',
    r'^\(enter your',
    r'^helping notes?:?',
    r'^guidance:?',
    r'^note:?\s+task\s+\d+',
    r'^note:?\s+the examples',
    r'^\(note:',
    r'^for task \d+,?\s+you (have been asked|are required)',
    r'^to fulfil (the requirement|requirements)',
    r'^you (have been asked|are required) to (write|describe|explain|discuss)',
    r'^\(write ',
    r'^\(describe ',
    r'^\(discuss ',
    r'^\(explain ',
    r'^\(identify ',
    r'^\(an honest',
    r'^\(description of',
    r'^\(identification',
    r'^assessor.{0,10}name',
    r'^assessor.{0,10}signature',
    r'^assessor.{0,10}feedback',
    r'^iqa.{0,10}name',
    r'^iqa.{0,10}signature',
    r'^iqa.{0,10}feedback',
    r'^iqa.{0,10}comments',
    r'^date\s*$',
    r'^the section below is for office use',
    r'^statement of authenticity',
    r'^learner.?s declaration',
    r'^i certify that the work',
    r'^your response to task \d+ fulfils',
    r'^this fulfils (the requirements of )?learning outcome',
    r'Provide a list of references',
    r'^an outline of (the main tasks|interprofessional)',
    r'^identify and explain how (health|these)',
    r'^discuss mechanisms for reporting',
    r'^a judgment as to the current',
]
_SKIP_RE = re.compile('|'.join(_SKIP_PATTERNS), re.IGNORECASE)


def is_skip(text: str) -> bool:
    return bool(_SKIP_RE.match(text.strip()))


class UniversalAssignmentParser:
    """
    Universal assignment parser supporting all UK qualification formats:
    - Explicit Task headings ("Task 1", "Task 2 and Task 3")
    - Learning Outcome headings ("LO 1:", "LO2:", "Learning Outcome 3")
    - Criterion-level prompts ("1.1 Explain...", "2.1 Discuss...")
    - Structured state-machine extraction of Intro, Tasks, Conclusion, and Bibliography
    """

    def parse(self, docx_bytes: bytes) -> ParsedAssignment:
        doc = docx.Document(io.BytesIO(docx_bytes))
        header = self._extract_header(doc)
        college = self._detect_college(header)
        
        from .font_resolver import DocxFontResolver
        resolver = DocxFontResolver(doc)
        format_summary = resolver.format_summary()
        
        sections = self._segment_sections(doc)
        
        # Combine all body sections for citation scanning
        all_body_text = "\n\n".join([
            sections["intro"],
            "\n\n".join(t.student_content for t in sections["tasks"]),
            sections["conclusion"],
        ])
        citation_stats = self._extract_citation_stats(all_body_text, sections["bibliography"])
        
        return ParsedAssignment(
            header=header,
            college=college,
            format_summary=format_summary,
            tasks=sections["tasks"],
            introduction=sections["intro"],
            conclusion=sections["conclusion"],
            bibliography=sections["bibliography"],
            citation_stats=citation_stats,
        )

    def _extract_citation_stats(self, body_text: str, bibliography_text: str) -> CitationStats:
        """
        Extracts Harvard in-text citations, narrative citations, and bibliography entries.
        Supports standard authors, multiple authors (& / and / et al.), government bodies,
        domains (e.g. gov.uk), and organisational acronyms (CQC, NICE, WHO, NHS, SCIE, GMC, NMC).
        """
        in_text_matches = []
        unique_authors = set()
        
        # Exclude non-citation parentheses
        skip_prefixes = (
            'see', 'e.g', 'i.e', 'table', 'figure', 'fig', 'task', 'lo',
            'criterion', 'note', 'learning outcome', 'appendix', 'page', 'p.', 'pp.'
        )

        # 1. Parenthetical citations:
        # e.g., (Smith, 2021), (World Health Organization, 2020), (CQC, 2022), (gov.uk, 2021), (NICE & SCIE, 2019), (Smith et al., 2020: 45)
        p_matches = re.findall(
            r'\(([a-zA-Z0-9\s\.\,\'\-\&\/]+?),\s*((?:19|20)\d{2}(?:[a-z])?(?:\s*:\s*\d+(?:-\d+)?)?|n\.?d\.?)\)',
            body_text,
        )
        for author, year in p_matches:
            author_clean = author.strip()
            author_lower = author_clean.lower()
            if (
                len(author_clean) >= 2
                and not any(author_lower.startswith(p) for p in skip_prefixes)
                and not re.match(r'^\d+$', author_clean)  # not just a number
            ):
                in_text_matches.append(f"({author_clean}, {year})")
                unique_authors.add(author_clean)

        # 2. Narrative citations:
        # e.g., Smith (2020), CQC (2021), WHO (2019), Department of Health (2018), Jones et al. (2019), Smith & Jones (2020)
        n_matches = re.findall(
            r'\b([A-Z][a-zA-Z0-9\s\.\,\'\-\&]+?(?:\s+et\s+al\.|\s+(?:and|\&)\s+[A-Z0-9][a-zA-Z0-9]+)?)\s+\(((?:19|20)\d{2}(?:[a-z])?|n\.?d\.?)\)',
            body_text,
        )
        for author, year in n_matches:
            author_clean = author.strip()
            author_lower = author_clean.lower()
            if (
                len(author_clean) >= 2
                and len(author_clean) <= 60
                and not any(author_lower.startswith(p) for p in skip_prefixes)
                and not re.match(r'^\d+$', author_clean)
            ):
                in_text_matches.append(f"{author_clean} ({year})")
                unique_authors.add(author_clean)

        # 3. Bibliography entries
        bib_entries = []
        if bibliography_text and bibliography_text.strip():
            for line in bibliography_text.split('\n'):
                line = line.strip()
                if line and len(line) > 15 and not is_skip(line):
                    bib_entries.append(line)

        return CitationStats(
            in_text_count=len(in_text_matches),
            unique_authors=sorted(list(unique_authors)),
            in_text_citations=in_text_matches[:30],
            bibliography_entries=bib_entries,
            bibliography_count=len(bib_entries),
            has_bibliography=bool(bib_entries or (bibliography_text and len(bibliography_text.strip()) > 20)),
        )

    def _extract_header(self, doc: docx.Document) -> AssignmentHeader:
        header = AssignmentHeader()
        if not doc.tables:
            return header
        table = doc.tables[0]
        for row in table.rows:
            cells = row.cells
            unique_vals = list(dict.fromkeys(c.text.strip() for c in cells if c.text.strip()))
            if not unique_vals:
                continue
            raw_key_cell = unique_vals[0].lower()
            raw_val_cell = unique_vals[1] if len(unique_vals) > 1 else ""
            if ":" in unique_vals[0] and len(unique_vals) == 1:
                parts = unique_vals[0].split(":", 1)
                raw_key_cell = parts[0].strip().lower()
                raw_val_cell = parts[1].strip()
            if is_skip(unique_vals[0]) or "office use" in raw_key_cell:
                continue
            if any(k in raw_key_cell for k in ("qualification title", "qualification")):
                header.qualification = raw_val_cell
                m_body = re.search(r'(Qualifi|OTHM|NOCN|ATHE)', raw_val_cell, re.I)
                if m_body:
                    header.awarding_body = m_body.group(1).upper()
                m_lvl = re.search(r'Level\s*(\d+)', raw_val_cell, re.I)
                if m_lvl:
                    header.level = f"Level {m_lvl.group(1)}"
            elif any(k in raw_key_cell for k in ("unit name", "unit title")):
                header.unit_name = raw_val_cell
            elif any(k in raw_key_cell for k in ("unit number", "unit code")):
                m_unit = re.match(r'^([A-Z0-9]+)\s*[-\u2013:]\s*(.+)$', raw_val_cell)
                if m_unit:
                    header.unit_code = m_unit.group(1).strip()
                    if not header.unit_name:
                        header.unit_name = m_unit.group(2).strip()
                else:
                    header.unit_code = raw_val_cell.split()[0] if raw_val_cell else ""
            elif any(k in raw_key_cell for k in (
                "learner full name", "learner name", "student name", "student full name"
            )):
                header.learner_name = raw_val_cell
            elif any(k in raw_key_cell for k in (
                "learner registration", "learner enrolment", "student id",
                "registration number", "enrolment id", "enrolment number"
            )):
                header.learner_id = raw_val_cell
            elif any(k in raw_key_cell for k in ("centre name", "center name", "centre:")):
                header.centre_name = raw_val_cell
            elif any(k in raw_key_cell for k in ("due date", "submission date", "date of submission")):
                header.submission_date = raw_val_cell
        if not header.unit_code and header.unit_name:
            m = re.search(r'\b([A-Z]{2,5}\d{3,})\b', header.unit_name)
            if m:
                header.unit_code = m.group(1)
        return header

    def _detect_college(self, header: AssignmentHeader) -> str:
        centre = header.centre_name.lower()
        qual = header.qualification.lower()
        if "international learning" in centre or "ilc" in centre or "inspire london" in centre:
            return "ILC"
        elif "uk professional development" in centre or "ukpda" in centre:
            return "UKPDA"
        elif "ilc" in qual:
            return "ILC"
        return "UKPDA"

    def _segment_sections(self, doc: docx.Document) -> Dict[str, Any]:
        from docx.oxml.ns import qn
        
        elements = []
        header_skipped = False
        body = doc.element.body
        for child in body:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "p":
                para = docx.text.paragraph.Paragraph(child, doc)
                text = para.text.strip()
                if text:
                    sn = (para.style.name or "").lower() if para.style else ""
                    is_h = "heading" in sn
                    is_bold = para.runs and any(r.bold for r in para.runs if r.text.strip())
                    elements.append({
                        "text": text,
                        "style": sn,
                        "is_heading": is_h,
                        "is_bold_short": is_bold and len(text) <= 120,
                        "is_template_style": any(ts in sn for ts in _TEMPLATE_STYLES) or ("list paragraph" in sn and is_bold),
                    })
            elif tag == "tbl":
                if not header_skipped:
                    header_skipped = True
                    continue
                for row_el in child.iter(qn("w:tr")):
                    for cell_el in row_el.iter(qn("w:tc")):
                        for p_el in cell_el.iter(qn("w:p")):
                            para = docx.text.paragraph.Paragraph(p_el, doc)
                            text = para.text.strip()
                            if text:
                                sn = (para.style.name or "").lower() if para.style else ""
                                is_h = "heading" in sn
                                is_bold = para.runs and any(r.bold for r in para.runs if r.text.strip())
                                elements.append({
                                    "text": text,
                                    "style": sn,
                                    "is_heading": is_h,
                                    "is_bold_short": is_bold and len(text) <= 120,
                                    "is_template_style": any(ts in sn for ts in _TEMPLATE_STYLES) or ("list paragraph" in sn and is_bold),
                                })

        current_sec = "none"
        current_tasks = []
        task_info = {}
        
        intro_paras = []
        concl_paras = []
        bib_paras = []
        task_paras = {}

        for el in elements:
            text = el["text"]
            tl = text.lower()

            # 1. Bibliography / References
            if (el["is_heading"] or el["is_bold_short"] or len(text) <= 60) and re.match(r'^(bibliography|references)\b', tl):
                current_sec = "bib"
                current_tasks = []
                continue

            # 2. Conclusion
            if (el["is_heading"] or el["is_bold_short"] or len(text) <= 60) and re.match(r'^conclusion\b', tl):
                current_sec = "concl"
                current_tasks = []
                continue

            # 3. Introduction
            if (el["is_heading"] or el["is_bold_short"] or len(text) <= 60) and re.match(r'^introduction\b', tl):
                current_sec = "intro"
                current_tasks = []
                continue

            # 4. Multi-Task Heading: "Task 2 and Task 3: ..."
            m_multi = _MULTI_TASK_RE.match(text)
            if m_multi and (el["is_heading"] or el["is_bold_short"] or len(text) <= 120):
                t_nums = sorted([int(m_multi.group(1)), int(m_multi.group(2))])
                current_sec = "task"
                current_tasks = t_nums
                wc_match = re.search(r'\((\d+)\s*[-\u2013]\s*(\d+)', text)
                targets = (int(wc_match.group(1)), int(wc_match.group(2))) if wc_match else None
                for tn in t_nums:
                    task_paras.setdefault(tn, [])
                    task_info[tn] = {
                        "heading": text,
                        "is_shared": True,
                        "method": "multi_task_heading",
                        "target_words": targets,
                    }
                continue

            # 5. Single Task Heading: "Task 1", "Task 2", etc.
            m_single = _SINGLE_TASK_RE.match(text)
            if m_single and (el["is_heading"] or el["is_bold_short"] or len(text) <= 120):
                tn = int(m_single.group(1))
                current_sec = "task"
                current_tasks = [tn]
                wc_match = re.search(r'\((\d+)\s*[-\u2013]\s*(\d+)', text)
                targets = (int(wc_match.group(1)), int(wc_match.group(2))) if wc_match else None
                task_paras.setdefault(tn, [])
                task_info[tn] = {
                    "heading": text,
                    "is_shared": False,
                    "method": "explicit_task_heading",
                    "target_words": targets,
                }
                continue

            # 6. Learning Outcome Heading: "LO 1:", "LO2:", "Learning Outcome 3", etc.
            m_lo = _LO_HEADING_RE.match(text)
            if m_lo and (el["is_heading"] or el["is_bold_short"] or len(text) <= 120):
                tn = int(m_lo.group(1))
                current_sec = "task"
                current_tasks = [tn]
                task_paras.setdefault(tn, [])
                if tn not in task_info:
                    task_info[tn] = {
                        "heading": text,
                        "is_shared": False,
                        "method": "lo_heading",
                        "target_words": None,
                    }
                continue

            # 7. Criterion prompt (e.g. "1.1 Explain...", "2.2 Discuss...")
            m_crit = _CRITERION_ID_RE.match(text)
            if m_crit and (el["is_template_style"] or len(text) <= 250):
                tn = int(m_crit.group(1))
                current_sec = "task"
                current_tasks = [tn]
                task_paras.setdefault(tn, [])
                if tn not in task_info:
                    task_info[tn] = {
                        "heading": f"Task {tn}",
                        "is_shared": False,
                        "method": "criterion_prompt",
                        "target_words": None,
                    }
                continue

            # Skip boilerplate & template prompts
            if is_skip(text) or el["is_template_style"]:
                continue

            # Accumulate content
            if current_sec == "intro":
                intro_paras.append(text)
            elif current_sec == "concl":
                concl_paras.append(text)
            elif current_sec == "bib":
                bib_paras.append(text)
            elif current_sec == "task" and current_tasks:
                for tn in current_tasks:
                    task_paras[tn].append(text)

        # Build TaskSection objects
        tasks: List[TaskSection] = []
        for tn in sorted(task_paras.keys()):
            paras = task_paras[tn]
            content = "\n\n".join(paras).strip()
            if content:
                info = task_info.get(tn, {})
                tasks.append(TaskSection(
                    task_number=tn,
                    heading=info.get("heading", f"Task {tn}"),
                    original_heading=info.get("heading", f"Task {tn}"),
                    target_words=info.get("target_words"),
                    student_content=content,
                    word_count=len(content.split()),
                    is_shared=info.get("is_shared", False),
                    detection_method=info.get("method", "state_machine"),
                ))

        # Fallback if no tasks separated
        if not tasks:
            all_body = []
            for el in elements:
                t = el["text"]
                if not is_skip(t) and not el["is_template_style"]:
                    all_body.append(t)
            full_text = "\n\n".join(all_body).strip()
            tasks.append(TaskSection(
                task_number=1,
                heading="Submission Content",
                student_content=full_text,
                word_count=len(full_text.split()),
                detection_method="fallback_blob",
            ))

        return {
            "tasks": tasks,
            "intro": "\n\n".join(intro_paras),
            "conclusion": "\n\n".join(concl_paras),
            "bibliography": "\n\n".join(bib_paras),
        }
