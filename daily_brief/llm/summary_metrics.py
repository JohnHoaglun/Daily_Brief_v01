"""Lightweight summarization metrics returned by batch_summarize_all()."""


class SummaryMetrics:
    __slots__ = (
        "auto_fallbacks",
        "batch_calls",
        "batch_failures",
        "batch_retries",
        "elapsed_s",
        "final_invalid",
        "final_valid",
        "individual_recovered",
        "individual_recovery_attempts",
        "sub_batches",
        "total_stories",
        "unavailable_summaries",
    )

    def __init__(
        self,
        total_stories: int = 0,
        sub_batches: int = 0,
        batch_calls: int = 0,
        batch_retries: int = 0,
        batch_failures: int = 0,
        individual_recovery_attempts: int = 0,
        individual_recovered: int = 0,
        auto_fallbacks: int = 0,
        unavailable_summaries: int = 0,
        final_valid: int = 0,
        final_invalid: int = 0,
        elapsed_s: float = 0.0,
    ):
        self.total_stories = total_stories
        self.sub_batches = sub_batches
        self.batch_calls = batch_calls
        self.batch_retries = batch_retries
        self.batch_failures = batch_failures
        self.individual_recovery_attempts = individual_recovery_attempts
        self.individual_recovered = individual_recovered
        self.auto_fallbacks = auto_fallbacks
        self.unavailable_summaries = unavailable_summaries
        self.final_valid = final_valid
        self.final_invalid = final_invalid
        self.elapsed_s = elapsed_s

    @property
    def is_valid(self) -> bool:
        return (
            self.final_valid
            + self.auto_fallbacks
            + self.unavailable_summaries
            + self.final_invalid
            == self.total_stories
        )

    def to_dict(self) -> dict:
        return {attr: getattr(self, attr) for attr in self.__slots__}

    def __repr__(self):
        return (
            f"SummaryMetrics(stories={self.total_stories}, "
            f"valid={self.final_valid}, auto={self.auto_fallbacks}, "
            f"unavailable={self.unavailable_summaries}, invalid={self.final_invalid}, "
            f"elapsed={self.elapsed_s:.2f}s)"
        )


def validate_metrics(metrics: SummaryMetrics) -> bool:
    return metrics.is_valid


def empty_metrics(total: int = 0) -> SummaryMetrics:
    return SummaryMetrics(total_stories=total)
