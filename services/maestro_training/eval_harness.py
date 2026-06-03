"""Toy evaluation harness for trivial Brazilian-format fields (cep, cpf, rg).

Used to baseline rule-based extractors BEFORE introducing any LLM. If rule precision
on validated samples is already >95% for a given field, an LLM is overkill.
"""
from __future__ import annotations

import re
from typing import Iterable, Tuple

CEP_RE = re.compile(r"\b(\d{5})-?(\d{3})\b")
CPF_RE = re.compile(r"\b(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})\b")
RG_RE = re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}-?[\dxX]\b")


def extract_cep(text: str) -> str | None:
    m = CEP_RE.search(text or "")
    return f"{m.group(1)}-{m.group(2)}" if m else None


def extract_cpf(text: str) -> str | None:
    m = CPF_RE.search(text or "")
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)}-{m.group(4)}" if m else None


def extract_rg(text: str) -> str | None:
    m = RG_RE.search(text or "")
    return m.group(0) if m else None


EXTRACTORS = {"cep": extract_cep, "cpf": extract_cpf, "rg": extract_rg}


def score(samples: Iterable[Tuple[str, str, str]]) -> dict:
    """samples = iterable of (field_name, raw_message, true_value).

    Returns {field_name: {tp, fp, fn, precision, recall}}.
    """
    stats: dict = {}
    for field_name, raw, true_value in samples:
        bucket = stats.setdefault(field_name, {"tp": 0, "fp": 0, "fn": 0})
        extractor = EXTRACTORS.get(field_name)
        if not extractor:
            continue
        predicted = extractor(raw)
        if predicted and predicted == true_value:
            bucket["tp"] += 1
        elif predicted and predicted != true_value:
            bucket["fp"] += 1
        else:
            bucket["fn"] += 1

    for bucket in stats.values():
        tp, fp, fn = bucket["tp"], bucket["fp"], bucket["fn"]
        bucket["precision"] = tp / (tp + fp) if (tp + fp) else 0.0
        bucket["recall"] = tp / (tp + fn) if (tp + fn) else 0.0
    return stats
