import os
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model


class NormalizedChatOpenAI(ChatOpenAI):
    """ChatOpenAI with normalized content output.

    The Responses API returns content as a list of typed blocks
    (reasoning, text, etc.). This normalizes to string for consistent
    downstream handling.
    """

    # Default method for with_structured_output; set per provider in get_llm().
    structured_output_method: str = "function_calling"

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))

    def with_structured_output(self, schema, *, method=None, **kwargs):
        """Wrap with structured output, defaulting to a per-provider method.

        OpenAI (function_calling): langchain-openai's Responses-API-parse path
        (the default for json_schema when use_responses_api=True) calls
        response.model_dump(...) on the OpenAI SDK's union-typed parsed
        response, which makes Pydantic emit ~20
        PydanticSerializationUnexpectedValue warnings per call. The
        function-calling path returns a plain tool-call shape that does not
        trigger that serialization, so it is the cleaner choice for our
        combination of use_responses_api=True + with_structured_output. Both
        paths use OpenAI's strict mode and produce the same typed Pydantic
        instance.

        Ollama local models (json_schema): small local models frequently emit
        empty tool args on the function-calling path, failing schema
        validation. Ollama's response_format json_schema path uses
        grammar-constrained decoding, which is reliable even for ~4B models.
        Ollama cloud models (":cloud" tags) ignore response_format json_schema
        and return prose, so they stay on function_calling.
        """
        if method is None:
            method = self.structured_output_method
        return super().with_structured_output(schema, method=method, **kwargs)

# Kwargs forwarded from user config to ChatOpenAI
_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "reasoning_effort",
    "api_key", "callbacks", "http_client", "http_async_client",
)

# Provider base URLs and API key env vars
_PROVIDER_CONFIG = {
    "xai": ("https://api.x.ai/v1", "XAI_API_KEY"),
    "deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "qwen": ("https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "glm": ("https://api.z.ai/api/paas/v4/", "ZHIPU_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "ollama": ("http://localhost:11434/v1", None),
    # Hugging Face Inference Providers — OpenAI-compatible router that fans
    # out to 15+ serverless partners. Model IDs are HF repo names (e.g.
    # "deepseek-ai/DeepSeek-V3-0324"); an optional ":provider" suffix pins a
    # specific backend, otherwise the fastest available is auto-selected.
    "huggingface": ("https://router.huggingface.co/v1", "HF_TOKEN"),
}


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI, Ollama, OpenRouter, and xAI providers.

    For native OpenAI models, uses the Responses API (/v1/responses) which
    supports reasoning_effort with function tools across all model families
    (GPT-4.1, GPT-5). Third-party compatible providers (xAI, OpenRouter,
    Ollama) use standard Chat Completions.
    """

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        provider: str = "openai",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider.lower()

    def get_llm(self) -> Any:
        """Return configured ChatOpenAI instance."""
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        # Provider-specific base URL and auth
        if self.provider in _PROVIDER_CONFIG:
            base_url, api_key_env = _PROVIDER_CONFIG[self.provider]
            llm_kwargs["base_url"] = base_url
            if api_key_env:
                api_key = os.environ.get(api_key_env)
                if api_key:
                    llm_kwargs["api_key"] = api_key
            else:
                llm_kwargs["api_key"] = "ollama"
        elif self.base_url:
            llm_kwargs["base_url"] = self.base_url

        # Forward user-provided kwargs
        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        # Native OpenAI: use Responses API for consistent behavior across
        # all model families. Third-party providers use Chat Completions.
        if self.provider == "openai":
            llm_kwargs["use_responses_api"] = True

        if self.provider == "ollama" and not self.model.endswith(":cloud"):
            llm_kwargs["structured_output_method"] = "json_schema"

        return NormalizedChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for the provider."""
        return validate_model(self.provider, self.model)
