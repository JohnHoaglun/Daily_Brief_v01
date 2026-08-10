# Version Locations

## Canonical Version

**Current release: `v1.0.135`**

## Required Release Process

Before every commit, read this file and update every location in the registry
to the current release version. When a new tracked file contains a current
release-version reference, add it to this registry in the same change.

Historical changelog entries are records of their original releases and must
not be rewritten during later version bumps.

## Current-Version Registry

| File | Location | Format |
|---|---|---|
| `README.md` | Title | `# Daily Brief vX.Y.Z` |
| `README.md` | Configuration table | `X.Y.Z` |
| `PROJECT.md` | Title | `vX.Y.Z` |
| `TODOS.md` | Title and status | `vX.Y.Z` |
| `config.yaml` | `version` key | `X.Y.Z` |
| `daily_brief/__init__.py` | Package docstring and `__version__` | `vX.Y.Z` and `X.Y.Z` |
| `daily_brief/config.py` | `DEFAULTS["version"]` | `X.Y.Z` |
| `daily_brief/__main__.py` | Module docstring | `vX.Y.Z` |
| `dashboard_pipeline.py` | Launcher docstring | `vX.Y.Z` |
| `daily_brief/capture_corpus.py` | Module docstring | `vX.Y.Z` |
| `daily_brief/harness.py` | Module docstring | `vX.Y.Z` |
| `daily_brief/http_client.py` | Module docstring | `vX.Y.Z` |
| `daily_brief/models.py` | Module docstring | `vX.Y.Z` |
| `daily_brief/utils.py` | Module docstring | `vX.Y.Z` |
| `daily_brief/validation.py` | Module docstring | `vX.Y.Z` |
| `daily_brief/llm/__init__.py` | Module docstring | `vX.Y.Z` |
| `daily_brief/llm/client.py` | Module docstring | `vX.Y.Z` |
| `daily_brief/sources/__init__.py` | Module docstring | `vX.Y.Z` |
| `daily_brief/sources/article.py` | Module docstring | `vX.Y.Z` |
| `daily_brief/sources/climate.py` | Module docstring | `vX.Y.Z` |
| `daily_brief/sources/weather.py` | Module docstring | `vX.Y.Z` |
| `daily_brief/sources/wunderground.py` | Module docstring | `vX.Y.Z` |
| `daily_brief/lifecycle.py` | Module docstring | `vX.Y.Z` |
| `PLAN.md` | Title and status | `vX.Y.Z` |
| `SUMMARY.md` | Latest changelog entry | `vX.Y.Z` |
| `versions_locations.md` | Canonical Version | `vX.Y.Z` |
