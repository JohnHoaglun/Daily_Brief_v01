# PLAN: v1.0.139 — HTML Parsing Offload ✅ COMPLETE

## Status: COMPLETED — implementation done, 574/574 tests passing.

## Objective
Offload CPU-bound HTML parsing to a worker thread so BeautifulSoup work does not block the event loop during concurrent extraction.

## Scope
- [x] Extract synchronous parse/clean logic into `_parse_article_html(html) -> str`.
- [x] Dispatch via `asyncio.to_thread(_parse_article_html, html)`.
- [x] Keep HTTP fetch, retries, semaphore ownership, error handling, and `story.context` assignment on the event loop.
- [x] 5 new offload tests: parity, dispatch verification, error containment, event-loop responsiveness, concurrency cap preservation.

## Verification
- [x] 574/574 full suite passing, 0 regressions.
- [x] Config validation: PASS.

## Non-Goals
- Do not change the RSS candidate pool or its widening behavior.
- Do not alter extraction concurrency limits or HTTP bounds.
