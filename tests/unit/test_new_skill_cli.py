from __future__ import annotations

from pathlib import Path

import pytest

from tailmate.entrypoints import cli as tailmate_cli
from tailmate.entrypoints.new_skill import create_new_skill_scaffold


def test_create_new_skill_scaffold_generates_standard_files(tmp_path: Path) -> None:
    repo_root = tmp_path
    (repo_root / "pyproject.toml").write_text("[project]\nname='tailmate-app'\n", encoding="utf-8")
    (repo_root / "src" / "tailmate").mkdir(parents=True)

    created = create_new_skill_scaffold("coat_analysis", cwd=repo_root)

    created_paths = {path.relative_to(repo_root).as_posix() for path in created}
    assert created_paths == {
        "docs/coat_analysis-slice.md",
        "src/tailmate/adapters/coat_analysis/__init__.py",
        "src/tailmate/adapters/coat_analysis/stub.py",
        "src/tailmate/contracts/coat_analysis.py",
        "src/tailmate/skills/coat_analysis/__init__.py",
        "src/tailmate/skills/coat_analysis/manifest.py",
        "src/tailmate/skills/coat_analysis/skill.py",
        "tests/contract/test_coat_analysis_registration.py",
        "tests/integration/test_coat_analysis_orchestration.py",
        "tests/unit/test_coat_analysis_skill.py",
    }

    manifest_text = (
        repo_root / "src" / "tailmate" / "skills" / "coat_analysis" / "manifest.py"
    ).read_text(encoding="utf-8")
    skill_text = (
        repo_root / "src" / "tailmate" / "skills" / "coat_analysis" / "skill.py"
    ).read_text(encoding="utf-8")
    unit_test_text = (
        repo_root / "tests" / "unit" / "test_coat_analysis_skill.py"
    ).read_text(encoding="utf-8")
    assert 'skill_id="coat_analysis"' in manifest_text
    assert "default_enabled=False" in manifest_text
    assert 'adapter_dependencies=("coat_analysis_adapter",)' in manifest_text
    assert "return build_coat_analysis_skill(adapter=adapter)" in manifest_text
    assert "request = normalize_coat_analysis_request(payload)" in skill_text
    assert "return self.adapter.run(request)" in skill_text
    assert "class FakeCoatAnalysisAdapter" in unit_test_text
    assert "test_coat_analysis_tool_invokes_adapter_with_normalized_payload" in unit_test_text
    assert 'assert payload == {"status": "ok"}' in unit_test_text


def test_create_new_skill_scaffold_rejects_invalid_names(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='tailmate-app'\n", encoding="utf-8")
    (tmp_path / "src" / "tailmate").mkdir(parents=True)

    with pytest.raises(ValueError, match="snake_case"):
        create_new_skill_scaffold("CoatAnalysis", cwd=tmp_path)


def test_new_skill_cli_prints_next_steps_checklist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='tailmate-app'\n", encoding="utf-8")
    (tmp_path / "src" / "tailmate").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    exit_code = tailmate_cli.main(["new-skill", "coat_analysis"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "tests/unit/test_coat_analysis_skill.py" in captured.out
    assert "Next steps for coat_analysis:" in captured.out
    assert "Define the intent string in src/tailmate/agent_runtime/intent_classifier/intents.py" in captured.out
    assert "Register the adapter dependency in the container and manifest" in captured.out
