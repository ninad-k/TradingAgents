"""Model name validators for each provider."""

from .model_catalog import get_known_models


# Providers whose model namespace is open-ended (local models, router repo
# IDs); any model name is accepted and never warned about.
_ACCEPT_ANY_MODEL = ("ollama", "openrouter", "huggingface")

VALID_MODELS = {
    provider: models
    for provider, models in get_known_models().items()
    if provider not in _ACCEPT_ANY_MODEL
}


def validate_model(provider: str, model: str) -> bool:
    """Check if model name is valid for the given provider.

    For ollama, openrouter, huggingface - any model is accepted.
    """
    provider_lower = provider.lower()

    if provider_lower in _ACCEPT_ANY_MODEL:
        return True

    if provider_lower not in VALID_MODELS:
        return True

    return model in VALID_MODELS[provider_lower]
