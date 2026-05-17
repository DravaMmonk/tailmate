"""Extraction strategies for dog profile enrichment."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from functools import lru_cache
from importlib.resources import files
import json
import math
import logging
import re
from typing import Any

from google.auth.credentials import Credentials
import vertexai
from vertexai.generative_models import GenerationConfig, GenerativeModel
import tenacity

from tailmate.contracts.dog_profile import DogProfile, ExtractionResult
from tailmate.contracts.errors import AdapterError


BREED_DATA_PATH = ("tailmate.adapters.dog_profile", "data", "breed_aliases_by_locale.json")
LOCALIZATION_DATA_PATH = ("tailmate.adapters.dog_profile", "data", "extractor_locale_data.json")
ASCII_ALIAS_PATTERN = re.compile(r"^[a-z0-9][a-z0-9 '/-]*$")
REGEX_FLAG_MAP = {
    "IGNORECASE": re.IGNORECASE,
}
logger = logging.getLogger(__name__)
RETRY_ATTEMPTS = 3
RETRY_INITIAL_WAIT_SECONDS = 1
RETRY_MAX_WAIT_SECONDS = 4


def _retry_external_call(
    *,
    operation: Callable[[], Any],
    failure_message: str,
    log_message: str,
    log_context: dict[str, Any],
) -> Any:
    retrying = tenacity.Retrying(
        sleep=tenacity.sleep,
        stop=tenacity.stop_after_attempt(RETRY_ATTEMPTS),
        wait=tenacity.wait_exponential(
            multiplier=RETRY_INITIAL_WAIT_SECONDS,
            min=RETRY_INITIAL_WAIT_SECONDS,
            max=RETRY_MAX_WAIT_SECONDS,
        ),
        retry=tenacity.retry_if_exception_type(Exception),
        reraise=False,
    )
    try:
        return retrying(operation)
    except tenacity.RetryError as exc:
        last_attempt = exc.last_attempt
        last_exception = last_attempt.exception() if last_attempt is not None else None
        logger.error(
            log_message,
            extra={
                **log_context,
                "attempts": last_attempt.attempt_number if last_attempt is not None else RETRY_ATTEMPTS,
                "error_type": type(last_exception).__name__ if last_exception is not None else None,
                "error_message": str(last_exception) if last_exception is not None else None,
            },
        )
        if last_exception is not None:
            raise AdapterError(failure_message) from last_exception
        raise AdapterError(failure_message) from exc


def _read_json_resource(resource_path: Sequence[str]) -> dict[str, Any]:
    resource = files(resource_path[0])
    for part in resource_path[1:]:
        resource = resource.joinpath(part)
    return json.loads(resource.read_text(encoding="utf-8"))


def _coerce_aliases_by_locale(raw_aliases: Mapping[str, Sequence[str]]) -> dict[str, tuple[str, ...]]:
    return {
        str(locale): tuple(str(alias) for alias in aliases)
        for locale, aliases in raw_aliases.items()
    }


def _flatten_aliases(aliases_by_locale: Mapping[str, Sequence[str]]) -> tuple[str, ...]:
    flattened: list[str] = []
    seen: set[str] = set()
    for aliases in aliases_by_locale.values():
        for alias in aliases:
            text = str(alias)
            if text in seen:
                continue
            seen.add(text)
            flattened.append(text)
    return tuple(flattened)


def _resolve_regex_flags(flag_names: Sequence[str]) -> int:
    flags = 0
    for flag_name in flag_names:
        flags |= REGEX_FLAG_MAP[str(flag_name)]
    return flags


def _compile_patterns(raw_group: Mapping[str, Any]) -> tuple[re.Pattern[str], ...]:
    flags = _resolve_regex_flags(raw_group.get("flags", ()))
    compiled: list[re.Pattern[str]] = []
    for patterns in raw_group["patterns_by_locale"].values():
        for pattern in patterns:
            compiled.append(re.compile(str(pattern), flags))
    return tuple(compiled)


def _compile_single_pattern(raw_group: Mapping[str, Any]) -> re.Pattern[str]:
    compiled = _compile_patterns(raw_group)
    if len(compiled) != 1:
        raise ValueError("Expected exactly one compiled pattern.")
    return compiled[0]


def _load_alias_group(
    raw_data: Mapping[str, Any],
    group_name: str,
) -> dict[str, dict[str, tuple[str, ...]]]:
    group = raw_data["alias_groups"][group_name]
    return {
        str(label): _coerce_aliases_by_locale(entry["aliases_by_locale"])
        for label, entry in group.items()
    }


def _load_keyword_group(raw_data: Mapping[str, Any], group_name: str) -> dict[str, tuple[str, ...]]:
    return _coerce_aliases_by_locale(raw_data["keyword_groups"][group_name]["aliases_by_locale"])


def _load_pattern_group(raw_data: Mapping[str, Any], group_name: str) -> tuple[re.Pattern[str], ...]:
    return _compile_patterns(raw_data["regex_groups"][group_name])


def _load_single_pattern(raw_data: Mapping[str, Any], group_name: str) -> re.Pattern[str]:
    return _compile_single_pattern(raw_data["regex_groups"][group_name])


def _load_labeled_pattern_group(
    raw_data: Mapping[str, Any],
    group_name: str,
) -> dict[str, tuple[re.Pattern[str], ...]]:
    group = raw_data["regex_label_groups"][group_name]
    return {
        str(label): _compile_patterns(entry)
        for label, entry in group.items()
    }


def _load_value_map(raw_data: Mapping[str, Any], group_name: str) -> dict[str, int]:
    merged: dict[str, int] = {}
    mappings_by_locale = raw_data["value_maps"][group_name]["mappings_by_locale"]
    for locale_values in mappings_by_locale.values():
        for key, value in locale_values.items():
            merged[str(key)] = int(value)
    return merged


def _load_string_map(raw_data: Mapping[str, Any], group_name: str) -> dict[str, str]:
    merged: dict[str, str] = {}
    mappings_by_locale = raw_data["string_maps"][group_name]["mappings_by_locale"]
    for locale_values in mappings_by_locale.values():
        for key, value in locale_values.items():
            merged[str(key)] = str(value)
    return merged


LOCALIZATION_DATA = _read_json_resource(LOCALIZATION_DATA_PATH)

CLAUSE_SPLIT_PATTERN = _load_single_pattern(LOCALIZATION_DATA, "clause_split")
TEXT_SPLIT_PATTERN = _load_single_pattern(LOCALIZATION_DATA, "text_split")
KG_PATTERN = _load_single_pattern(LOCALIZATION_DATA, "kg")
JIN_PATTERN = _load_single_pattern(LOCALIZATION_DATA, "jin")
LB_PATTERN = _load_single_pattern(LOCALIZATION_DATA, "lb")
BIRTHDATE_PATTERNS = _load_pattern_group(LOCALIZATION_DATA, "birthdate")
AGE_MONTH_HALF_PATTERNS = _load_pattern_group(LOCALIZATION_DATA, "age_month_half")
AGE_MONTH_PATTERNS = _load_pattern_group(LOCALIZATION_DATA, "age_month")
AGE_YEAR_PATTERNS = _load_pattern_group(LOCALIZATION_DATA, "age_year")
ALLERGY_PATTERNS = _load_pattern_group(LOCALIZATION_DATA, "allergy")
MEDICATION_PATTERNS = _load_pattern_group(LOCALIZATION_DATA, "medication")
MEDICAL_HISTORY_PATTERNS = _load_pattern_group(LOCALIZATION_DATA, "medical_history")
DOG_NAME_PATTERNS = _load_pattern_group(LOCALIZATION_DATA, "dog_name")
DOG_NAME_REJECTS = frozenset(
    _flatten_aliases(_load_keyword_group(LOCALIZATION_DATA, "dog_name_rejects"))
)
CHINESE_DIGIT_VALUES = _load_value_map(LOCALIZATION_DATA, "chinese_digits")
NUMERIC_STRIP_TOKENS = frozenset(
    _flatten_aliases(_load_keyword_group(LOCALIZATION_DATA, "numeric_strip"))
)
HALF_TOKENS = frozenset(
    _flatten_aliases(_load_keyword_group(LOCALIZATION_DATA, "numeric_half"))
)
TEN_TOKENS = frozenset(
    _flatten_aliases(_load_keyword_group(LOCALIZATION_DATA, "numeric_ten"))
)
BIRTHDATE_NORMALIZATION_REPLACEMENTS = _load_string_map(
    LOCALIZATION_DATA,
    "birthdate_normalization",
)
MEDICAL_TRIGGER_KEYWORDS = _flatten_aliases(
    _load_keyword_group(LOCALIZATION_DATA, "medical_trigger")
)
MEDICAL_HISTORY_KEYWORDS = _flatten_aliases(
    _load_keyword_group(LOCALIZATION_DATA, "medical_history_trigger")
)
RAW_NOTE_HINT_KEYWORDS = _flatten_aliases(
    _load_keyword_group(LOCALIZATION_DATA, "raw_note_hint")
)
DOG_CONTEXT_KEYWORDS_BY_LOCALE = _load_keyword_group(LOCALIZATION_DATA, "dog_context")
SEX_ALIASES_BY_LABEL = _load_alias_group(LOCALIZATION_DATA, "sex")
SEX_SINGLE_TOKEN_PATTERNS = _load_labeled_pattern_group(LOCALIZATION_DATA, "sex_single_token")
NEUTERED_ALIASES_BY_LABEL = _load_alias_group(LOCALIZATION_DATA, "neutered")
TEMPERAMENT_ALIASES_BY_LABEL = _load_alias_group(LOCALIZATION_DATA, "temperament")
ACTIVITY_ALIASES_BY_LABEL = _load_alias_group(LOCALIZATION_DATA, "activity_level")
DIET_ALIASES_BY_LABEL = _load_alias_group(LOCALIZATION_DATA, "diet")
FUZZY_AGE_ALIASES_BY_LABEL = _load_alias_group(LOCALIZATION_DATA, "fuzzy_age")


def _normalize_free_text(text: str) -> str:
    normalized = text.casefold().replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", normalized).strip()


def _find_alias_position(text: str, alias: str) -> int:
    if not alias:
        return -1
    if ASCII_ALIAS_PATTERN.fullmatch(alias):
        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        match = re.search(pattern, text, re.IGNORECASE)
        return match.start() if match is not None else -1
    return text.find(alias)


def split_message_clauses(message: str) -> list[str]:
    """Split a free-form message into simple clauses for rule-based parsing."""

    return [clause.strip() for clause in CLAUSE_SPLIT_PATTERN.split(message) if clause.strip()]


def _split_compound_values(value: str) -> list[str]:
    parts = [part.strip(" :：") for part in TEXT_SPLIT_PATTERN.split(value) if part.strip(" :：")]
    if not parts:
        return [value.strip(" :：")]
    return parts


def _round_half_up(value: float) -> int:
    return int(math.floor(value + 0.5))


def detect_dog_name(message: str) -> str | None:
    """Best-effort name extraction for the implicit profile-create path."""

    for pattern in DOG_NAME_PATTERNS:
        match = pattern.search(message)
        if match is None:
            continue
        candidate = match.group(1).strip(" ,，。.!！？;；")
        if candidate.casefold() in DOG_NAME_REJECTS:
            continue
        matched_text = match.group(0).strip()
        if _is_possessive_name_intro(matched_text) and not _looks_like_dog_profile_intro(message):
            continue
        return candidate
    return None


def _is_possessive_name_intro(matched_text: str) -> bool:
    stripped = matched_text.strip()
    return stripped.startswith(("我的", "我家")) and "是" in stripped


def _looks_like_dog_profile_intro(message: str) -> bool:
    if get_breed_matcher().match(message) is not None:
        return True
    if any(pattern.search(message) is not None for pattern in AGE_MONTH_HALF_PATTERNS):
        return True
    if any(pattern.search(message) is not None for pattern in AGE_MONTH_PATTERNS):
        return True
    if any(pattern.search(message) is not None for pattern in AGE_YEAR_PATTERNS):
        return True
    if any(pattern.search(message) is not None for pattern in BIRTHDATE_PATTERNS):
        return True
    if RuleBasedExtractor._extract_weight_kg(message) is not None:
        return True
    if RuleBasedExtractor._extract_sex(message) is not None:
        return True
    if RuleBasedExtractor._extract_neutered(message) is not None:
        return True
    if _contains_medical_trigger(message):
        return True
    return re.search(r"(?:狗|犬)", message) is not None


@dataclass(frozen=True)
class KeywordLabelMatcher:
    """Flatten locale-scoped keyword groups into a runtime matcher."""

    aliases_by_label: Mapping[str, Mapping[str, Sequence[str]]]
    _ordered_aliases: tuple[tuple[str, str], ...] = field(init=False, repr=False)
    _coverage: dict[str, int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        ordered_aliases: list[tuple[str, str]] = []
        coverage: dict[str, int] = {}
        seen: set[tuple[str, str]] = set()
        for label, aliases_by_locale in self.aliases_by_label.items():
            for locale, aliases in aliases_by_locale.items():
                coverage.setdefault(locale, 0)
                for alias in aliases:
                    normalized_alias = _normalize_free_text(alias)
                    if not normalized_alias or (label, normalized_alias) in seen:
                        continue
                    seen.add((label, normalized_alias))
                    ordered_aliases.append((normalized_alias, label))
                    coverage[locale] += 1
        ordered_aliases.sort(key=lambda item: len(item[0]), reverse=True)
        object.__setattr__(self, "_ordered_aliases", tuple(ordered_aliases))
        object.__setattr__(self, "_coverage", coverage)

    def match(self, text: str) -> str | None:
        normalized_text = _normalize_free_text(text)
        best_match: tuple[int, int, str] | None = None
        for alias, label in self._ordered_aliases:
            position = _find_alias_position(normalized_text, alias)
            if position == -1:
                continue
            match_key = (position, -len(alias), label)
            if best_match is None or match_key < best_match:
                best_match = match_key
        return best_match[2] if best_match is not None else None

    def matched_labels(self, text: str) -> set[str]:
        normalized_text = _normalize_free_text(text)
        matched: set[str] = set()
        for alias, label in self._ordered_aliases:
            if _find_alias_position(normalized_text, alias) != -1:
                matched.add(label)
        return matched

    def coverage_report(self) -> dict[str, int]:
        return dict(self._coverage)


@dataclass(frozen=True)
class BreedMatcher:
    """Data-driven breed matcher backed by a multilingual alias JSON file."""

    resource_package: str = BREED_DATA_PATH[0]
    resource_parts: tuple[str, ...] = BREED_DATA_PATH[1:]
    _ordered_aliases: tuple[tuple[str, str], ...] = field(init=False, repr=False)
    _coverage: dict[str, int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        resource = files(self.resource_package)
        for part in self.resource_parts:
            resource = resource.joinpath(part)
        raw = json.loads(resource.read_text(encoding="utf-8"))

        ordered_aliases: list[tuple[str, str]] = []
        coverage: dict[str, int] = {}
        seen: set[tuple[str, str]] = set()
        for entry in raw.values():
            canonical = str(entry["canonical"]).strip()
            aliases_by_locale = entry.get("aliases_by_locale", {})
            for locale, aliases in aliases_by_locale.items():
                coverage.setdefault(locale, 0)
                for alias in aliases:
                    normalized_alias = _normalize_free_text(str(alias))
                    if not normalized_alias or (canonical, normalized_alias) in seen:
                        continue
                    seen.add((canonical, normalized_alias))
                    ordered_aliases.append((normalized_alias, canonical))
                    coverage[locale] += 1
        ordered_aliases.sort(key=lambda item: len(item[0]), reverse=True)
        object.__setattr__(self, "_ordered_aliases", tuple(ordered_aliases))
        object.__setattr__(self, "_coverage", coverage)

    def match(self, text: str) -> str | None:
        normalized_text = _normalize_free_text(text)
        for alias, canonical in self._ordered_aliases:
            if _find_alias_position(normalized_text, alias) != -1:
                return canonical
        return None

    def coverage_report(self) -> dict[str, int]:
        return dict(self._coverage)


@lru_cache(maxsize=1)
def get_breed_matcher() -> BreedMatcher:
    return BreedMatcher()


@lru_cache(maxsize=1)
def get_dog_context_matcher() -> KeywordLabelMatcher:
    return KeywordLabelMatcher({"dog_context": DOG_CONTEXT_KEYWORDS_BY_LOCALE})


@lru_cache(maxsize=1)
def get_sex_matcher() -> KeywordLabelMatcher:
    return KeywordLabelMatcher(SEX_ALIASES_BY_LABEL)


@lru_cache(maxsize=1)
def get_neutered_matcher() -> KeywordLabelMatcher:
    return KeywordLabelMatcher(NEUTERED_ALIASES_BY_LABEL)


@lru_cache(maxsize=1)
def get_temperament_matcher() -> KeywordLabelMatcher:
    return KeywordLabelMatcher(TEMPERAMENT_ALIASES_BY_LABEL)


@lru_cache(maxsize=1)
def get_activity_matcher() -> KeywordLabelMatcher:
    return KeywordLabelMatcher(ACTIVITY_ALIASES_BY_LABEL)


@lru_cache(maxsize=1)
def get_diet_matcher() -> KeywordLabelMatcher:
    return KeywordLabelMatcher(DIET_ALIASES_BY_LABEL)


@lru_cache(maxsize=1)
def get_fuzzy_age_matcher() -> KeywordLabelMatcher:
    return KeywordLabelMatcher(FUZZY_AGE_ALIASES_BY_LABEL)


def _contains_medical_trigger(message: str) -> bool:
    lowered = message.casefold()
    return any(keyword.casefold() in lowered for keyword in MEDICAL_TRIGGER_KEYWORDS)


def _contains_raw_note_hint(message: str) -> bool:
    lowered = message.casefold()
    return any(keyword.casefold() in lowered for keyword in RAW_NOTE_HINT_KEYWORDS)


def _mentions_current_dog_name(message: str, current_profile: DogProfile | None) -> bool:
    if current_profile is None:
        return False
    candidate = current_profile.name.strip()
    if not candidate:
        return False
    if candidate.isascii() and len(candidate) < 3:
        return False
    return candidate.casefold() in message.casefold()


def looks_like_raw_note_candidate(message: str, current_profile: DogProfile | None = None) -> bool:
    stripped = message.strip()
    if not stripped:
        return False
    has_context = get_dog_context_matcher().match(stripped) is not None or _mentions_current_dog_name(
        stripped,
        current_profile,
    )
    if not has_context:
        return False
    return len(stripped) >= 48 or _contains_raw_note_hint(stripped)


def looks_like_dog_profile_trigger(message: str, current_profile: DogProfile | None = None) -> bool:
    """Return whether a message is worth escalating to an LLM extractor."""

    stripped = message.strip()
    if not stripped:
        return False
    if any(character.isdigit() for character in stripped):
        return True
    if len(stripped) >= 48:
        return True
    if _contains_medical_trigger(stripped):
        return True
    if get_breed_matcher().match(stripped) is not None:
        return True
    return looks_like_raw_note_candidate(stripped, current_profile)


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if "\n" in stripped:
            stripped = stripped.split("\n", 1)[1]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or start > end:
        raise ValueError("No JSON object found in LLM response.")
    return json.loads(stripped[start : end + 1])


def _parse_numeric_token(token: str) -> float | None:
    normalized = token.strip()
    for strip_token in NUMERIC_STRIP_TOKENS:
        normalized = normalized.replace(strip_token, "")
    if not normalized:
        return None
    try:
        return float(normalized)
    except ValueError:
        pass

    if normalized in HALF_TOKENS:
        return 0.5
    for half_token in HALF_TOKENS:
        if normalized.endswith(half_token) and normalized != half_token:
            base = _parse_numeric_token(normalized[: -len(half_token)])
            if base is not None:
                return base + 0.5
    if normalized in TEN_TOKENS:
        return 10.0
    for ten_token in TEN_TOKENS:
        if ten_token in normalized:
            left, _, right = normalized.partition(ten_token)
            tens = CHINESE_DIGIT_VALUES.get(left, 1) if left else 1
            ones = CHINESE_DIGIT_VALUES.get(right, 0) if right else 0
            return float(tens * 10 + ones)
    if normalized in CHINESE_DIGIT_VALUES:
        return float(CHINESE_DIGIT_VALUES[normalized])
    return None


def _parse_birthdate(raw_value: str) -> date | None:
    normalized = raw_value.strip()
    for source, target in BIRTHDATE_NORMALIZATION_REPLACEMENTS.items():
        normalized = normalized.replace(source, target)
    normalized = normalized.replace("/", "-").replace(".", "-")
    for fmt in ("%Y-%m-%d",):
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue
    return None


def _age_in_months_from_birthdate(raw_value: str, *, today: date) -> int | None:
    birthdate = _parse_birthdate(raw_value)
    if birthdate is None or birthdate > today:
        return None
    months = (today.year - birthdate.year) * 12 + (today.month - birthdate.month)
    if today.day < birthdate.day:
        months -= 1
    return max(months, 0)


def _merge_unique_strings(existing: list[str], incoming: list[str]) -> list[str]:
    merged = list(existing)
    seen = {item.casefold() for item in existing}
    for item in incoming:
        lowered = item.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        merged.append(item)
    return merged


@dataclass(frozen=True)
class RuleExtractionAssessment:
    """Internal rule-layer output plus escalation hints for the composite strategy."""

    result: ExtractionResult
    should_escalate: bool = False
    medical_triggered: bool = False
    raw_note_fallback_used: bool = False


@dataclass
class RuleBasedExtractor:
    """Fast rule-based extractor for explicit profile facts."""

    strategy_name: str = "rule"
    breed_matcher: BreedMatcher = field(default_factory=get_breed_matcher)
    now_provider: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    def extract(self, user_message: str, current_profile: DogProfile) -> ExtractionResult:
        return self.analyze(user_message, current_profile).result

    def analyze(self, user_message: str, current_profile: DogProfile) -> RuleExtractionAssessment:
        message = user_message.strip()
        clauses = split_message_clauses(message)
        used_clauses: set[str] = set()
        structured_fields: dict[str, Any] = {}
        medical_fields_detected = False
        resolved_age_confidence: float | None = None
        raw_note_candidate = looks_like_raw_note_candidate(message, current_profile)

        breed = self._extract_breed(message)
        if breed and breed != current_profile.breed:
            structured_fields["breed"] = breed

        age_months, age_confidence = self._extract_age_months(message)
        if age_months is not None and age_months != current_profile.age_months:
            structured_fields["age_months"] = age_months
            resolved_age_confidence = age_confidence

        weight_kg = self._extract_weight_kg(message)
        if weight_kg is not None and weight_kg != current_profile.weight_kg:
            structured_fields["weight_kg"] = weight_kg

        sex = self._extract_sex(message)
        if sex and sex != current_profile.sex:
            structured_fields["sex"] = sex

        neutered = self._extract_neutered(message)
        if neutered is not None and neutered != current_profile.neutered:
            structured_fields["neutered"] = neutered

        medical_history = self._extract_medical_history(clauses, used_clauses)
        if medical_history:
            structured_fields["medical_history"] = medical_history
            medical_fields_detected = True

        allergies = self._extract_allergies(clauses, used_clauses)
        if allergies:
            structured_fields["allergies"] = allergies
            medical_fields_detected = True

        medications = self._extract_medications(clauses, used_clauses)
        if medications:
            structured_fields["current_medications"] = medications
            medical_fields_detected = True

        temperament = self._extract_temperament(message, clauses, used_clauses)
        if temperament and temperament != current_profile.temperament:
            structured_fields["temperament"] = temperament

        activity_level = self._extract_activity_level(message)
        if activity_level and activity_level != current_profile.activity_level:
            structured_fields["activity_level"] = activity_level

        diet = self._extract_diet(message, clauses, used_clauses)
        if diet and diet != current_profile.diet:
            structured_fields["diet"] = diet

        raw_note = None
        raw_note_fallback_used = False
        if not structured_fields and raw_note_candidate:
            raw_note = message
            raw_note_fallback_used = True

        confidence = self._resolve_confidence(
            structured_fields=structured_fields,
            raw_note=raw_note,
            age_confidence=resolved_age_confidence,
            medical_fields_detected=medical_fields_detected,
        )
        result = ExtractionResult(
            structured_fields=structured_fields,
            raw_note=raw_note,
            confidence=confidence,
            strategy_used=self.strategy_name,
        )
        should_escalate = medical_fields_detected or raw_note_fallback_used
        if medical_fields_detected or _contains_medical_trigger(message):
            should_escalate = True
        return RuleExtractionAssessment(
            result=result,
            should_escalate=should_escalate,
            medical_triggered=medical_fields_detected or _contains_medical_trigger(message),
            raw_note_fallback_used=raw_note_fallback_used,
        )

    def _extract_breed(self, message: str) -> str | None:
        return self.breed_matcher.match(message)

    def _extract_age_months(self, message: str) -> tuple[int | None, float | None]:
        for pattern in AGE_MONTH_HALF_PATTERNS:
            match = pattern.search(message)
            if match is None:
                continue
            value = _parse_numeric_token(match.group("value"))
            if value is not None:
                return _round_half_up(value + 0.5), 0.7

        for pattern in AGE_MONTH_PATTERNS:
            match = pattern.search(message)
            if match is None:
                continue
            value = _parse_numeric_token(match.group("value"))
            if value is not None:
                return _round_half_up(value), 0.92

        for pattern in AGE_YEAR_PATTERNS:
            match = pattern.search(message)
            if match is None:
                continue
            value = _parse_numeric_token(match.group("value"))
            if value is None:
                continue
            half_group = match.groupdict().get("half")
            if half_group:
                value += 0.5
                return _round_half_up(value * 12), 0.75
            return _round_half_up(value * 12), 0.92

        today = self.now_provider().date()
        for pattern in BIRTHDATE_PATTERNS:
            match = pattern.search(message)
            if match is None:
                continue
            age_months = _age_in_months_from_birthdate(match.group("date"), today=today)
            if age_months is not None:
                return age_months, 0.88

        fuzzy_match = get_fuzzy_age_matcher().match(message)
        if fuzzy_match == "puppy":
            return 6, 0.55
        if fuzzy_match == "senior":
            return 108, 0.55
        return None, None

    @staticmethod
    def _extract_weight_kg(message: str) -> float | None:
        jin_match = JIN_PATTERN.search(message)
        if jin_match is not None:
            return round(float(jin_match.group("value")) * 0.5, 2)

        kg_match = KG_PATTERN.search(message)
        if kg_match is not None:
            return round(float(kg_match.group("value")), 2)

        lb_match = LB_PATTERN.search(message)
        if lb_match is not None:
            return round(float(lb_match.group("value")) * 0.4536, 2)
        return None

    @staticmethod
    def _extract_sex(message: str) -> str | None:
        matched_single_tokens = {
            label
            for label, patterns in SEX_SINGLE_TOKEN_PATTERNS.items()
            if any(pattern.search(message) is not None for pattern in patterns)
        }
        if len(matched_single_tokens) == 1:
            return next(iter(matched_single_tokens))
        if len(matched_single_tokens) > 1:
            return None
        labels = get_sex_matcher().matched_labels(message)
        if len(labels) != 1:
            return None
        return next(iter(labels))

    @staticmethod
    def _extract_neutered(message: str) -> bool | None:
        labels = get_neutered_matcher().matched_labels(message)
        if "negative" in labels:
            return False
        if "positive" in labels:
            return True
        return None

    @staticmethod
    def _extract_allergies(clauses: list[str], used_clauses: set[str]) -> list[str]:
        extracted: list[str] = []
        for clause in clauses:
            for pattern in ALLERGY_PATTERNS:
                match = pattern.search(clause)
                if match is None:
                    continue
                extracted = _merge_unique_strings(extracted, _split_compound_values(match.group("value")))
                used_clauses.add(clause)
        return extracted

    @staticmethod
    def _extract_medications(clauses: list[str], used_clauses: set[str]) -> list[str]:
        extracted: list[str] = []
        for clause in clauses:
            for pattern in MEDICATION_PATTERNS:
                match = pattern.search(clause)
                if match is None:
                    continue
                extracted = _merge_unique_strings(extracted, _split_compound_values(match.group("value")))
                used_clauses.add(clause)
        return extracted

    @staticmethod
    def _extract_medical_history(clauses: list[str], used_clauses: set[str]) -> list[str]:
        extracted: list[str] = []
        for clause in clauses:
            for pattern in MEDICAL_HISTORY_PATTERNS:
                match = pattern.search(clause)
                if match is None:
                    continue
                value = match.groupdict().get("value") or clause
                extracted = _merge_unique_strings(extracted, [value.strip()])
                used_clauses.add(clause)
                break
            else:
                lowered = clause.casefold()
                if clause not in used_clauses and any(keyword.casefold() in lowered for keyword in MEDICAL_HISTORY_KEYWORDS):
                    extracted = _merge_unique_strings(extracted, [clause])
                    used_clauses.add(clause)
        return extracted

    @staticmethod
    def _extract_temperament(message: str, clauses: list[str], used_clauses: set[str]) -> str | None:
        label = get_temperament_matcher().match(message)
        if label is None:
            return None
        for clause in clauses:
            if get_temperament_matcher().match(clause) == label:
                used_clauses.add(clause)
                break
        return label

    @staticmethod
    def _extract_activity_level(message: str) -> str | None:
        return get_activity_matcher().match(message)

    @staticmethod
    def _extract_diet(message: str, clauses: list[str], used_clauses: set[str]) -> str | None:
        label = get_diet_matcher().match(message)
        if label is None:
            return None
        for clause in clauses:
            if get_diet_matcher().match(clause) == label:
                used_clauses.add(clause)
                break
        return label

    @staticmethod
    def _resolve_confidence(
        *,
        structured_fields: Mapping[str, Any],
        raw_note: str | None,
        age_confidence: float | None,
        medical_fields_detected: bool,
    ) -> float:
        if structured_fields:
            medical_field_names = {"medical_history", "allergies", "current_medications"}
            if set(structured_fields).issubset(medical_field_names):
                return 0.72
            if age_confidence is not None and age_confidence < 0.92 and len(structured_fields) == 1:
                return age_confidence
            if age_confidence is not None and age_confidence < 0.92:
                return 0.84
            if medical_fields_detected:
                return 0.84
            return 0.92
        if raw_note:
            return 0.45
        return 0.0


@dataclass
class GeminiStructuredExtractorClient:
    """Thin Vertex AI Gemini client for JSON-only extraction responses."""

    model_name: str
    project_id: str
    location: str
    api_key: str | None = None
    credentials: Credentials | None = None
    timeout_seconds: int = 15
    initializer: Callable[..., None] = vertexai.init
    model_factory: Callable[[str], Any] = GenerativeModel

    def extract_structured_fields(
        self,
        *,
        user_message: str,
        current_profile: DogProfile,
        rule_hints: Mapping[str, Any] | None = None,
        rule_raw_note: str | None = None,
    ) -> dict[str, Any]:
        response = _retry_external_call(
            operation=lambda: self._generate_structured_fields_content(
                user_message=user_message,
                current_profile=current_profile,
                rule_hints=rule_hints,
                rule_raw_note=rule_raw_note,
            ),
            failure_message=(
                f"Failed to reach Gemini model '{self.model_name}' through Vertex AI."
            ),
            log_message="dog_profile.gemini_request_failed_after_retries",
            log_context={
                "model_name": self.model_name,
                "project_id": self.project_id,
                "location": self.location,
            },
        )

        try:
            response_text = str(getattr(response, "text", "") or "").strip()
        except Exception as exc:
            raise AdapterError("Gemini returned an unreadable extraction payload.") from exc

        if not response_text:
            raise AdapterError("Gemini returned an empty extraction payload.")

        try:
            return _extract_json_object(response_text)
        except Exception as exc:
            raise AdapterError("Gemini returned an invalid extraction payload.") from exc

    def _generate_structured_fields_content(
        self,
        *,
        user_message: str,
        current_profile: DogProfile,
        rule_hints: Mapping[str, Any] | None,
        rule_raw_note: str | None,
    ) -> Any:
        self.initializer(
            project=self.project_id,
            location=self.location,
            credentials=self.credentials,
            api_key=self.api_key,
        )
        return self.model_factory(self.model_name).generate_content(
            self._build_prompt(
                user_message=user_message,
                current_profile=current_profile,
                rule_hints=rule_hints,
                rule_raw_note=rule_raw_note,
            ),
            generation_config=GenerationConfig(
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )

    @staticmethod
    def _build_prompt(
        *,
        user_message: str,
        current_profile: DogProfile,
        rule_hints: Mapping[str, Any] | None,
        rule_raw_note: str | None,
    ) -> str:
        profile_json = json.dumps(
            current_profile.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
        )
        hint_payload = {
            "structured_fields": dict(rule_hints or {}),
            "raw_note": rule_raw_note,
        }
        hint_json = json.dumps(hint_payload, ensure_ascii=False, sort_keys=True)
        return (
            "Extract new or changed dog profile facts from the user message.\n"
            "Return JSON only with this exact shape:\n"
            '{"structured_fields": {}, "raw_note": null, "confidence": 0.0}\n'
            "Rules:\n"
            "- Only include fields that are empty in the current profile or clearly changed.\n"
            "- Allowed structured field names: "
            "name, breed, age_months, weight_kg, sex, neutered, medical_history, "
            "allergies, current_medications, temperament, activity_level, diet.\n"
            "- Convert age to months and weight to kilograms.\n"
            "- Use arrays for medical_history, allergies, and current_medications.\n"
            "- Use raw_note only for useful dog details that cannot be structured cleanly.\n"
            "- Rule-based hints are candidate evidence from deterministic parsing. Reuse them when "
            "they are supported by the user message, especially for medical details, but normalize "
            "or discard them if they are wrong.\n"
            "- Do not invent facts.\n"
            f"Current profile: {profile_json}\n"
            f"Rule-based hints: {hint_json}\n"
            f"User message: {user_message}"
        )


@dataclass
class _BaseLLMExtractor:
    """Shared LLM extraction logic."""

    client: GeminiStructuredExtractorClient
    strategy_name: str

    def extract(self, user_message: str, current_profile: DogProfile) -> ExtractionResult:
        return self.extract_with_hints(
            user_message=user_message,
            current_profile=current_profile,
            rule_hints=None,
            rule_raw_note=None,
        )

    def extract_with_hints(
        self,
        *,
        user_message: str,
        current_profile: DogProfile,
        rule_hints: Mapping[str, Any] | None,
        rule_raw_note: str | None,
    ) -> ExtractionResult:
        payload = self.client.extract_structured_fields(
            user_message=user_message,
            current_profile=current_profile,
            rule_hints=rule_hints,
            rule_raw_note=rule_raw_note,
        )
        return ExtractionResult.model_validate(
            {
                "structured_fields": payload.get("structured_fields", {}),
                "raw_note": payload.get("raw_note"),
                "confidence": payload.get("confidence", 0.0),
                "strategy_used": self.strategy_name,
            }
        )


@dataclass
class LLMFlashExtractor(_BaseLLMExtractor):
    """Gemini Flash-backed extractor."""

    strategy_name: str = "flash"


@dataclass
class LLMProExtractor(_BaseLLMExtractor):
    """Gemini Pro-backed extractor reserved for harder cases."""

    strategy_name: str = "pro"


def _merge_extraction_results(rule_result: ExtractionResult, flash_result: ExtractionResult) -> ExtractionResult:
    merged_fields = dict(rule_result.structured_fields)
    for field_name, value in flash_result.structured_fields.items():
        merged_fields[field_name] = value
    return ExtractionResult(
        structured_fields=merged_fields,
        raw_note=flash_result.raw_note or rule_result.raw_note,
        confidence=max(rule_result.confidence, flash_result.confidence),
        strategy_used=flash_result.strategy_used,
    )


@dataclass
class CompositeExtractor:
    """Default strategy: rule first, then Flash when escalation is warranted."""

    rule_extractor: RuleBasedExtractor = field(default_factory=RuleBasedExtractor)
    flash_extractor: LLMFlashExtractor | None = None
    strategy_name: str = "composite"

    def extract(self, user_message: str, current_profile: DogProfile) -> ExtractionResult:
        assessment = self.rule_extractor.analyze(user_message, current_profile)
        rule_result = assessment.result
        if self.flash_extractor is None or not assessment.should_escalate:
            return rule_result

        flash_result = self.flash_extractor.extract_with_hints(
            user_message=user_message,
            current_profile=current_profile,
            rule_hints=rule_result.structured_fields,
            rule_raw_note=rule_result.raw_note,
        )
        if flash_result.structured_fields or flash_result.raw_note:
            return _merge_extraction_results(rule_result, flash_result)
        return rule_result
