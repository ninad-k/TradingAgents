"""Shared model catalog for CLI selections and validation."""

from __future__ import annotations

from typing import Dict, List, Tuple

ModelOption = Tuple[str, str]
ProviderModeOptions = Dict[str, Dict[str, List[ModelOption]]]


MODEL_OPTIONS: ProviderModeOptions = {
    "openai": {
        "quick": [
            ("GPT-5.4 Mini - Fast, strong coding and tool use", "gpt-5.4-mini"),
            ("GPT-5.4 Nano - Cheapest, high-volume tasks", "gpt-5.4-nano"),
            ("GPT-5.4 - Latest frontier, 1M context", "gpt-5.4"),
            ("GPT-4.1 - Smartest non-reasoning model", "gpt-4.1"),
        ],
        "deep": [
            ("GPT-5.4 - Latest frontier, 1M context", "gpt-5.4"),
            ("GPT-5.2 - Strong reasoning, cost-effective", "gpt-5.2"),
            ("GPT-5.4 Mini - Fast, strong coding and tool use", "gpt-5.4-mini"),
            ("GPT-5.4 Pro - Most capable, expensive ($30/$180 per 1M tokens)", "gpt-5.4-pro"),
        ],
    },
    "anthropic": {
        "quick": [
            ("Claude Sonnet 5 - New frontier", "claude-sonnet-5"),
            ("Claude Sonnet 4.6 - Best speed and intelligence balance", "claude-sonnet-4-6"),
            ("Claude Haiku 4.5 - Fast, near-instant responses", "claude-haiku-4-5"),
            ("Claude Sonnet 4.5 - Agents and coding", "claude-sonnet-4-5"),
        ],
        "deep": [
            ("Claude Sonnet 5 - New frontier", "claude-sonnet-5"),
            ("Claude Opus 4.6 - Most intelligent, agents and coding", "claude-opus-4-6"),
            ("Claude Opus 4.5 - Premium, max intelligence", "claude-opus-4-5"),
            ("Claude Sonnet 4.6 - Best speed and intelligence balance", "claude-sonnet-4-6"),
            ("Claude Sonnet 4.5 - Agents and coding", "claude-sonnet-4-5"),
        ],
    },
    "google": {
        "quick": [
            ("Gemini 3 Flash - Next-gen fast", "gemini-3-flash-preview"),
            ("Gemini 2.5 Flash - Balanced, stable", "gemini-2.5-flash"),
            ("Gemini 3.1 Flash Lite - Most cost-efficient", "gemini-3.1-flash-lite-preview"),
            ("Gemini 2.5 Flash Lite - Fast, low-cost", "gemini-2.5-flash-lite"),
        ],
        "deep": [
            ("Gemini 3.1 Pro - Reasoning-first, complex workflows", "gemini-3.1-pro-preview"),
            ("Gemini 3 Flash - Next-gen fast", "gemini-3-flash-preview"),
            ("Gemini 2.5 Pro - Stable pro model", "gemini-2.5-pro"),
            ("Gemini 2.5 Flash - Balanced, stable", "gemini-2.5-flash"),
        ],
    },
    "xai": {
        "quick": [
            ("Grok 4.1 Fast (Non-Reasoning) - Speed optimized, 2M ctx", "grok-4-1-fast-non-reasoning"),
            ("Grok 4 Fast (Non-Reasoning) - Speed optimized", "grok-4-fast-non-reasoning"),
            ("Grok 4.1 Fast (Reasoning) - High-performance, 2M ctx", "grok-4-1-fast-reasoning"),
        ],
        "deep": [
            ("Grok 4 - Flagship model", "grok-4-0709"),
            ("Grok 4.1 Fast (Reasoning) - High-performance, 2M ctx", "grok-4-1-fast-reasoning"),
            ("Grok 4 Fast (Reasoning) - High-performance", "grok-4-fast-reasoning"),
            ("Grok 4.1 Fast (Non-Reasoning) - Speed optimized, 2M ctx", "grok-4-1-fast-non-reasoning"),
        ],
    },
    "deepseek": {
        "quick": [
            ("DeepSeek V3.2", "deepseek-chat"),
            ("Custom model ID", "custom"),
        ],
        "deep": [
            ("DeepSeek V3.2 (thinking)", "deepseek-reasoner"),
            ("DeepSeek V3.2", "deepseek-chat"),
            ("Custom model ID", "custom"),
        ],
    },
    "qwen": {
        "quick": [
            ("Qwen 3.5 Flash", "qwen3.5-flash"),
            ("Qwen Plus", "qwen-plus"),
            ("Custom model ID", "custom"),
        ],
        "deep": [
            ("Qwen 3.6 Plus", "qwen3.6-plus"),
            ("Qwen 3.5 Plus", "qwen3.5-plus"),
            ("Qwen 3 Max", "qwen3-max"),
            ("Custom model ID", "custom"),
        ],
    },
    "glm": {
        "quick": [
            ("GLM-4.7", "glm-4.7"),
            ("GLM-5", "glm-5"),
            ("Custom model ID", "custom"),
        ],
        "deep": [
            ("GLM-5.1", "glm-5.1"),
            ("GLM-5", "glm-5"),
            ("Custom model ID", "custom"),
        ],
    },
    # Hugging Face Inference Providers (OpenAI-compatible router). Model IDs are
    # HF repo names; the validator accepts any, so custom IDs work too. These
    # picks all support tool calling + structured output (required by the agent
    # graph). Availability on the serverless router can change — verify on
    # https://huggingface.co/<id> if a request 404s, and swap as needed.
    "huggingface": {
        "quick": [
            ("Qwen3 30B A3B - Fast MoE, strong tool use", "Qwen/Qwen3-30B-A3B"),
            ("GPT-OSS 20B - Open reasoning, cheap", "openai/gpt-oss-20b"),
            ("Llama 3.3 70B Instruct - Reliable tool calling", "meta-llama/Llama-3.3-70B-Instruct"),
            ("Qwen 2.5 72B Instruct - Broad capability", "Qwen/Qwen2.5-72B-Instruct"),
            ("Custom model ID", "custom"),
        ],
        "deep": [
            ("DeepSeek V3 (0324) - Top open reasoning", "deepseek-ai/DeepSeek-V3-0324"),
            ("Qwen3 235B A22B - Large MoE, deep reasoning", "Qwen/Qwen3-235B-A22B"),
            ("GPT-OSS 120B - Open frontier reasoning", "openai/gpt-oss-120b"),
            ("Llama 3.3 70B Instruct - Reliable tool calling", "meta-llama/Llama-3.3-70B-Instruct"),
            ("Custom model ID", "custom"),
        ],
    },
    # OpenRouter: fetched dynamically. Azure: any deployed model name.
    # Ollama also serves cloud models (":cloud" tags) through the local daemon
    # after `ollama signin` — inference runs on ollama.com, not this machine.
    "ollama": {
        "quick": [
            ("Qwen3 4B (local, tool calling)", "qwen3:4b"),
            ("Qwen 2.5 1.5B (cheapest local)", "qwen2.5:1.5b"),
            ("Qwen 2.5 3B (local)", "qwen2.5:3b"),
            ("Gemma 3 (4B, local fallback)", "gemma3:4b"),
            ("Qwen3:latest (8B, local)", "qwen3:latest"),
            ("GPT-OSS:latest (20B, local)", "gpt-oss:latest"),
            ("GLM-4.7-Flash:latest (30B, local)", "glm-4.7-flash:latest"),
        ],
        "deep": [
            ("GLM-5.2 (Ollama cloud, needs signin)", "glm-5.2:cloud"),
            ("Kimi K3 (Ollama cloud, needs Pro/Max)", "kimi-k3:cloud"),
            ("Qwen 2.5 1.5B (cheapest local)", "qwen2.5:1.5b"),
            ("Qwen 2.5 3B (local)", "qwen2.5:3b"),
            ("Gemma 3 (4B, local fallback)", "gemma3:4b"),
            ("GLM-4.7-Flash:latest (30B, local)", "glm-4.7-flash:latest"),
            ("GPT-OSS:latest (20B, local)", "gpt-oss:latest"),
            ("Qwen3:latest (8B, local)", "qwen3:latest"),
        ],
    },
}


def get_model_options(provider: str, mode: str) -> List[ModelOption]:
    """Return shared model options for a provider and selection mode."""
    return MODEL_OPTIONS[provider.lower()][mode]


def get_known_models() -> Dict[str, List[str]]:
    """Build known model names from the shared CLI catalog."""
    return {
        provider: sorted(
            {
                value
                for options in mode_options.values()
                for _, value in options
            }
        )
        for provider, mode_options in MODEL_OPTIONS.items()
    }
