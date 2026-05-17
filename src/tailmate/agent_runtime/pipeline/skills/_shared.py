"""Shared helpers for runtime skill classification and active-dog selection."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from tailmate.adapters.dog_profile.extractors import detect_dog_name
from tailmate.agent_runtime.pipeline.steps._tool_finder import find_tool
from tailmate.agent_runtime.pipeline.turn_context import SkillExecutionResult, TurnContext
from tailmate.agent_runtime.ports.dog_profile_db_adapter import DogProfileDBAdapter
from tailmate.agent_runtime.ports.skill_registry import SkillRegistry
from tailmate.agent_runtime.services.turn_messages import (
    is_dog_profile_recall_query,
    is_explicit_dog_switch_request,
    should_prompt_for_dog_selection,
)
from tailmate.contracts.constants import ACTIVE_DOG_ID_ATTRIBUTE_KEY
from tailmate.contracts.dog_profile import DogProfile


@dataclass(frozen=True)
class DogSelectionResolution:
    """Resolved active-dog state for the current turn."""

    active_dog_id: str | None
    current_active_dog_id: str | None
    active_profile: DogProfile | None = None
    available_profiles: tuple[DogProfile, ...] = ()
    matched_by_name: bool = False
    explicit_switch: bool = False
    needs_disambiguation: bool = False


def _normalize_dog_id(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def resolve_active_dog_id(context: Any, request_metadata: dict[str, Any]) -> str | None:
    """Resolve the active dog id from request metadata or session attributes."""

    for candidate in (
        request_metadata.get("dog_id"),
        context.attributes.get(ACTIVE_DOG_ID_ATTRIBUTE_KEY),
        context.attributes.get("dog_id"),
    ):
        normalized = _normalize_dog_id(candidate)
        if normalized is not None:
            return normalized
    return None


def persist_active_dog(attributes: dict[str, Any], dog_id: str) -> None:
    """Persist the canonical active-dog selection while preserving legacy compatibility."""

    attributes[ACTIVE_DOG_ID_ATTRIBUTE_KEY] = dog_id
    attributes["dog_id"] = dog_id


def list_known_dog_profiles(
    request_metadata: dict[str, Any],
    dog_profile_db_adapter: DogProfileDBAdapter | None,
) -> tuple[DogProfile, ...]:
    """Return the current user's known dog profiles when the adapter supports listing."""

    verified_user_id = str(request_metadata.get("user_id", "")).strip()
    if not verified_user_id or dog_profile_db_adapter is None:
        return ()
    list_profiles = getattr(dog_profile_db_adapter, "list_profiles", None)
    if list_profiles is None:
        return ()
    try:
        profiles = list_profiles(requesting_user_id=verified_user_id)
    except Exception:
        return ()
    return tuple(profile for profile in profiles if profile.dog_id)


def _match_profiles_by_name(message: str, profiles: tuple[DogProfile, ...]) -> tuple[DogProfile, ...]:
    message_text = message.strip()
    if not message_text:
        return ()

    lowered_message = message_text.casefold()
    matches: list[DogProfile] = []
    for profile in profiles:
        candidate_name = str(profile.name).strip()
        if not candidate_name:
            continue
        lowered_name = candidate_name.casefold()
        if _contains_named_reference(lowered_message, lowered_name):
            matches.append(profile)

    if not matches:
        return ()

    matches.sort(key=lambda profile: len(str(profile.name).strip()), reverse=True)
    best_name = str(matches[0].name).strip().casefold()
    return tuple(
        profile
        for profile in matches
        if str(profile.name).strip().casefold() == best_name
    )


def _contains_named_reference(message: str, lowered_name: str) -> bool:
    if not lowered_name:
        return False
    if re.fullmatch(r"[a-z0-9][a-z0-9\s'-]*", lowered_name):
        boundary_pattern = re.compile(
            rf"(?<![^\W_]){re.escape(lowered_name)}(?![^\W_])",
            flags=re.UNICODE,
        )
        return boundary_pattern.search(message) is not None
    return lowered_name in message


def resolve_dog_selection(
    ctx: TurnContext,
    dog_profile_db_adapter: DogProfileDBAdapter | None,
) -> DogSelectionResolution:
    """Resolve the target dog for this turn, including name-based switching."""

    cached = ctx.dog_selection
    if isinstance(cached, DogSelectionResolution):
        return cached

    current_active_dog_id = resolve_active_dog_id(ctx.session, ctx.request_metadata)
    explicit_dog_id = _normalize_dog_id(ctx.request_metadata.get("dog_id"))
    available_profiles = list_known_dog_profiles(ctx.request_metadata, dog_profile_db_adapter)
    explicit_switch = is_explicit_dog_switch_request(ctx.message, ctx.locale)

    active_profile: DogProfile | None = None
    matched_by_name = False
    needs_disambiguation = False

    if explicit_dog_id is not None:
        active_dog_id = explicit_dog_id
        active_profile = next(
            (profile for profile in available_profiles if profile.dog_id == explicit_dog_id),
            None,
        )
    else:
        named_matches = _match_profiles_by_name(ctx.message, available_profiles)
        if len(named_matches) == 1:
            active_profile = named_matches[0]
            active_dog_id = active_profile.dog_id
            matched_by_name = True
        elif len(named_matches) > 1:
            active_dog_id = None
            needs_disambiguation = True
        elif current_active_dog_id is not None:
            active_dog_id = current_active_dog_id
            active_profile = next(
                (
                    profile
                    for profile in available_profiles
                    if profile.dog_id == current_active_dog_id
                ),
                None,
            )
        elif len(available_profiles) == 1:
            active_profile = available_profiles[0]
            active_dog_id = active_profile.dog_id
        else:
            active_dog_id = None

    if (
        active_dog_id is None
        and len(available_profiles) > 1
        and should_prompt_for_dog_selection(ctx.message, ctx.locale)
    ):
        needs_disambiguation = True

    resolution = DogSelectionResolution(
        active_dog_id=active_dog_id,
        current_active_dog_id=current_active_dog_id,
        active_profile=active_profile,
        available_profiles=available_profiles,
        matched_by_name=matched_by_name,
        explicit_switch=explicit_switch,
        needs_disambiguation=needs_disambiguation,
    )
    ctx.dog_selection = resolution
    return resolution


def resolve_active_dog_name(
    context: Any,
    request_metadata: dict[str, Any],
    dog_profile_db_adapter: DogProfileDBAdapter | None,
) -> str | None:
    """Resolve the current dog name from the profile store or recent turns."""

    active_dog_id = resolve_active_dog_id(context, request_metadata)
    if active_dog_id is None:
        return None

    verified_user_id = str(request_metadata.get("user_id", "")).strip()
    if dog_profile_db_adapter is not None and verified_user_id:
        try:
            profile = dog_profile_db_adapter.load_profile(
                active_dog_id,
                requesting_user_id=verified_user_id,
            )
        except Exception:
            profile = None
        if profile is not None:
            normalized_name = str(profile.name).strip()
            if normalized_name:
                return normalized_name

    recent_user_turns = context.turns[:-1] if hasattr(context, "turns") else ()
    for turn in reversed(recent_user_turns):
        if str(turn.get("role", "")).strip() != "user":
            continue
        detected_name = detect_dog_name(str(turn.get("message", "")))
        if detected_name is not None:
            return detected_name
        for profile in list_known_dog_profiles(request_metadata, dog_profile_db_adapter):
            normalized_name = str(profile.name).strip()
            if normalized_name and _contains_named_reference(
                str(turn.get("message", "")).casefold(),
                normalized_name.casefold(),
            ):
                return normalized_name
    return None


def has_tool(registry: SkillRegistry, tool_id: str) -> bool:
    """Return whether the tool id is currently registered."""

    return find_tool(registry, tool_id) is not None


def is_recall_turn(
    ctx: TurnContext,
    *,
    dog_profile_db_adapter: DogProfileDBAdapter | None,
) -> bool:
    """Return whether the current message should route to profile recall."""

    selection = resolve_dog_selection(ctx, dog_profile_db_adapter)
    if selection.active_dog_id is None:
        return False

    dog_name = None
    if selection.active_profile is not None:
        normalized_name = str(selection.active_profile.name).strip()
        dog_name = normalized_name or None
    else:
        dog_name = resolve_active_dog_name(
            ctx.session,
            ctx.request_metadata,
            dog_profile_db_adapter,
        )
    return is_dog_profile_recall_query(ctx.message, dog_name=dog_name)


def find_result(
    ctx: TurnContext,
    skill_id: str,
    outcome: str | None = None,
) -> SkillExecutionResult | None:
    """Return the first matching skill result for the given route id."""

    for result in ctx.skill_results:
        if result.skill_id != skill_id:
            continue
        if outcome is not None and result.outcome != outcome:
            continue
        return result
    return None
