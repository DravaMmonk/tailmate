from __future__ import annotations

import importlib
import json

from tailmate.agent_runtime.services import safety_boundaries


def test_classify_safety_boundary_matches_existing_english_categories() -> None:
    assert safety_boundaries.classify_safety_boundary(
        "How much ibuprofen can I give my dog?"
    ) == safety_boundaries.SafetyBoundaryDecision(
        hit=True,
        category="medication_dose",
    )
    assert safety_boundaries.classify_safety_boundary(
        "My dog collapsed and is not breathing."
    ) == safety_boundaries.SafetyBoundaryDecision(
        hit=True,
        category="emergency_triage",
    )
    assert safety_boundaries.classify_safety_boundary(
        "Could this be cancer?"
    ) == safety_boundaries.SafetyBoundaryDecision(
        hit=True,
        category="diagnosis",
    )


def test_classify_safety_boundary_matches_existing_non_english_terms() -> None:
    assert safety_boundaries.classify_safety_boundary("我的狗中毒了") == (
        safety_boundaries.SafetyBoundaryDecision(hit=True, category="emergency_triage")
    )
    assert safety_boundaries.classify_safety_boundary("هل هذا يحتاج وصفة؟") == (
        safety_boundaries.SafetyBoundaryDecision(
            hit=True,
            category="prescription_authorisation",
        )
    )


def test_classify_safety_boundary_returns_false_for_safe_message() -> None:
    assert safety_boundaries.classify_safety_boundary("Hello there") == (
        safety_boundaries.SafetyBoundaryDecision(hit=False)
    )


def test_safety_boundaries_config_path_can_be_overridden(tmp_path, monkeypatch) -> None:
    custom_config = {
        "categories": [
            {
                "id": "custom_boundary",
                "patterns_en": ["\\bcustom trigger\\b"],
                "terms_by_locale": {"en": ["custom term"]}
            }
        ]
    }
    config_path = tmp_path / "custom_safety_boundaries.json"
    config_path.write_text(json.dumps(custom_config), encoding="utf-8")
    monkeypatch.setenv("SAFETY_BOUNDARIES_CONFIG_PATH", str(config_path))

    reloaded = importlib.reload(safety_boundaries)
    try:
        assert reloaded.classify_safety_boundary("custom trigger") == (
            reloaded.SafetyBoundaryDecision(hit=True, category="custom_boundary")
        )
        assert reloaded.classify_safety_boundary("custom term") == (
            reloaded.SafetyBoundaryDecision(hit=True, category="custom_boundary")
        )
    finally:
        monkeypatch.delenv("SAFETY_BOUNDARIES_CONFIG_PATH", raising=False)
        importlib.reload(reloaded)
