"""Rule-based safety boundaries for conversational fallback responses."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re


@dataclass(frozen=True)
class SafetyBoundaryDecision:
    """Result of evaluating whether a message crosses a hard-stop boundary."""

    hit: bool
    category: str | None = None


_DEFAULT_CONFIG_PATH = Path(__file__).with_name("safety_boundaries.json")


def _config_path() -> Path:
    override = os.environ.get("SAFETY_BOUNDARIES_CONFIG_PATH", "").strip()
    if override:
        return Path(override)
    return _DEFAULT_CONFIG_PATH


def _load_rules() -> tuple[
    tuple[tuple[str, tuple[re.Pattern[str], ...]], ...],
    tuple[tuple[str, tuple[str, ...]], ...],
]:
    with _config_path().open(encoding="utf-8") as handle:
        raw_config = json.load(handle)

    category_patterns: list[tuple[str, tuple[re.Pattern[str], ...]]] = []
    category_terms: list[tuple[str, tuple[str, ...]]] = []
    for category in raw_config.get("categories", []):
        category_id = str(category["id"])
        pattern_strings = tuple(str(pattern) for pattern in category.get("patterns_en", []))
        compiled_patterns = tuple(re.compile(pattern) for pattern in pattern_strings)
        category_patterns.append((category_id, compiled_patterns))

        terms_by_locale = category.get("terms_by_locale", {})
        flattened_terms = tuple(
            str(term)
            for terms in terms_by_locale.values()
            for term in terms
        )
        category_terms.append((category_id, flattened_terms))
    return tuple(category_patterns), tuple(category_terms)


_CATEGORY_PATTERNS, _CATEGORY_TERMS = _load_rules()


def classify_safety_boundary(message: str) -> SafetyBoundaryDecision:
    """Return whether the user message crosses a hard-stop safety boundary."""

    normalized = " ".join(message.strip().casefold().split())
    if not normalized:
        return SafetyBoundaryDecision(hit=False)

    for category, patterns in _CATEGORY_PATTERNS:
        if any(pattern.search(normalized) for pattern in patterns):
            return SafetyBoundaryDecision(hit=True, category=category)
    for category, terms in _CATEGORY_TERMS:
        if any(term.casefold() in normalized for term in terms):
            return SafetyBoundaryDecision(hit=True, category=category)
    return SafetyBoundaryDecision(hit=False)
