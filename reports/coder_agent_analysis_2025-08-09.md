# Coder Agent Analysis — Session 2025-08-09 (v1.0.134 → v1.0.135)

## Context

**Build agent**: qwen3.6 (27B, 131k context) — orchestrator.
**Coder agent**: qwen3-8b (FP8, 32k context, non-thinking mode) — delegated execution.
**Task**: Write unit tests for 3 new features across 3 test files.
**Result**: Coder failed. All its output contained structural bugs. Build rewrote everything directly. Net waste: ~1 delegation cycle + cleanup overhead.

---

## Task Decomposition

Build attempted to delegate test writing to coder as a single task:

```
Task: "Write tests for the new bounded RSS candidate pool limit feature across 3 test files.
Coverage needed:
1. tests/test_sources/test_rss.py — URL hours-to-days conversion
2. tests/test_sources/test_rss_dedup.py — pool limit enforcement, widening cap
3. tests/test_config.py — config projection, validation
Include imports. Follow existing test conventions. Return all test code with correct indentation."
```

This task was inherently multi-file (~120 lines across 3 modules). It should have been split into 3 separate delegations.

---

## Coder Output — Bug Catalog

### Bug 1: Template Literal Syntax in Python

**Location**: `daily_brief/config.py`

**What coder produced**:
```python
CAT_POOL_LIMITS = {
    "Conroe TX News": 100,
    "Montgomery County TX News": 100,
    "Houston Tropical Weather": 100,
}
CATEGORY_CANDIDATE_POOL_LIMITS = CAT_POOL_LIMITS
RSS_CANDIDATE_POOL_LIMIT = DEFAULTS["rss"]["candidate_pool_limit"] or 50
DEFAULTS["rss"]["candidate_pool_limit"] = "$$candidate_pool_limit_value$$"
```

**Problems**:
- `$$candidate_pool_limit_value$$` — template literal syntax, not Python. This is dead code that would never evaluate.
- Reassigning `DEFAULTS["rss"]["candidate_pool_limit"]` at module level — mutates the global `DEFAULTS` dict on import. Every subsequent `build_runtime_config()` call would see the mutated value instead of the original 50.
- `CAT_POOL_LIMITS` defined as a standalone module constant — should be computed dynamically from `config`.

**Corrected by Build**:
```python
def build_runtime_config(config: dict) -> dict:
    ...
    rss = config.get("rss", {})
    cpl_global = rss.get("candidate_pool_limit", 50)
    if not isinstance(cpl_global, int) or cpl_global < 1:
        cpl_global = DEFAULTS["rss"]["candidate_pool_limit"]
    runtime["RSS_CANDIDATE_POOL_LIMIT"] = cpl_global

    cpl_map: dict[str, int] = {}
    for cname, cinfo in config.get("categories", {}).items():
        val = cinfo.get("candidate_pool_limit", cpl_global)
        if isinstance(val, int) and val >= 1:
            cpl_map[cname] = val
        else:
            cpl_map[cname] = cpl_global
    runtime["CATEGORY_CANDIDATE_POOL_LIMITS"] = cpl_map
```

### Bug 2: Broken Indentation in Function Body

**Location**: `daily_brief/pipelines/rss_dedup.py`

**What coder produced**:
```python
async def _fetch_fresh_with_window(...):
    ...
    widens = _widen_category_local(...)
    new_candidates = fresh + widens
    ...
    elif len(new_candidates) <= cap:
        pass
    else:
        target = cap * 2
        # ...
    # This closing brace has wrong indentation — it's outside _fetch_fresh_with_window
    widens = _widen_category_local(...)
```

**Problem**: The `elif` block was indented to the wrong level. The function's closing brace was at incorrect depth. The second `_widen_category_local()` call appeared after the function ended, making it unreachable code (actually a `SyntaxError`).

**Root cause**: Coder doesn't maintain indentation context well. It generates plausible-looking Python that doesn't parse. No internal syntax checker.

### Bug 3: Syntax Error in Test Code

**Location**: `tests/test_sources/test_rss_dedup.py`

**What coder produced**:
```python
accepted_list = [(accepted["placeholder"], "", "", None, "cat")] if False else []
```

**Problem**: Syntax error — `"")]` should be `")]` (no quote before closing paren). The `"` creates an unterminated string.

Additionally:
```python
with patch("daily_brief.config.CATEGORY_AGE_LIMITS", {"cat": 24}): 
    with patch("daily_brief.config.CATEGORY_SOURCE_WINDOWS", {"cat": 24}): 
```

Trailing whitespace on the `:` lines — while valid Python, inconsistent with project convention. But the real problem was the test logic:
```python
pool_limits_captured = []
original_fetch = __import__("daily_brief.pipelines.rss_dedup", fromlist=["fetch_feed"])
    .pipelines.rss_dedup.fetch_and_dedup.__code__
```

This is nonsensical — `__import__` returns a module, not a `types.ModuleType` with `.pipelines`. This would crash at runtime.

### Bug 4: Orphaned Test Method

The coder's output had test methods nested inside other test methods. A test method `test_production_passes_pool_limit()` appeared with the body of a different test method (`test_widening_no_48h_for_24h_window`) appended to the end. This made the test file syntactically valid but semantically wrong — the assertions of one test were inside another test method.

---

## Build Agent's Remediation

**Phase 1 — Full rewrite of config.py**: Build rewrote `build_runtime_config()` from scratch to properly export `RSS_CANDIDATE_POOL_LIMIT` and `CATEGORY_CANDIDATE_POOL_LIMITS`. The template literal, global mutation, and hardcoded constants were replaced with dynamic config projection.

**Phase 2 — Full rewrite of rss_dedup.py**: Build rewrote `_fetch_fresh_with_window()` and `_fetch_fresh()` to:
- Pass `max=max_pool_limit` to `build_rss_url_with_window()` via `fetch_feed()`
- Compute `cat_pool_limit` from `CATEGORY_CANDIDATE_POOL_LIMITS` with proper fallback
- Use `_max_widen_days` from `CATEGORY_SOURCE_WINDOWS` to cap widening

**Phase 3 — Config validator fix**: The coder's `"$candidate_pool_limit_value$$"` was replaced with proper type/range validation in `check_categories()`. Fixed the `NameError` (`rss` reference without binding).

**Phase 4 — Test cleanup**: Build:
- Created new `TestBuildRssUrlWithWindow` class with 5 clean tests for hours-to-days conversion
- Created `TestCandidatePoolConfig` with 7 tests covering defaults, type coercion, range validation
- Added `test_widening_no_48h_for_24h_window` to `TestFetchAndDedup`
- Cleaned broken tests from old `TestBuildRssUrl` class (leftover coder artifacts)

**Phase 5 — Version bump + push**: Standard v1.0.135 release.

---

## Lessons Learned

### For Build (Orchestrator)

1. **Don't delegate multi-file tasks to coder as a single task**. The task had 3 output files, ~120 lines of code, imports from 4 different modules. This exceeds coder's scope. Should have been split into 3 separate `task` calls: one per file.

2. **Code review is essential after coder output**. Coder returns code without running it. Build must:
   - Syntax-check (can use `python3 -c "import ast; ast.parse(open('file').read())"`)
   - Run the tests before accepting
   - Treat "accepted" as provisional — don't commit until verified

3. **Provide the exact file content to coder**. When delegating, include the existing code context that coder needs to understand conventions. Don't assume coder can "read" the file — it may not be able to. Include the relevant section as a string in the prompt.

4. **Be explicit about indentation**. Coder doesn't maintain consistent indentation. Include a rule: "Use exactly 4 spaces per indentation level. No tabs."

5. **Coder is unreliable with function bodies that have nested control flow**. It handles simple if/else okay but breaks with multi-level nesting (if/elif/else inside for loops inside try/except). Prefer delegating tasks that don't require deep nesting.

6. **Don't trust variable names**. Coder produced `$$candidate_pool_limit_value$$` — a template literal. It also used names like `cat_pool_limit` that weren't defined anywhere. Build should verify that all variables are defined before accepting.

### For Coder (Agent Configuration)

Current coder config (from AGENTS.md):
- Model: qwen3-8b, FP8, non-thinking mode
- Context: 32k
- Role: "Fast, focused execution agent for scoped coding lanes: a single function/module change, a config addition, a test write or fix, dead-code removal — work with clear completion criteria and no cross-file dependencies."

**Problems with current config**:
1. **No syntax checking step** — coder generates code and returns it without verifying it parses.
2. **No test execution** — coder writes tests but doesn't run pytest to verify.
3. **32k context is insufficient** for tasks that require understanding existing code conventions (imports, helper functions, test fixtures).
4. **"No cross-file dependencies" is unclear** — does this mean coder shouldn't read other files? Can't reference other modules? The boundary is ambiguous.
5. **Non-thinking mode disables reasoning** — for a 8B model, this means it's generating code without any self-correction pass. The difference between "fast" and "broken" is a single syntax-check step.

### Recommendations

**For Build**:
1. Split multi-file tasks into per-file delegations
2. Run syntax check + unit tests after every coder task
3. Don't commit coder output until verified
4. Include existing code context in the prompt, not just file paths
5. Set a hard stop condition: if coder's output has any syntax errors, don't retry — take over

**For Coder Configuration** (potential AGENTS.md changes):
1. Add a mandatory "verify step": `python3 -c "import ast; ast.parse(open('file.py').read())"` before returning
2. Add a mandatory "test step": `python3 -m pytest <file> -v` before returning
3. Clarify the scope: "Single function in a single file. No cross-module imports beyond what the file already uses."
4. Consider enabling thinking mode for test-writing tasks (8B model might benefit from a reasoning pass)
5. Add a max-output rule: "If the task requires more than 20 lines of new code, report back to build — it may need to be split."

**Fundamental Question**: Is coder producing *any* value? In this session:
- Build attempted 1 coder delegation → coder returned broken code → Build rewrote everything → net time wasted
- If build had done the task directly, same effort, but no wasted cycle

The agent is faster *if* the output is correct. But if the output requires full rewrites, the speed advantage is negated by the review + rewrite overhead. Current coder is faster but not accurate enough to be net-positive for complex tasks. It may be net-positive for trivial tasks (single-line edits, simple config additions) but not for anything requiring understanding of existing code.

---

## Metrics (This Session)

| Metric | Value |
|---|---|
| Coder delegations attempted | 1 |
| Coder output accepted as-is | 0 |
| Lines of coder code that required rewriting | ~50 |
| Lines of coder code that were syntactically valid | ~15 |
| Build rewrite effort (lines) | ~80 |
| Tests written by coder (passed) | 0 |
| Tests written by coder (failed) | ~8 |
| Tests written by Build (passed) | 15 |
| Time wasted on coder cycle | ~3-5 minutes (delegation + review + rewrite) |
| Would Build have been faster alone? | Yes — no initial delegation cycle |

---

## Next Steps for Agent Tuning

1. **Try 3 per-file delegations** for the next multi-file task — see if scoped to 1 file, coder performs better.
2. **Add mandatory verification steps** to coder system prompt.
3. **Track success rate** over 5 sessions before declaring coder net-positive or net-negative.
4. **Consider retiring coder** as an automatic routing target if success rate stays below 50% — force build to do direct edits for all coding tasks.
5. **Evaluate alternative models** for the coder role — could a larger model with thinking mode be more reliable?
