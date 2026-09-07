"""
Feature engineering and extraction utilities for GradePro ML pipeline.
Extracts structured numeric and lexical metrics from DOCX paragraphs/tables.
"""

import re
from typing import Dict, List, Any
import numpy as np


def extract_text_statistics(text: str) -> Dict[str, float]:
    """Calculate statistical word, character, and sentence counts from text."""
    if not text or not text.strip():
        return {
            "word_count": 0.0,
            "char_count": 0.0,
            "avg_word_length": 0.0,
            "sentence_count": 0.0,
            "reference_count": 0.0,
        }

    words = text.split()
    word_count = len(words)
    char_count = len(text)
    avg_word_len = (sum(len(w) for w in words) / word_count) if word_count > 0 else 0.0

    # Rough sentence split
    sentences = re.split(r'[.!?]+', text)
    sentence_count = len([s for s in sentences if s.strip()])

    # Academic citation markers (e.g. (Smith, 2020), [1], et al.)
    citation_patterns = [
        r'\([A-Z][a-zA-Z\s]+,\s*\d{4}\)',  # (Author, Year)
        r'\[\d+\]',                         # [1]
        r'et al\.',                         # et al.
        r'ibid\.',                          # ibid.
    ]
    ref_count = 0
    for pat in citation_patterns:
        ref_count += len(re.findall(pat, text))

    return {
        "word_count": float(word_count),
        "char_count": float(char_count),
        "avg_word_length": float(avg_word_len),
        "sentence_count": float(sentence_count),
        "reference_count": float(ref_count),
    }


def compile_unit_features(
    task_contents: List[str],
    doc_format_features: Dict[str, Any],
) -> np.ndarray:
    """
    Combines task content statistics and document formatting features
    into a numeric vector for XGBoost fallback inference.
    """
    feature_list: List[float] = []

    # Total word count across tasks
    total_words = 0.0
    total_citations = 0.0

    for idx, content in enumerate(task_contents):
        stats = extract_text_statistics(content)
        feature_list.append(stats["word_count"])
        feature_list.append(stats["avg_word_length"])
        feature_list.append(stats["reference_count"])
        total_words += stats["word_count"]
        total_citations += stats["reference_count"]

    feature_list.append(total_words)
    feature_list.append(total_citations)

    # Document formatting features
    feature_list.append(float(doc_format_features.get("body_font_size_pt", 12.0)))
    feature_list.append(float(doc_format_features.get("heading_font_size_pt", 13.0)))
    feature_list.append(float(doc_format_features.get("bold_ratio", 0.05)))
    feature_list.append(float(doc_format_features.get("table_count", 1.0)))

    return np.array(feature_list, dtype=np.float32)
