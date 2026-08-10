# Coder Agent Analysis — Session 2025-08-09 (v1.0.134 → v1.0.135)

## Context

**Build agent**: qwen3.6 (27B, 131k context) — orchestrator.
**Coder agent**: qwen3-8b (FP8, 32k context, non-thinking mode) — delegated execution.
**Task**: Write unit tests for 3 new features across 3 test files.
**Result**: The delegated output required correction and Build rewrote it. The primary preventable failure was Build orchestration: it dispatched a multi-file, cross-module task to an agent explicitly intended for a scoped, single-file lane, then did not promptly run a syntax check and focused test command before continuing.

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

This task was inherently multi-file (~120 lines across 3 modules), depended on different fixtures and imports in each file, and was not an appropriate Coder lane. This is a Build assignment and management failure, not evidence that Coder is incapable of understanding the relevant conventions.

The correct decomposition was three independent, self-contained assignments:

1. `tests/test_sources/test_rss.py`: add only URL hours-to-days cases to the named test class.
2. `tests/test_sources/test_rss_dedup.py`: add only the source-window widening-cap case, reusing the existing helpers named in the prompt.
3. `tests/test_config.py`: add only global/per-category candidate-pool configuration and validation cases.

Each assignment should have stated the precise insertion point, provided the immediately surrounding source, limited the expected diff, and required an exact test command before return.

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

**Evidence-based conclusion**: The returned edit had invalid structure and had not been syntax-checked. It is not possible to attribute that solely to model capability from one oversized task. The operational failure is that Build accepted the return path without requiring and independently confirming syntax/test verification.

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

### Responsibility Matrix

| Observation | Primary owner | Why |
|---|---|---|
| One task covered three files with separate fixtures and conventions | Build | Coder's documented lane is a scoped, single-file change. Build chose the task boundary. |
| The prompt required Coder to reason across source and test modules | Build | Build should have decomposed production and test work, or supplied the minimal local context for one file. |
| Returned edit contained structural defects | Shared, with Build owning containment | Coder produced the edit, but Build owns validation and must prevent an unverified edit from contaminating the active worktree. |
| Syntax and focused tests were not run immediately after the lane returned | Build | Verification is an orchestration responsibility even if Coder is also asked to run it. |
| No demonstrated evidence that 32k context caused the failure | Build analysis | The prior report inferred a model limitation without a controlled, correctly scoped comparison. |

### For Build (Orchestrator)

1. **Don't delegate multi-file tasks to coder as a single task**. The task had 3 output files, ~120 lines of code, imports from 4 different modules. This exceeds coder's scope. Should have been split into 3 separate `task` calls: one per file.

2. **Code review is essential after coder output**. Coder returns code without running it. Build must:
   - Syntax-check (can use `python3 -c "import ast; ast.parse(open('file').read())"`)
   - Run the tests before accepting
   - Treat "accepted" as provisional — don't commit until verified

3. **Provide the exact local context needed for the one-file lane**. A 32k context limit is not itself an issue for a small, properly scoped change. Build must send the target function/class, relevant imports and fixtures, exact insertion point, and acceptance tests. The prompt should not require Coder to reconstruct conventions across several files.

4. **Specify formatting and verify it**. State "Use exactly 4 spaces per indentation level. No tabs" for Python edits, then immediately run syntax and focused tests. One failed oversized task is not enough evidence to declare a general Coder indentation limitation.

5. **Assign Coder only atomic edit units**. Do not infer a general inability to write nested control flow from this incident. Instead, keep its assignment to one named function, test class, or declarative configuration block and verify its output immediately.

6. **Don't trust variable names**. Coder produced `$$candidate_pool_limit_value$$` — a template literal. It also used names like `cat_pool_limit` that weren't defined anywhere. Build should verify that all variables are defined before accepting.

### For Coder (Agent Configuration)

Current coder config (from AGENTS.md):
- Model: qwen3-8b, FP8, non-thinking mode
- Context: 32k
- Role: "Fast, focused execution agent for scoped coding lanes: a single function/module change, a config addition, a test write or fix, dead-code removal — work with clear completion criteria and no cross-file dependencies."

**Problems with current config**:
1. **No syntax checking step** — coder generates code and returns it without verifying it parses.
2. **No test execution** — coder writes tests but doesn't run pytest to verify.
3. **32k context is a hard boundary, not a demonstrated root cause here**. It is ample for a small, self-contained file edit when Build provides the local context. It becomes a risk only when Build sends a multi-file task or expects Coder to discover many independent conventions.
4. **"No cross-file dependencies" is unclear** — does this mean coder shouldn't read other files? Can't reference other modules? The boundary is ambiguous.
5. **Non-thinking mode disables reasoning** — for a 8B model, this means it's generating code without any self-correction pass. The difference between "fast" and "broken" is a single syntax-check step.

### Recommendations

**For Build**:
1. Treat Coder as a scoped execution worker, not a mini-orchestrator: one file, one cohesive change, one test command.
2. Split independent file changes into parallel per-file delegations only after confirming that the files do not overlap.
3. Provide the local source context, exact insertion/replacement location, expected symbols, and acceptance criteria in every task prompt.
4. Require Coder to run a syntax check and the focused test command; Build independently repeats the focused test before integrating other work.
5. Do not commit coder output until verified.
6. On a failed syntax check or focused test, stop the lane, inspect the diff, and either issue one narrowly defined repair task or take over. Do not layer another broad request on a broken working tree.

**For Coder Configuration** (potential AGENTS.md changes):
1. Add a mandatory "verify step": `python3 -c "import ast; ast.parse(open('file.py').read())"` before returning
2. Add a mandatory "test step": `python3 -m pytest <file> -v` before returning
3. Clarify the scope: "One file only; one named function, class, or configuration block; do not modify adjacent files; stop and report if required context is absent."
4. Require Coder to report the exact files changed, the test command run, and its result, rather than only describing the intended change.
5. Add a dispatch guard for Build: if a request names more than one file or requires changing production code and tests together, Build must decompose it before delegation.
6. Evaluate thinking mode only after applying the above workflow controls. Model configuration may help, but it is not the first corrective action because the task violated the documented lane contract.

**Fundamental Question**: Is Coder producing value? This session does not answer that fairly because Build gave it a task outside its stated lane. The evidence shows that this particular dispatch was net-negative. It does not establish that Coder is net-negative for correctly scoped single-file work.

The next evaluation must compare like-for-like work: a few independently scoped, one-file changes with local context and mandatory verification. Measure success rate, review/rework time, and end-to-end elapsed time against Build doing the same task directly.

---

## Metrics (This Session)

| Metric | Value |
|---|---|
| Coder delegations attempted | 1, but outside the documented single-file lane |
| Coder output accepted as-is | 0 |
| Lines of coder code that required rewriting | Approximately 50 |
| Lines of coder code that were syntactically valid | Approximately 15; estimate, not a measured metric |
| Build rewrite effort (lines) | Approximately 80 |
| Tests written by coder (passed) | 0 accepted from this lane |
| Tests written by Build (passed) | 15 |
| Time lost in this dispatch | Approximately 3-5 minutes; estimate |
| Primary owner of the failed dispatch | Build orchestration |

---

## Next Steps for Agent Tuning

1. **Run a controlled trial**: choose 5 atomic, independent, one-file edits. Give each Coder the needed local source context and one focused test command.
2. **Use a Build dispatch checklist** before every Coder task: one file, no conflicting parallel writers, clear insertion/replacement point, acceptance test, and maximum expected diff.
3. **Make verification mandatory**: Coder syntax-checks and runs the focused test; Build independently repeats the focused test before integration.
4. **Track success rate and rework cost** over the controlled trial before changing models or disabling Coder.
5. **Only then evaluate model configuration**: if correctly scoped tasks still fail materially, test thinking mode or a different execution model.
