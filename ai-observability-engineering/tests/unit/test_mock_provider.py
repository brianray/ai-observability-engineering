from aiobs.providers.mock import MockProvider


class _DeterministicClock:
    def __init__(self) -> None:
        self._now = 0.0

    def now(self) -> float:
        return self._now

    def sleep(self, seconds: float) -> None:
        self._now += seconds


def test_stream_chat_emits_role_only_chunk_before_content_and_usage_only_chunk_last():
    provider = MockProvider()
    chunks = list(
        provider.stream_chat(
            "what are the warranty terms",
            context="Hardware carries a twelve month limited warranty from delivery",
            stream_options={"include_usage": True},
            clock=_DeterministicClock(),
        )
    )

    assert chunks[0].choices
    assert chunks[0].choices[0].delta.role == "assistant"
    assert chunks[0].choices[0].delta.content == ""

    first_content = next(chunk for chunk in chunks if chunk.choices and chunk.choices[0].delta.content)
    assert first_content.choices[0].delta.content

    final_chunk = chunks[-1]
    assert final_chunk.choices == []
    assert final_chunk.usage is not None
    assert final_chunk.usage.completion_tokens == provider.stream_completion_tokens


def test_chat_without_retry_reports_single_attempt_metadata():
    reply = MockProvider(retry_fraction=0.0).chat(
        "what are the warranty terms",
        context="Hardware carries a twelve month limited warranty from delivery",
    )

    assert reply.attempts == 1
    assert reply.attempt_models == (reply.model,)


def test_chat_with_retry_reports_two_attempts_metadata_deterministically():
    reply = MockProvider(retry_fraction=1.0).chat(
        "what are the warranty terms",
        context="Hardware carries a twelve month limited warranty from delivery",
    )

    assert reply.attempts == 2
    assert reply.attempt_models == (reply.model, reply.model)

    baseline = MockProvider(retry_fraction=0.0).chat(
        "what are the warranty terms",
        context="Hardware carries a twelve month limited warranty from delivery",
    )
    assert reply.input_tokens == baseline.input_tokens * 2
    assert reply.output_tokens == baseline.output_tokens * 2
