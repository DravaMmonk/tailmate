# Contributing to Tailmate

Tailmate is at pre-1.0. Issues and pull requests are welcome,
especially around the agent runtime, the design system, or the dog-profile
extraction strategies. Larger changes should start with an issue first so we
can sketch the approach before code lands.

## Working language

All code, comments, commit messages, and GitHub content are in English.

Exception: localized user-facing strings, multilingual extraction dictionaries,
and language-specific test fixtures may include non-English text when they
exist to validate or ship localization behavior.

## Branching

Create short-lived branches from `main`:

- `feature/<topic>`
- `fix/<topic>`
- `docs/<topic>`
- `chore/<topic>`

Don't push directly to `main`. Use Draft PRs for multi-day or risky work.
`Squash and merge` by default.

## Versioning

Pre-1.0 semantic versioning (`0.MINOR.PATCH`):

- `0.MINOR.0` — a new feature slice or meaningful developer-workflow capability
- `0.MINOR.PATCH` — bug fixes, reliability work, non-breaking docs/operational updates
- pre-release tags like `v0.5.1-rc.1` for staged candidates

Call out any breaking pre-1.0 behavior explicitly in the PR and `CHANGELOG.md`.

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat: add vertex smoke test ui`
- `fix: stop exporting gemini api key in cloud mode`
- `docs: rewrite version control policy for pre-1.0`
- `chore: sync agent engine requirements`

## Pull requests

Before requesting review:

- update the relevant `docs/*.md` spec when architecture, workflow, deployment,
  or testing contracts change
- update `CHANGELOG.md` when the change affects versioned behavior
- explain any breaking pre-1.0 behavior explicitly

CI runs Ruff, scoped mypy, Bandit, pip-audit against locked deps, unit tests
with coverage, and contract tests.

## Local validation

Minimum local checks before opening a merge-ready PR:

```bash
uv run python -m compileall src
uv run mypy
uv run bandit -c pyproject.toml -r src
uv run python -m pytest tests/unit
```

Add integration or contract tests when the change affects persistence, runtime
wiring, deployment contracts, or exposed schemas.
