"""Localized non-LLM turn messages and locale resolution helpers."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
import json
import re
from typing import Any, Mapping, Sequence

from tailmate.adapters.dog_profile.extractors import detect_dog_name
from tailmate.contracts.dog_profile import DogProfile


DEFAULT_LOCALE = "en-AU"
SUPPORTED_LOCALES = ("en-AU", "zh-Hans", "ar", "vi", "yue", "hi")
PREFERRED_LOCALE_ATTRIBUTE = "preferred_locale"
UNSUPPORTED_LOCALE_DEFAULT_REASON = "unsupported_locale_defaulted_to_english"
PREFERRED_LOCALE_METADATA_KEYS = (
    "preferred_locale",
    "preferred_language",
    "locale",
    "language",
)
ARABIC_PATTERN = re.compile(r"[\u0600-\u06FF]")
DEVANAGARI_PATTERN = re.compile(r"[\u0900-\u097F]")
HAN_PATTERN = re.compile(r"[\u3400-\u9FFF]")
VIETNAMESE_DIACRITICS_PATTERN = re.compile(
    r"[ăâđêôơưĂÂĐÊÔƠƯáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệ"
    r"íìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]"
)
CATALOG_RESOURCE_NAME = "turn_messages.json"
ROUTING_PATTERNS_RESOURCE_NAME = "turn_routing_patterns.json"
CANTONESE_MARKERS = (
    "佢",
    "咗",
    "喺",
    "冇",
    "嘅",
    "咩",
    "啲",
    "而家",
    "係咪",
    "唔",
    "咁",
)
VIETNAMESE_MARKERS = (
    "xin chào",
    "xin chao",
    "con chó",
    "con cho",
    "giúp",
    "giup",
    "giống",
    "giong",
    "tuổi",
    "tuoi",
    "cân nặng",
    "can nang",
)


def _read_json_resource(resource_name: str) -> dict[str, Any]:
    resource = files("tailmate.agent_runtime.services").joinpath(resource_name)
    return json.loads(resource.read_text(encoding="utf-8"))


def _coerce_aliases_by_locale(
    raw_aliases: Mapping[str, Sequence[str]],
) -> dict[str, tuple[str, ...]]:
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


@lru_cache(maxsize=1)
def _load_routing_patterns() -> dict[str, Any]:
    return _read_json_resource(ROUTING_PATTERNS_RESOURCE_NAME)


def _load_keyword_group(group_name: str) -> dict[str, tuple[str, ...]]:
    return _coerce_aliases_by_locale(
        _load_routing_patterns()["keyword_groups"][group_name]["aliases_by_locale"]
    )


GREETING_PATTERNS = _load_keyword_group("greeting")
CAPABILITY_PATTERNS = _load_keyword_group("capability")
PROFILE_RECALL_REFERENCE_PATTERNS = _flatten_aliases(
    _load_keyword_group("profile_recall_reference")
)
PROFILE_RECALL_QUESTION_PATTERNS = _flatten_aliases(
    _load_keyword_group("profile_recall_question")
)
QUESTION_PATTERNS = _flatten_aliases(_load_keyword_group("question"))
QUESTION_LEAD_PATTERNS = _flatten_aliases(_load_keyword_group("question_lead"))
INLINE_QUESTION_PATTERNS = _flatten_aliases(_load_keyword_group("inline_question"))
FOLLOW_UP_REFERENCE_PATTERNS = _load_keyword_group("follow_up_reference")
DOG_SWITCH_PATTERNS = _load_keyword_group("dog_switch")
CJK_FALLBACK_LOCALES = {"zh-Hans", "yue"}
DOG_PROFILE_RECALL_FIELD_ORDER = (
    "breed",
    "age_months",
    "weight_kg",
    "sex",
    "neutered",
    "medical_history",
    "allergies",
    "current_medications",
    "temperament",
    "activity_level",
    "diet",
    "raw_notes",
)
DOG_PROFILE_CONTEXT_FIELD_ORDER = (
    "breed",
    "age_months",
    "weight_kg",
    "sex",
    "neutered",
    "medical_history",
    "allergies",
    "current_medications",
    "temperament",
    "activity_level",
    "diet",
)


@dataclass(frozen=True)
class LocaleResolution:
    """Result of resolving one turn into a supported locale."""

    locale: str
    source: str
    requested_locale: str | None = None
    locale_fallback_reason: str | None = None


@dataclass(frozen=True)
class LocalizedTurnMessage:
    """Localized message together with the catalog key used to resolve it."""

    key: str
    text: str


@lru_cache(maxsize=1)
def _load_catalog() -> dict[str, Any]:
    return _read_json_resource(CATALOG_RESOURCE_NAME)


def normalize_locale(value: Any) -> str | None:
    """Normalize user- or client-supplied locale aliases into supported locales."""

    if value is None:
        return None
    raw_value = str(value).strip()
    if not raw_value:
        return None

    lowered = raw_value.replace("_", "-").casefold()
    aliases = {
        "en": "en-AU",
        "en-au": "en-AU",
        "english": "en-AU",
        "zh": "zh-Hans",
        "zh-cn": "zh-Hans",
        "zh-sg": "zh-Hans",
        "zh-hans": "zh-Hans",
        "mandarin": "zh-Hans",
        "cmn": "zh-Hans",
        "chinese": "zh-Hans",
        "ar": "ar",
        "arabic": "ar",
        "vi": "vi",
        "vi-vn": "vi",
        "vietnamese": "vi",
        "yue": "yue",
        "zh-yue": "yue",
        "zh-hk": "yue",
        "cantonese": "yue",
        "hi": "hi",
        "hi-in": "hi",
        "hindi": "hi",
    }
    if lowered in aliases:
        return aliases[lowered]
    if lowered.startswith("zh"):
        return "zh-Hans"
    if lowered.startswith("en"):
        return "en-AU"
    if lowered.startswith("ar"):
        return "ar"
    if lowered.startswith("vi"):
        return "vi"
    if lowered.startswith("yue"):
        return "yue"
    if lowered.startswith("hi"):
        return "hi"
    return None


def resolve_locale(
    *,
    message: str,
    request_metadata: Mapping[str, Any],
    context_attributes: Mapping[str, Any],
) -> LocaleResolution:
    """Resolve locale from request metadata, session preference, or message heuristics."""

    requested_from_metadata = _first_requested_locale(request_metadata)
    if requested_from_metadata is not None:
        normalized = normalize_locale(requested_from_metadata)
        if normalized is not None:
            return LocaleResolution(
                locale=normalized,
                source="metadata",
                requested_locale=requested_from_metadata,
            )
        return LocaleResolution(
            locale=DEFAULT_LOCALE,
            source="default",
            requested_locale=requested_from_metadata,
            locale_fallback_reason=UNSUPPORTED_LOCALE_DEFAULT_REASON,
        )

    requested_from_context = _first_requested_locale(
        {PREFERRED_LOCALE_ATTRIBUTE: context_attributes.get(PREFERRED_LOCALE_ATTRIBUTE)}
    )
    if requested_from_context is not None:
        normalized = normalize_locale(requested_from_context)
        if normalized is not None:
            return LocaleResolution(
                locale=normalized,
                source="context",
                requested_locale=requested_from_context,
            )
        return LocaleResolution(
            locale=DEFAULT_LOCALE,
            source="default",
            requested_locale=requested_from_context,
            locale_fallback_reason=UNSUPPORTED_LOCALE_DEFAULT_REASON,
        )

    detected_locale = detect_locale(message)
    if detected_locale is not None:
        return LocaleResolution(locale=detected_locale, source="detected")
    return LocaleResolution(locale=DEFAULT_LOCALE, source="default")


def detect_locale(message: str) -> str | None:
    """Best-effort locale detection across the supported non-LLM fallback locales."""

    stripped = message.strip()
    if not stripped:
        return None
    lowered = stripped.casefold()

    if ARABIC_PATTERN.search(stripped):
        return "ar"
    if DEVANAGARI_PATTERN.search(stripped):
        return "hi"
    if VIETNAMESE_DIACRITICS_PATTERN.search(stripped):
        return "vi"
    if any(marker in lowered for marker in VIETNAMESE_MARKERS):
        return "vi"
    if HAN_PATTERN.search(stripped):
        if any(marker in stripped for marker in CANTONESE_MARKERS):
            return "yue"
        return "zh-Hans"
    return None


def classify_fallback_reason(
    message: str,
    locale: str,
    *,
    context_attributes: Mapping[str, Any] | None = None,
    turns: list[dict[str, Any]] | None = None,
) -> str:
    """Classify a non-skill turn into one of the supported fallback buckets."""

    lowered = message.strip().casefold()
    if lowered and _contains_locale_pattern(lowered, GREETING_PATTERNS.get(locale, ()), locale):
        return "fallback.greeting"
    if lowered and _contains_locale_pattern(lowered, CAPABILITY_PATTERNS.get(locale, ()), locale):
        return "fallback.capability_inquiry"
    if _has_active_dog(context_attributes) and message_contains_question(message):
        return "fallback.profile_query"
    if _follows_knowledge_base_turn(turns) and _looks_like_follow_up(message, locale):
        return "fallback.post_kb_followup"
    return "fallback.no_skill_matched"


def is_referential_follow_up(message: str, locale: str) -> bool:
    """Return whether a turn looks like a short referential follow-up."""

    lowered = message.strip().casefold()
    if not lowered:
        return False
    return _contains_follow_up_reference(lowered, locale)


def localize_message(key: str, locale: str, **params: Any) -> LocalizedTurnMessage:
    """Resolve one message key into the selected locale with English fallback."""

    catalog = _load_catalog()
    normalized_locale = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    locale_messages = catalog.get(normalized_locale, {}).get("messages", {})
    default_messages = catalog[DEFAULT_LOCALE]["messages"]
    template = locale_messages.get(key, default_messages.get(key, key))
    return LocalizedTurnMessage(key=key, text=template.format(**params))


def build_create_confirmation(*, locale: str, name: str) -> LocalizedTurnMessage:
    """Build a localized dog-profile create confirmation."""

    return localize_message("dog_profile.create_confirmation", locale, name=name)


def build_enrich_confirmation(
    *,
    locale: str,
    updated_fields: tuple[str, ...],
    raw_note_present: bool,
) -> LocalizedTurnMessage:
    """Build a localized dog-profile enrichment confirmation."""

    if updated_fields:
        localized_fields = ", ".join(localize_field_labels(updated_fields, locale))
        return localize_message(
            "dog_profile.enrich_confirmation",
            locale,
            fields=localized_fields,
        )
    if raw_note_present:
        return localize_message("dog_profile.note_confirmation", locale)
    return localize_message("fallback.no_skill_matched", locale)


def build_dog_profile_recall_summary(
    *,
    locale: str,
    profile: DogProfile,
) -> LocalizedTurnMessage:
    """Build a localized dog-profile recall summary."""

    summary = _format_profile_summary(profile, locale)
    if summary is None:
        return localize_message("dog_profile.recall_no_details", locale, name=profile.name)
    return localize_message(
        "dog_profile.recall_summary",
        locale,
        name=profile.name,
        summary=summary,
    )


def build_active_dog_switch_confirmation(
    *,
    locale: str,
    name: str,
) -> LocalizedTurnMessage:
    """Build a localized active-dog switch confirmation."""

    return localize_message("dog_profile.switch_confirmation", locale, name=name)


def build_active_dog_selection_prompt(
    *,
    locale: str,
    dog_names: tuple[str, ...],
) -> LocalizedTurnMessage:
    """Build a localized disambiguation prompt for multi-dog users."""

    return localize_message(
        "dog_profile.switch_prompt",
        locale,
        dog_names=", ".join(dog_names),
    )


def build_enrich_and_answer_message(
    *,
    locale: str,
    updated_fields: tuple[str, ...],
    raw_note_present: bool,
    answer_text: str,
) -> LocalizedTurnMessage:
    """Build a combined localized enrich confirmation and knowledge answer."""

    enrich_message = build_enrich_confirmation(
        locale=locale,
        updated_fields=updated_fields,
        raw_note_present=raw_note_present,
    )
    return localize_message(
        "dog_profile.enrich_and_answer",
        locale,
        enrich_confirmation=enrich_message.text,
        answer=answer_text,
    )


def build_strip_metadata_confirmation(
    *,
    locale: str,
    resource_uri: str,
) -> LocalizedTurnMessage:
    """Build a localized strip-metadata success confirmation."""

    return localize_message("strip_metadata.success", locale, resource_uri=resource_uri)


def build_knowledge_base_answer(
    *,
    locale: str,
    answer: str,
    sources: list[str],
) -> LocalizedTurnMessage:
    """Build a localized knowledge-base answer wrapper."""

    sources_text = ", ".join(sources)
    return localize_message(
        "knowledge_base.answer",
        locale,
        answer=answer,
        sources=sources_text,
    )


def build_knowledge_base_out_of_scope(*, locale: str) -> LocalizedTurnMessage:
    """Build the localized knowledge-base out-of-scope response."""

    return localize_message("knowledge_base.out_of_scope", locale)


def build_platform_link_required_message(
    *,
    locale: str,
    login_url: str,
) -> LocalizedTurnMessage:
    """Build the localized bind-your-platform-account response."""

    return localize_message("platform.link_required", locale, login_url=login_url)


def build_llm_safety_redirect(*, locale: str) -> LocalizedTurnMessage:
    """Build the localized hard-stop vet redirect response."""

    return localize_message("llm.safety_redirect", locale)


def build_fallback_message(
    *,
    locale: str,
    reason: str,
    dog_name: str | None = None,
) -> LocalizedTurnMessage:
    """Build a localized fallback response from the classified reason key."""

    if reason == "fallback.greeting" and dog_name is not None:
        normalized_name = dog_name.strip()
        if normalized_name:
            return localize_message(
                "fallback.greeting_returning",
                locale,
                name=normalized_name,
            )
    return localize_message(reason, locale)


def build_skill_error_message(*, locale: str) -> LocalizedTurnMessage:
    """Build the localized user-facing skill-error fallback."""

    return localize_message("error.skill_exception", locale)


def build_session_welcome(*, locale: str) -> LocalizedTurnMessage:
    """Build the localized proactive welcome message for a fresh session."""

    return localize_message("session.welcome", locale)


def message_contains_question(message: str) -> bool:
    """Return whether the message appears to contain a question."""

    lowered = message.strip().casefold()
    if not lowered:
        return False
    if any(pattern in lowered for pattern in QUESTION_PATTERNS):
        return True
    if any(pattern in lowered for pattern in INLINE_QUESTION_PATTERNS):
        return True
    clauses = re.split(r"[.!;\n]+", lowered)
    return any(
        clause.strip().startswith(pattern)
        for clause in clauses
        for pattern in QUESTION_LEAD_PATTERNS
    )


def is_dog_profile_recall_query(message: str, *, dog_name: str | None) -> bool:
    """Return whether a turn is asking to recall the current dog's stored profile."""

    stripped = message.strip()
    if not stripped:
        return False
    lowered = stripped.casefold()
    references_current_dog = any(pattern in lowered for pattern in PROFILE_RECALL_REFERENCE_PATTERNS)
    if dog_name is not None:
        normalized_name = dog_name.strip()
        if normalized_name:
            references_current_dog = references_current_dog or normalized_name.casefold() in lowered
    if not references_current_dog:
        return False
    return any(pattern in lowered for pattern in PROFILE_RECALL_QUESTION_PATTERNS)


def is_explicit_dog_switch_request(message: str, locale: str) -> bool:
    """Return whether the current turn explicitly asks to change the active dog."""

    lowered = message.strip().casefold()
    if not lowered:
        return False
    return _contains_locale_pattern(lowered, DOG_SWITCH_PATTERNS.get(locale, ()), locale)


def should_prompt_for_dog_selection(message: str, locale: str) -> bool:
    """Return whether the user likely needs to choose one dog before continuing."""

    if is_explicit_dog_switch_request(message, locale):
        return True
    if is_dog_profile_recall_query(message, dog_name=None):
        return True
    return looks_like_dog_profile_update(message)


def looks_like_dog_profile_update(message: str) -> bool:
    """Return whether a turn looks like a dog-specific profile update statement."""

    stripped = message.strip()
    if not stripped:
        return False
    return detect_dog_name(stripped) is not None or _looks_like_profile_fact_statement(stripped)


def localize_field_labels(field_names: tuple[str, ...], locale: str) -> list[str]:
    """Resolve structured field names into localized labels."""

    catalog = _load_catalog()
    normalized_locale = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    locale_fields = catalog.get(normalized_locale, {}).get("fields", {})
    default_fields = catalog[DEFAULT_LOCALE]["fields"]
    labels: list[str] = []
    for field_name in field_names:
        labels.append(locale_fields.get(field_name, default_fields.get(field_name, field_name)))
    return labels


def resolve_greeting_dog_name(
    *,
    context_attributes: Mapping[str, Any] | None = None,
    current_dog_profile: DogProfile | None = None,
    turns: Sequence[Mapping[str, Any]] | None = None,
) -> str | None:
    """Resolve the best available dog name for a returning-user greeting."""

    if current_dog_profile is not None:
        normalized_name = str(current_dog_profile.name).strip()
        if normalized_name:
            return normalized_name

    if context_attributes is not None:
        candidate = context_attributes.get("dog_name")
        if candidate is not None:
            normalized_name = str(candidate).strip()
            if normalized_name:
                return normalized_name

    if turns is None:
        return None

    for turn in reversed(turns):
        if str(turn.get("role", "")).strip() != "user":
            continue
        candidate = detect_dog_name(str(turn.get("message", "")))
        if candidate is not None:
            return candidate
    return None


def _format_profile_summary(profile: DogProfile, locale: str) -> str | None:
    fragments: list[str] = []
    for field_name in DOG_PROFILE_RECALL_FIELD_ORDER:
        value = getattr(profile, field_name)
        if value in (None, "", []):
            continue
        fragments.append(
            f"{localize_field_labels((field_name,), locale)[0]}: {_format_profile_value(field_name, value, locale)}"
        )
    if not fragments:
        return None
    return ", ".join(fragments)


def format_dog_profile_context(profile: DogProfile, locale: str) -> str:
    """Format a compact dog-profile snapshot for downstream KB prompting."""

    fragments: list[str] = []
    for field_name in DOG_PROFILE_CONTEXT_FIELD_ORDER:
        value = getattr(profile, field_name)
        if value in (None, "", []):
            continue
        fragments.append(
            f"{localize_field_labels((field_name,), locale)[0]}: {_format_profile_value(field_name, value, locale)}"
        )
    if not fragments:
        return f"Dog: {profile.name}."
    return f"Dog: {profile.name}. " + ", ".join(fragments) + "."


def _format_profile_value(field_name: str, value: Any, locale: str) -> str:
    if field_name == "age_months":
        return _format_age_months(int(value), locale)
    if field_name == "weight_kg":
        weight = float(value)
        return f"{weight:g} kg"
    if field_name == "neutered":
        return _format_bool(bool(value), locale)
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _format_age_months(age_months: int, locale: str) -> str:
    if age_months >= 12 and age_months % 12 == 0:
        years = age_months // 12
        if locale == "zh-Hans":
            return f"{years}岁"
        if locale == "ar":
            return f"{years} years"
        if locale == "vi":
            return f"{years} tuổi"
        if locale == "yue":
            return f"{years}歲"
        if locale == "hi":
            return f"{years} साल"
        return f"{years} years"
    if locale == "zh-Hans":
        return f"{age_months}个月"
    if locale == "ar":
        return f"{age_months} months"
    if locale == "vi":
        return f"{age_months} tháng"
    if locale == "yue":
        return f"{age_months}個月"
    if locale == "hi":
        return f"{age_months} महीने"
    return f"{age_months} months"


def _format_bool(value: bool, locale: str) -> str:
    if locale == "zh-Hans":
        return "是" if value else "否"
    if locale == "ar":
        return "نعم" if value else "لا"
    if locale == "vi":
        return "có" if value else "không"
    if locale == "yue":
        return "有" if value else "冇"
    if locale == "hi":
        return "हाँ" if value else "नहीं"
    return "yes" if value else "no"


def _first_requested_locale(values: Mapping[str, Any]) -> str | None:
    for key in PREFERRED_LOCALE_METADATA_KEYS:
        raw_value = values.get(key)
        if raw_value is None:
            continue
        text = str(raw_value).strip()
        if text:
            return text
    return None


def _has_active_dog(context_attributes: Mapping[str, Any] | None) -> bool:
    if context_attributes is None:
        return False
    candidate = context_attributes.get("active_dog_id") or context_attributes.get("dog_id")
    if candidate is None:
        return False
    return bool(str(candidate).strip())


def _follows_knowledge_base_turn(turns: list[dict[str, Any]] | None) -> bool:
    if not turns:
        return False
    for turn in reversed(turns):
        if str(turn.get("role", "")).strip() != "assistant":
            continue
        return str(turn.get("source", "")).strip() == "knowledge_base"
    return False


def _looks_like_follow_up(message: str, locale: str) -> bool:
    lowered = message.strip().casefold()
    if not lowered:
        return False
    return _is_short_message(lowered, locale) or _contains_follow_up_reference(lowered, locale)


def _contains_follow_up_reference(message: str, locale: str) -> bool:
    patterns = FOLLOW_UP_REFERENCE_PATTERNS.get(locale, ())
    if locale in CJK_FALLBACK_LOCALES:
        return any(pattern in message for pattern in patterns)
    tokens = _tokenize_words(message)
    if not tokens:
        return False
    for pattern in patterns:
        pattern_tokens = tuple(_tokenize_words(pattern.casefold()))
        if not pattern_tokens:
            continue
        if _contains_token_sequence(tokens, pattern_tokens):
            return True
    return False


def _contains_locale_pattern(message: str, patterns: tuple[str, ...], locale: str) -> bool:
    if locale in CJK_FALLBACK_LOCALES:
        return any(pattern.casefold() in message for pattern in patterns)
    tokens = _tokenize_words(message)
    if not tokens:
        return False
    for pattern in patterns:
        pattern_tokens = tuple(_tokenize_words(pattern.casefold()))
        if not pattern_tokens:
            continue
        if _contains_token_sequence(tokens, pattern_tokens):
            return True
    return False


def _is_short_message(message: str, locale: str) -> bool:
    if locale in CJK_FALLBACK_LOCALES:
        non_space_length = len("".join(message.split()))
        return 0 < non_space_length < 12
    words = _tokenize_words(message)
    return bool(words) and len(words) < 10


def _looks_like_profile_fact_statement(message: str) -> bool:
    lowered = message.casefold()
    if any(token in lowered for token in (" years old", " kg", " kilograms", " breed", " weight")):
        return True
    if any(token in message for token in ("岁", "公斤", "體重", "体重", "品种", "品種")):
        return True
    return False


def _tokenize_words(message: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", message, flags=re.UNICODE))


def _contains_token_sequence(tokens: tuple[str, ...], pattern_tokens: tuple[str, ...]) -> bool:
    window_size = len(pattern_tokens)
    if window_size == 0 or window_size > len(tokens):
        return False
    return any(tokens[index : index + window_size] == pattern_tokens for index in range(len(tokens) - window_size + 1))
