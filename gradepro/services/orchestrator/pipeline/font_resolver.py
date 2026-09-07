from typing import Dict, List, Any
import docx
from docx.oxml.ns import qn


class DocxFontResolver:
    """
    Resolves effective rendered font size, family, and styles by walking
    the 4-level DOCX style inheritance hierarchy:
    Run Override -> Paragraph rPr -> Style Chain -> Document Defaults
    """

    def __init__(self, doc: docx.Document):
        self.doc = doc
        self._doc_defaults = self._parse_doc_defaults()

    def _parse_doc_defaults(self) -> Dict[str, Any]:
        defaults = {"size_pt": 12.0, "name": "Times New Roman", "bold": False}
        try:
            body = self.doc.element.body
            parent = body.getparent()
            docDefaults = parent.find(qn("w:docDefaults"))
            if docDefaults is not None:
                rPrDefault = docDefaults.find(qn("w:rPrDefault"))
                if rPrDefault is not None:
                    rPr = rPrDefault.find(qn("w:rPr"))
                    if rPr is not None:
                        sz = rPr.find(qn("w:sz"))
                        if sz is not None and sz.get(qn("w:val")):
                            defaults["size_pt"] = float(sz.get(qn("w:val"))) / 2.0
                        rFonts = rPr.find(qn("w:rFonts"))
                        if rFonts is not None:
                            font_name = rFonts.get(qn("w:ascii")) or rFonts.get(qn("w:hAnsi"))
                            if font_name:
                                defaults["name"] = font_name
        except Exception:
            pass
        return defaults

    def resolve_run_font_size(self, run: docx.text.run.Run, para: docx.text.paragraph.Paragraph) -> float:
        # Level 1: Run-level override
        if run.font.size is not None:
            return float(run.font.size.pt)

        # Level 2: Paragraph rPr
        pPr = para._p.find(qn("w:pPr"))
        if pPr is not None:
            rPr = pPr.find(qn("w:rPr"))
            if rPr is not None:
                sz = rPr.find(qn("w:sz"))
                if sz is not None and sz.get(qn("w:val")):
                    return float(sz.get(qn("w:val"))) / 2.0

        # Level 3: Named Style chain
        style = para.style
        while style is not None:
            if hasattr(style, 'font') and style.font.size is not None:
                return float(style.font.size.pt)
            style = getattr(style, 'base_style', None)

        # Level 4: Document defaults
        return self._doc_defaults["size_pt"]

    def resolve_run_font_name(self, run: docx.text.run.Run, para: docx.text.paragraph.Paragraph) -> str:
        # Level 1: Run
        if run.font.name:
            return run.font.name

        # Level 2: Style chain
        style = para.style
        while style is not None:
            if hasattr(style, 'font') and style.font.name:
                return style.font.name
            style = getattr(style, 'base_style', None)

        # Level 3: Document Normal style
        try:
            normal = self.doc.styles["Normal"].font.name
            if normal:
                return normal
        except Exception:
            pass

        return self._doc_defaults["name"]

    def resolve_run_bold(self, run: docx.text.run.Run, para: docx.text.paragraph.Paragraph) -> bool:
        if run.font.bold is not None:
            return bool(run.font.bold)
        style = para.style
        while style is not None:
            if hasattr(style, 'font') and style.font.bold is not None:
                return bool(style.font.bold)
            style = getattr(style, 'base_style', None)
        return self._doc_defaults["bold"]

    def format_summary(self) -> Dict[str, Any]:
        body_sizes: List[float] = []
        heading_sizes: List[float] = []
        names: List[str] = []
        bold_count = 0
        total_runs = 0

        for para in self.doc.paragraphs:
            is_heading = "Heading" in (para.style.name if para.style else "")
            for run in para.runs:
                text = run.text.strip()
                if not text:
                    continue
                total_runs += 1
                sz = self.resolve_run_font_size(run, para)
                nm = self.resolve_run_font_name(run, para)
                bd = self.resolve_run_bold(run, para)

                names.append(nm)
                if bd:
                    bold_count += 1
                if is_heading:
                    heading_sizes.append(sz)
                else:
                    body_sizes.append(sz)

        primary_font = max(set(names), key=names.count) if names else "Times New Roman"
        primary_body_sz = max(set(body_sizes), key=body_sizes.count) if body_sizes else 12.0
        primary_heading_sz = max(heading_sizes) if heading_sizes else 13.0

        return {
            "body_font_size_pt": primary_body_sz,
            "heading_font_size_pt": primary_heading_sz,
            "primary_font": primary_font,
            "bold_ratio": (bold_count / total_runs) if total_runs > 0 else 0.0,
            "table_count": len(self.doc.tables),
        }

    def validate_against_rules(self, rules: Dict[str, Any]) -> List[Dict[str, Any]]:
        summary = self.format_summary()
        violations = []

        expected_font = rules.get("font_family", "Times New Roman")
        if expected_font.lower() not in summary["primary_font"].lower():
            violations.append({
                "rule": "font_family",
                "expected": expected_font,
                "actual": summary["primary_font"],
                "severity": "warning",
            })

        expected_size = float(rules.get("body_font_size_pt", 12.0))
        if abs(summary["body_font_size_pt"] - expected_size) > 0.5:
            violations.append({
                "rule": "body_font_size_pt",
                "expected": expected_size,
                "actual": summary["body_font_size_pt"],
                "severity": "warning",
            })

        return violations
