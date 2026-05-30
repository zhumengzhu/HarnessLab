"""Tests for provider usage normalization."""

from __future__ import annotations

from harnesslab.providers.pricing import CanonicalUsage, normalize_usage


def test_normalize_usage_anthropic_maps_cache_buckets() -> None:
    usage = normalize_usage(
        {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_creation_input_tokens": 200,
            "cache_read_input_tokens": 300,
        },
        provider="anthropic",
        api_mode="anthropic_messages",
    )
    assert usage == CanonicalUsage(
        input=100,
        output=50,
        cache_read=300,
        cache_write=200,
    )
    assert usage.prompt_tokens == 600
    assert usage.total_tokens == 650


def test_normalize_usage_anthropic_splits_cache_creation_tiers() -> None:
    usage = normalize_usage(
        {
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_creation_input_tokens": 150,
            "cache_read_input_tokens": 20,
            "cache_creation": {
                "ephemeral_5m_input_tokens": 100,
                "ephemeral_1h_input_tokens": 50,
            },
        },
        provider="anthropic",
        api_mode="anthropic_messages",
    )
    assert usage.cache_write == 0
    assert usage.cache_write_5m == 100
    assert usage.cache_write_1h == 50
    assert usage.cache_read == 20


def test_normalize_usage_openai_responses_subtracts_cached_input() -> None:
    usage = normalize_usage(
        {
            "input_tokens": 1000,
            "output_tokens": 200,
            "input_tokens_details": {"cached_tokens": 400, "cache_creation_tokens": 100},
            "output_tokens_details": {"reasoning_tokens": 50},
        },
        provider="openai",
        api_mode="openai_responses",
    )
    assert usage.input == 500
    assert usage.cache_read == 400
    assert usage.cache_write == 100
    assert usage.output == 200
    assert usage.reasoning == 50


def test_normalize_usage_deepseek_cache_hit() -> None:
    usage = normalize_usage(
        {
            "prompt_tokens": 800,
            "completion_tokens": 120,
            "prompt_cache_hit_tokens": 300,
        },
        provider="deepseek",
        api_mode="openai_chat",
    )
    assert usage.input == 500
    assert usage.cache_read == 300
    assert usage.output == 120


def test_normalize_usage_gemini_thoughts() -> None:
    usage = normalize_usage(
        {
            "promptTokenCount": 90,
            "candidatesTokenCount": 10,
            "thoughtsTokenCount": 25,
        },
        provider="gemini",
        api_mode="gemini",
    )
    assert usage.input == 90
    assert usage.output == 10
    assert usage.reasoning == 25
    assert usage.total_tokens == 125


def test_legacy_token_fields_from_breakdown() -> None:
    from harnesslab.providers.pricing.normalize import legacy_token_fields

    usage = CanonicalUsage(input=100, output=20, cache_read=50, reasoning=5)
    fields = legacy_token_fields(usage)
    assert fields["request_tokens"] == 150
    assert fields["response_tokens"] == 25
    assert fields["total_tokens"] == 175
