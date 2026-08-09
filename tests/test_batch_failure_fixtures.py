"""
Test fixtures for deterministic mocked LLM failure paths in batch_summarize_all.
All tests use mocked LLM responses — no live LLM calls.
Used by C.4 failure-path tests and any new tests that need batch failure scenarios.
"""
import asyncio
import time
from unittest import TestCase, mock
from unittest.mock import AsyncMock, MagicMock, patch

from daily_brief.llm.summarizer import (
    StoryPipelineState,
    _safe_sentence_summary,
    _is_valid_summary,
    _is_boilerplate,
    _generate_auto_fallback,
    batch_summarize_all,
)


# ---------------------------------------------------------------------------
# Helper factory
# ---------------------------------------------------------------------------

def _make_story(title, category, snip="Snippet for testing.", context="Article content that is long enough for proper context generation during LLM summary processing."):
    s = StoryPipelineState(title=title, link="http://x", snippet=snip, pub_dt="2024-01-01", category=category)
    s.context = context
    s.summary = None
    return s


def _run(async_fn):
    """Run an async function in the event loop."""
    return asyncio.get_event_loop().run_until_complete(async_fn)


def _retry_patches():
    """Return context managers that disable LLM retry and sleep delays."""
    return (
        patch("daily_brief.config.LLM_SUMMARY_RETRY_ATTEMPTS", 1),
        patch("daily_brief.config.LLM_SUMMARY_RETRY_BACKOFF", []),
        patch("asyncio.sleep", new_callable=AsyncMock, return_value=None),
    )


def _is_batch_call(msgs):
    """Detect whether an LLM call is a batch call by checking for STORY_0 in system prompt."""
    if not msgs:
        return False
    system = msgs[0].get("content", "") if isinstance(msgs[0], dict) else ""
    return "STORY_0" in system


def _make_mock_response(content):
    """Create a mock LLM response object with the given content string."""
    r = MagicMock()
    r.choices = [MagicMock(message=MagicMock(content=content))]
    return r


def _valid_summary_text(topic):
    """Generate 2+ sentence valid summary that won't be flagged as boilerplate."""
    return (
        f"The {topic} event unfolded today with significant consequences for stakeholders. "
        f"Analysts reported measurable changes in the relevant sector overnight."
    )


# ---------------------------------------------------------------------------
# 1. TestTransientBatchException
# ---------------------------------------------------------------------------

class TestTransientBatchException(TestCase):
    """Batch call raises exception; recovery via _summarize succeeds or also fails."""

    def test_first_batch_fails_recovery_succeeds(self):
        """Batch calls raise Exception; single-story recovery returns valid summaries.
        Verify: batch calls made, all stories get valid summaries (not [Auto])."""
        stories = [
            _make_story("Alpha Market Rally Stocks Surging", "Finance"),
            _make_story("Beta Climate Warming Report Released", "Finance"),
        ]

        batch_calls = [0]
        single_calls = [0]

        async def side_effect(**kwargs):
            msgs = kwargs.get("messages", [])
            if _is_batch_call(msgs):
                batch_calls[0] += 1
                raise Exception("Connection refused")
            else:
                single_calls[0] += 1
                title_hint = "market rally"  # keyword overlap with both story headlines
                return _make_mock_response(
                    f"Recovery summary with concrete facts about the {title_hint} story. "
                    "Analysts reported measurable gains across the sector today."
                )

        # Also patch _summarize to use the same side_effect for its internal LLM call
        async def mock_summarize(client, ctx, title=None, **skwargs):
            single_calls[0] += 1
            return (f"Recovery summary with concrete facts about the {title} story. "
                    "Analysts reported measurable gains across the sector today.")

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, side_effect=mock_summarize):
                    await batch_summarize_all(client, stories, batch_size=2)

        _run(run())
        self.assertEqual(batch_calls[0], 2, "Expected 2 batch calls (initial + retry)")
        self.assertEqual(single_calls[0], 2, "Expected 2 single recovery calls")
        for s in stories:
            self.assertNotIn("[Auto]", s.summary, f"Story {s.title} should not be [Auto], got: {s.summary}")

    def test_batch_fails_recovery_also_fails(self):
        """Batch raises exception; single-story recovery also fails (returns None).
        Verify: stories fall back to [Auto] headline summary."""
        stories = [
            _make_story("Gamma Tech IPO Launch Today", "Tech"),
            _make_story("Delta Housing Market Crash Report", "Tech"),
        ]

        batch_calls = [0]

        async def side_effect(**kwargs):
            msgs = kwargs.get("messages", [])
            if _is_batch_call(msgs):
                batch_calls[0] += 1
            raise Exception("Connection refused")

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, return_value=None):
                    await batch_summarize_all(client, stories, batch_size=2)

        _run(run())
        self.assertEqual(batch_calls[0], 2, "Expected 2 batch calls (initial + retry)")
        for s in stories:
            self.assertTrue(s.summary.startswith("[Auto]"), f"Expected [Auto] for {s.title}, got: {s.summary}")


# ---------------------------------------------------------------------------
# 2. TestMalformedBatchResponse
# ---------------------------------------------------------------------------

class TestMalformedBatchResponse(TestCase):
    """Batch response is garbled or partial; recovery path exercised."""

    def test_completely_garbled_response(self):
        """Batch response has no STORY_N or numbered format.
        Verify: parse returns empty strings, stories enter recovery, get [Auto] when recovery fails."""
        stories = [
            _make_story("Epsilon News Item One Breaking", "News"),
            _make_story("Zeta News Item Two Analysis", "News"),
        ]

        garbled = "xhdfjkslhdkjfsldkfj random noise no structure at all blah blah gibberish"

        async def side_effect(**kwargs):
            return _make_mock_response(garbled)

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, return_value=None):
                    await batch_summarize_all(client, stories, batch_size=2)

        _run(run())
        for s in stories:
            self.assertTrue(s.summary.startswith("[Auto]"), f"Expected [Auto] for {s.title}, got: {s.summary}")

    def test_partial_valid_response(self):
        """Batch response has valid data for only 2 of 4 stories.
        Verify: 2 stories have valid summaries, 2 enter recovery path."""
        stories = [
            _make_story("Iota Finance Stock Market Rally Today", "Finance"),
            _make_story("Kappa Finance Bond Yield Increase Rate", "Finance"),
            _make_story("Lambda Climate Temperature Report Rising", "Finance"),
            _make_story("Mu Climate Ocean Acidification Study", "Finance"),
        ]

        # Only stories 0 and 1 get valid summaries; 2 and 3 are missing
        partial_resp = (
            "STORY_0 | Iota Finance Stock Market Rally=The stock market rally accelerated today with strong gains across sectors. "
            "Investors poured billions into index funds during afternoon trading.\n"
            "STORY_1 | Kappa Finance Bond Yield Increase=Bond yields increased sharply on the treasury auction results this morning. "
            "The yield curve inverted for the second consecutive week of trading."
        )

        async def mock_summarize(client, context, title=None, **kwargs):
            if "Lambda" in title or "Mu" in title:
                return None  # Recovery fails for stories 2,3
            return _valid_summary_text(title or "unknown")

        async def side_effect(**kwargs):
            return _make_mock_response(partial_resp)

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, side_effect=mock_summarize):
                    await batch_summarize_all(client, stories, batch_size=4)

        _run(run())
        # Stories 0 and 1: validated by parse, should have summaries
        self.assertNotIn("[Auto]", stories[0].summary)
        self.assertNotIn("[Auto]", stories[1].summary)
        # Stories 2 and 3: empty from batch parse → recovery returns None → [Auto]
        self.assertTrue(stories[2].summary.startswith("[Auto]"), f"Expected [Auto] for story 2, got: {stories[2].summary}")
        self.assertTrue(stories[3].summary.startswith("[Auto]"), f"Expected [Auto] for story 3, got: {stories[3].summary}")


# ---------------------------------------------------------------------------
# 3. TestPartialParseFailure
# ---------------------------------------------------------------------------

class TestPartialParseFailure(TestCase):
    """Batch response parses but summaries fail validation in _summarize_sub_batch."""

    def test_short_summaries_fail_validation(self):
        """Batch response has STORY_N format but _safe_sentence_summary produces
        single sentences → _is_valid_summary fails (too few sentences).
        Stories enter recovery → get [Auto] when recovery fails."""
        stories = [
            _make_story("Nu Finance Market Update Brief", "Finance"),
            _make_story("Xi Finance Trading Volume Low", "Finance"),
        ]

        short_resp = (
            "STORY_0 | Nu Finance Market Update=Market went up.\n"
            "STORY_1 | Xi Finance Trading Volume=Volume was down."
        )

        async def side_effect(**kwargs):
            return _make_mock_response(short_resp)

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, return_value=None):
                    await batch_summarize_all(client, stories, batch_size=2)

        _run(run())
        for s in stories:
            self.assertTrue(s.summary.startswith("[Auto]"), f"Expected [Auto] for {s.title}, got: {s.summary}")

    def test_boilerplate_caught_by_parser(self):
        """Batch response has STORY_N format but _is_boilerplate catches all text.
        Verify: stories enter recovery path, get [Auto] when recovery fails."""
        stories = [
            _make_story("Omicron Tech Startup Funding Round", "Tech"),
            _make_story("Pi Tech AI Robot Manufacturing Plant", "Tech"),
        ]

        boilerplate_resp = (
            "STORY_0 | Omicron Tech Startup=This article discusses the implications of the new policy thoroughly.\n"
            "STORY_1 | Pi Tech AI Robot=This highlights a significant trend in modern technology today."
        )

        async def side_effect(**kwargs):
            return _make_mock_response(boilerplate_resp)

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, return_value=None):
                    await batch_summarize_all(client, stories, batch_size=2)

        _run(run())
        for s in stories:
            self.assertTrue(s.summary.startswith("[Auto]"), f"Expected [Auto] for {s.title}, got: {s.summary}")


# ---------------------------------------------------------------------------
# 4. TestInvalidSingleRecovery
# ---------------------------------------------------------------------------

class TestInvalidSingleRecovery(TestCase):
    """Batch fails; single-story recovery via _summarize returns valid or invalid text."""

    def test_recovery_returns_valid_text(self):
        """Batch fails; _summarize returns text that passes recovery validation.
        Verify: recovered stories have real summaries, no [Auto] used."""
        stories = [
            _make_story("Rho Finance Interest Rate Change Decision", "Finance"),
            _make_story("Sigma Finance Bank Merger Announcement", "Finance"),
        ]

        async def side_effect(**kwargs):
            raise Exception("Batch error")

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        recovery_counter = [0]

        async def mock_summarize(client, ctx, title=None, **kwargs):
            idx = recovery_counter[0]
            recovery_counter[0] += 1
            texts = [
                "The Federal Reserve changed interest rates today by 0.25 percent. "
                "Analysts note this will affect borrowing costs nationwide significantly.",
                "Two major banks announced a merger worth $50 billion today. "
                "Investors reacted positively to the news in pre-market trading.",
            ]
            return texts[idx] if idx < len(texts) else None

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, side_effect=mock_summarize):
                    await batch_summarize_all(client, stories, batch_size=2)

        _run(run())
        for s in stories:
            self.assertNotIn("[Auto]", s.summary, f"Story {s.title} should not be [Auto], got: {s.summary}")

    def test_recovery_one_sentence_rejected(self):
        """Batch fails; recovery returns a one-sentence response.
        Verify: falls through to [Auto] fallback, not counted as recovered."""
        stories = [
            _make_story("Kappa Finance Credit Default Crisis", "Finance"),
        ]

        async def side_effect(**kwargs):
            raise Exception("Batch error")

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def mock_summarize(client, ctx, title=None, **kwargs):
            return "Credit defaults are rising across the sector as borrowers struggle with payments."

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, side_effect=mock_summarize):
                    await batch_summarize_all(client, stories, batch_size=2)

        _run(run())
        self.assertTrue(stories[0].summary.startswith("[Auto]"), f"Expected [Auto], got: {stories[0].summary}")

    def test_recovery_headline_echo_rejected(self):
        """Batch fails; recovery returns the exact headline.
        Verify: falls through to [Auto] fallback."""
        stories = [
            _make_story("Lambda Finance Stock Buyback Program", "Finance"),
        ]

        async def side_effect(**kwargs):
            raise Exception("Batch error")

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def mock_summarize(client, ctx, title=None, **kwargs):
            return "Lambda Finance Stock Buyback Program"

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, side_effect=mock_summarize):
                    await batch_summarize_all(client, stories, batch_size=2)

        _run(run())
        self.assertTrue(stories[0].summary.startswith("[Auto]"), f"Expected [Auto], got: {stories[0].summary}")

    def test_recovery_headline_plus_period_rejected(self):
        """Batch fails; recovery returns headline plus period.
        Verify: falls through to [Auto] fallback."""
        stories = [
            _make_story("Mu Finance Crypto Exchange Shutdown", "Finance"),
        ]

        async def side_effect(**kwargs):
            raise Exception("Batch error")

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def mock_summarize(client, ctx, title=None, **kwargs):
            return "Mu Finance Crypto Exchange Shutdown."

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, side_effect=mock_summarize):
                    await batch_summarize_all(client, stories, batch_size=2)

        _run(run())
        self.assertTrue(stories[0].summary.startswith("[Auto]"), f"Expected [Auto], got: {stories[0].summary}")

    def test_recovery_refusal_rejected(self):
        """Batch fails; recovery returns refusal text.
        Verify: falls through to [Auto] fallback."""
        stories = [
            _make_story("Nu Finance Bond Yield Spike Event", "Finance"),
        ]

        async def side_effect(**kwargs):
            raise Exception("Batch error")

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def mock_summarize(client, ctx, title=None, **kwargs):
            return "I cannot summarize the Bond Yield article. I don't have access to the full content."

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, side_effect=mock_summarize):
                    await batch_summarize_all(client, stories, batch_size=2)

        _run(run())
        self.assertTrue(stories[0].summary.startswith("[Auto]"), f"Expected [Auto], got: {stories[0].summary}")

    def test_recovery_refusal_with_headline_words_rejected(self):
        """Batch fails; recovery returns a two-sentence refusal containing headline keywords.
        Verify: [Auto] fallback via canonical _is_valid_summary, not counted as recovery."""
        stories = [
            _make_story("Xi Finance Stock Market Volatility Event", "Finance"),
        ]

        async def side_effect(**kwargs):
            raise Exception("Batch error")

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def mock_summarize(client, ctx, title=None, **kwargs):
            return "I cannot summarize the Stock Market Volatility article. I don't have access today."

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, side_effect=mock_summarize):
                    await batch_summarize_all(client, stories, batch_size=2)

        _run(run())
        self.assertTrue(stories[0].summary.startswith("[Auto]"), f"Expected [Auto], got: {stories[0].summary}")

    def test_recovery_no_topic_overlap_rejected(self):
        """Batch fails; recovery returns valid text but no keyword overlap with headline.
        Verify: falls through to [Auto] fallback."""
        stories = [
            _make_story("Omicron Finance Credit Default Risk", "Finance"),
        ]

        async def side_effect(**kwargs):
            raise Exception("Batch error")

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def mock_summarize(client, ctx, title=None, **kwargs):
            return "The weather in Houston has been unusually hot this season. Residents should stay cool today."

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, side_effect=mock_summarize):
                    await batch_summarize_all(client, stories, batch_size=2)

        _run(run())
        self.assertTrue(stories[0].summary.startswith("[Auto]"), f"Expected [Auto], got: {stories[0].summary}")

    def test_recovery_auto_fallback_not_counted_as_recovered(self):
        """Batch fails; _summarize returns a generated [Auto] headline fallback.
        Verify: [Auto] marker in story, auto_fallbacks incremented, not counted as recovery."""
        stories = [
            _make_story("Pi Finance Derivative Pricing Change", "Finance"),
        ]

        async def side_effect(**kwargs):
            raise Exception("Batch error")

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def mock_summarize(client, ctx, title=None, **kwargs):
            return "[Auto] Pi Finance Derivative Pricing Change"

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, side_effect=mock_summarize):
                    return await batch_summarize_all(client, stories, batch_size=2)

        metrics = _run(run())
        self.assertTrue(stories[0].summary.startswith("[Auto]"))
        self.assertEqual(metrics.auto_fallbacks, 1)
        self.assertEqual(metrics.individual_recovered, 0)

    def test_recovery_fails_validation(self):
        """Batch fails; _summarize returns text that fails recovery validation
        (is boilerplate). Verify: falls through to [Auto]."""
        stories = [
            _make_story("Tau Finance Market Crash", "Finance"),
            _make_story("Upsilon Finance Housing Bubble", "Finance"),
        ]

        async def side_effect(**kwargs):
            raise Exception("Batch error")

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        # Returns boilerplate text — recovery path rejects it → [Auto]
        async def mock_summarize(client, ctx, title=None, **kwargs):
            return "This article discusses the implications of the financial market crash thoroughly."

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, side_effect=mock_summarize):
                    await batch_summarize_all(client, stories, batch_size=2)

        _run(run())
        for s in stories:
            self.assertTrue(s.summary.startswith("[Auto]"), f"Expected [Auto] for {s.title}, got: {s.summary}")

    def test_recovery_concurrency_2_barrier(self):
        """Batch fails. _summarize mocked with async barrier events.
        Assert two recovery calls can enter before the first returns.
        Assert peak concurrent recovery calls equal recovery_max_concurrency."""
        stories = [
            _make_story("RecoverA Finance Market Rally Stocks", "Finance"),
            _make_story("RecoverB Finance Bond Yield Surge", "Finance"),
            _make_story("RecoverC Finance IPO Launch Filing", "Finance"),
        ]

        # Events for barrier synchronization — no reliance on asyncio.sleep patching
        second_entered = asyncio.Event()
        first_release = asyncio.Event()
        all_release = asyncio.Event()
        active = [0]
        max_active = [0]

        async def side_effect(**kwargs):
            raise Exception("Batch error")

        async def mock_summarize(client, ctx, title=None, **kwargs):
            active[0] += 1
            max_active[0] = max(max_active[0], active[0])
            if max_active[0] >= 2:
                second_entered.set()
            if not first_release.is_set():
                await first_release.wait()
            await all_release.wait()
            active[0] -= 1
            return f"Recovery summary for the {title} event with significant market impact. " \
                   "Analysts reported measurable changes in the sector today."

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            # NOTE: do NOT patch asyncio.sleep — it prevents task interleaving.
            # Patch only the retry config.
            with patch("daily_brief.config.LLM_SUMMARY_RETRY_ATTEMPTS", 1):
                with patch("daily_brief.config.LLM_SUMMARY_RETRY_BACKOFF", []):
                    with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, side_effect=mock_summarize):
                        result_task = asyncio.create_task(
                            batch_summarize_all(
                                client, stories, batch_size=3, recovery_max_concurrency=2
                            )
                        )
                        # Wait for the second task to enter the mock
                        await second_entered.wait()
                        self.assertGreaterEqual(max_active[0], 2)
                        self.assertLessEqual(max_active[0], 2)
                        first_release.set()
                        await asyncio.sleep(0)
                        all_release.set()
                        await result_task

        _run(run())
        self.assertGreaterEqual(max_active[0], 2,
            f"Expected at least 2 concurrent recovery calls, got peak {max_active[0]}")
        self.assertLessEqual(max_active[0], 2,
            f"Expected at most 2 concurrent recovery calls (max_concurrency=2), got peak {max_active[0]}")

    def test_recovery_concurrency_1_serial(self):
        """recovery_max_concurrency=1. Verify only one recovery call is active at a time
        using an active-count counter via barrier events."""
        stories = [
            _make_story("SerialA Finance Interest Rate Decision", "Finance"),
            _make_story("SerialB Finance Bank Merger Deal", "Finance"),
        ]

        active = [0]
        max_active = [0]
        gate = asyncio.Event()

        async def side_effect(**kwargs):
            raise Exception("Batch error")

        async def mock_summarize(client, ctx, title=None, **kwargs):
            active[0] += 1
            max_active[0] = max(max_active[0], active[0])
            await gate.wait()
            active[0] -= 1
            return f"Recovery summary for the {title} event with important details. " \
                   "Market analysts provided detailed analysis of the situation."

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def poll_and_release():
            for _ in range(200):
                if active[0] >= 1:
                    await asyncio.sleep(0)
                    # Second task should NOT be active concurrently
                    if active[0] <= 1:
                        gate.set()
                        await asyncio.sleep(0)
                        gate.set()  # Release second task
                        return
                await asyncio.sleep(0)
            gate.set()
            await asyncio.sleep(0)
            gate.set()

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, side_effect=mock_summarize):
                    poll_task = asyncio.create_task(poll_and_release())
                    recovery_task = asyncio.create_task(
                        batch_summarize_all(
                            client, stories, batch_size=2, recovery_max_concurrency=1
                        )
                    )
                    await recovery_task
                    await poll_task

        _run(run())
        self.assertEqual(max_active[0], 1,
            f"Expected only 1 concurrent recovery call (max_concurrency=1), got peak {max_active[0]}")

    def test_recovery_deadline_prevents_queue(self):
        """Batch fails. _summarize mocked with slow delays.
        Recovery deadline recovery_deadline_s=0.01.
        Assert that recovery attempts are bounded. Stories past the deadline get [Auto]."""
        stories = [
            _make_story("DeadlineA Finance Market Rally", "Finance"),
            _make_story("DeadlineB Finance Bond Yield", "Finance"),
            _make_story("DeadlineC Finance IPO Filing", "Finance"),
        ]

        async def side_effect(**kwargs):
            raise Exception("Batch error")

        mono_counter = [0]
        def mock_monotonic():
            # Each call advances time by 1 second — well past 0.01 deadline
            mono_counter[0] += 1
            return float(mono_counter[0])

        async def mock_summarize(client, ctx, title=None, **kwargs):
            # Even without sleep, the pre-dispatch gate checks monotonic time
            # and will skip if past deadline
            return f"Recovery summary for the {title} with important facts. " \
                   "Analysts reported significant findings in their analysis."

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, side_effect=mock_summarize):
                    with patch("daily_brief.llm.summarizer.time.monotonic", side_effect=mock_monotonic):
                        return await batch_summarize_all(
                            client, stories, batch_size=3,
                            recovery_max_concurrency=2,
                            recovery_deadline_s=0.01
                        )

        metrics = _run(run())
        # With time advancing past 0.01 on the first monotonic call,
        # all recovery tasks should hit the pre-dispatch deadline gate → [Auto]
        auto_count = sum(1 for s in stories if s.summary and s.summary.startswith("[Auto]"))
        self.assertGreater(auto_count, 0,
            f"Expected some [Auto] fallbacks due to deadline, all stories: {[s.summary[:30] for s in stories]}")

    def test_recovery_auto_fallback_on_all_fail(self):
        """All batch calls fail. _summarize returns valid recovery text.
        Assert individual_recovered equals the number of recovered stories and
        auto_fallbacks equals zero."""
        stories = [
            _make_story("AllRecoverA Finance Market Rally Stocks", "Finance"),
            _make_story("AllRecoverB Finance Bond Yield Surge", "Finance"),
        ]

        async def side_effect(**kwargs):
            raise Exception("Batch error")

        async def mock_summarize(client, ctx, title=None, **kwargs):
            if "RecoverA" in str(title):
                return "The financial market rallied with strong gains across major indices today. " \
                       "Analysts reported record trading volume in the tech sector."
            elif "RecoverB" in str(title):
                return "Bond yields surged to their highest level in six months on auction results. " \
                       "Traders adjusted portfolios to account for the rate change."
            return None

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, side_effect=mock_summarize):
                    return await batch_summarize_all(client, stories, batch_size=2)

        metrics = _run(run())
        for s in stories:
            self.assertNotIn("[Auto]", s.summary, f"Story {s.title} should not be [Auto], got: {s.summary}")
        self.assertEqual(metrics.individual_recovered, 2,
            f"Expected 2 recovered, got {metrics.individual_recovered}")
        self.assertEqual(metrics.auto_fallbacks, 0,
            f"Expected 0 auto_fallbacks, got {metrics.auto_fallbacks}")


# ---------------------------------------------------------------------------
# 5. TestExhaustedRecovery
# ---------------------------------------------------------------------------

class TestExhaustedRecovery(TestCase):
    """All batch and recovery calls fail; all stories fall back to [Auto]."""

    def test_all_batch_and_recovery_fail(self):
        """All batch calls fail, all single-story recovery returns None.
        Verify: all stories get [Auto] {title}. auto_fallbacks == total stories."""
        stories = [
            _make_story("Phi Tech Startup Round A Fund", "Tech"),
            _make_story("Chi Tech AI Neural Network Paper", "Tech"),
            _make_story("Psi Economics Inflation Data Release", "Economy"),
            _make_story("Omega Economics Jobs Report Monthly", "Economy"),
        ]

        async def side_effect(**kwargs):
            raise Exception("Total system failure")

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, return_value=None):
                    await batch_summarize_all(client, stories, batch_size=2)

        _run(run())
        auto_count = sum(1 for s in stories if s.summary and s.summary.startswith("[Auto]"))
        self.assertEqual(auto_count, len(stories))
        for s in stories:
            self.assertIn(s.title, s.summary)

    def test_partial_batch_success_mixed_recovery(self):
        """Batch partially succeeds for one category, fails for another.
        Recovery exhausted for failed ones with max_concurrency=2.
        Verify: valid stories have real summaries, failed stories have [Auto]."""
        stories = [
            _make_story("Alphaa Finance Market Rally Gains", "Finance"),
            _make_story("Alphab Finance Bond Yield Drop", "Finance"),
            _make_story("Alphac Climate Warming Data Rise", "Climate"),
            _make_story("Alphad Climate Ocean Plastic Cleanup", "Climate"),
        ]

        async def side_effect(**kwargs):
            msgs = kwargs.get("messages", [])
            if not _is_batch_call(msgs):
                return _make_mock_response("Recovered. Two sentences for validation.")
            user_msg = msgs[1].get("content", "")
            if "Climate" in user_msg:
                raise RuntimeError("Climate batch timeout")
            content = (
                "STORY_0 | Alphaa Finance Market Rally=Market rally gained strong momentum today with tech leading gains. "
                "The S&P 500 closed at record highs for the third day of trading.\n"
                "STORY_1 | Alphab Finance Bond Yield Drop=Bond yields dropped sharply following the latest treasury auction results. "
                "The 10-year note fell to its lowest level in six months of trading."
            )
            return _make_mock_response(content)

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, return_value=None):
                    await batch_summarize_all(
                        client, stories, batch_size=2, max_concurrency=2
                    )

        _run(run())
        # Finance: valid batch summaries
        self.assertNotIn("[Auto]", stories[0].summary)
        self.assertNotIn("[Auto]", stories[1].summary)
        # Climate: batch failed → recovery returns None → [Auto]
        self.assertTrue(stories[2].summary.startswith("[Auto]"))
        self.assertTrue(stories[3].summary.startswith("[Auto]"))


# ---------------------------------------------------------------------------
# 6. TestConcurrentMetrics
# ---------------------------------------------------------------------------

class TestConcurrentMetrics(TestCase):
    """Concurrent execution timing and metric consistency with max_concurrency=2."""

    def test_concurrent_execution_timing_and_metrics(self):
        """4 stories across 2 categories, max_concurrency=2.
        Use timing tracker to prove concurrent execution of batch calls.
        Verify metric counts are consistent."""
        stories = [
            _make_story("Bravo Tech AI Chip Design", "Tech"),
            _make_story("Charlie Tech Software Release", "Tech"),
            _make_story("Delta Economics GDP Growth Rate", "Economy"),
            _make_story("Echo Economics Trade Deficit", "Economy"),
        ]

        call_times = []
        batch_call_count = [0]
        single_call_count = [0]

        async def side_effect(**kwargs):
            msgs = kwargs.get("messages", [])
            t_start = time.time()
            if _is_batch_call(msgs):
                batch_call_count[0] += 1
                user_msg = msgs[1].get("content", "")
                # Build valid response for this batch's stories
                blocks = user_msg.split("\n---\n\n")
                hls = []
                for block in blocks:
                    for line in block.strip().split("\n"):
                        if line and not line.startswith(("1. ", "2. ", "3. ")):
                            hls.append(line.strip())
                            break
                lines = []
                for i, hl in enumerate(hls):
                    lines.append(
                        f"STORY_{i} | {hl}=Summary for the {hl} story here with detailed analysis. "
                        f"This report contains important findings about the topic area."
                    )
                await asyncio.sleep(0.05)  # Small delay for timing measurement
                t_end = time.time()
                call_times.append(("batch", t_start, t_end))
                return _make_mock_response("\n".join(lines))
            else:
                single_call_count[0] += 1
                return _make_mock_response(
                    "Recovery summary text with important facts about this story. "
                    "Analysts reported significant findings in their assessment."
                )

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            patches = _retry_patches()
            with patches[0], patches[1], patches[2]:
                with patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, return_value=None):
                    await batch_summarize_all(
                        client, stories, batch_size=2, max_concurrency=2
                    )

        _run(run())

        # Exactly 2 batch calls (1 per category)
        self.assertEqual(batch_call_count[0], 2, f"Expected 2 batch calls, got {batch_call_count[0]}")

        # With max_concurrency=2 and asyncio.gather, batch calls should overlap.
        # Check timing: start times should be close (< 15ms apart for concurrency)
        batch_times = [ts for kind, ts, te in call_times if kind == "batch"]
        if len(batch_times) >= 2:
            # Extract (start, end) pairs
            batch_intervals = [(ts, te) for kind, ts, te in call_times if kind == "batch"]
            if len(batch_intervals) >= 2:
                s1, e1 = batch_intervals[0]
                s2, e2 = batch_intervals[1]
                time_diff = abs(s1 - s2)
                self.assertLess(time_diff, 0.015,
                    f"Batch calls started {time_diff:.4f}s apart — not concurrent. "
                    f"Intervals: [{s1:.6f},{e1:.6f}] vs [{s2:.6f},{e2:.6f}]")

        # Metric consistency: all 4 stories have summaries
        total_with_summary = sum(1 for s in stories if s.summary)
        valid_summaries = sum(1 for s in stories if s.summary and "[Auto]" not in s.summary)
        fallback_summaries = sum(1 for s in stories if s.summary and s.summary.startswith("[Auto]"))
        self.assertEqual(total_with_summary, 4, "All stories should have summaries")
        self.assertEqual(valid_summaries + fallback_summaries, 4, "Sum of categories should equal total")
