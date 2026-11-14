"""Model providers and presets. Verda is the default provider; the other providers are named in a strategy's
`base_model` or brought by a preset.

A strategy's `base_model` is `{model, provider?, base_url?, key_env?}`. `model` is a preset name (see PRESETS) or a raw
model id. An explicit `provider`, `base_url` or `key_env` wins over the preset's and the provider's."""
import os
from dataclasses import dataclass

from .errors import ModelError

ALL_CHOICES = ("auto", "required", "none")

# Verda's inference URL depends on the deployment, so it comes from the environment (check it with
# tools/models_probe.py). `rpm` = requests per minute allowed (None = no limit); NVIDIA's free tier allows 40.
# `client`: "openai" (Chat Completions, models.ModelClient) or "anthropic" (Messages API, anthropic_client).
# `tool_choices`: what the provider accepts. Anthropic's current Opus/Sonnet models refuse forced tool use but take
# "none"; Meta's Model API takes only "auto" (dev.meta.ai docs, 2026-11-14). The runner adapts to what is missing.
# `default_model`: the preset training uses when VENUS_TRAIN_PROVIDER names this provider and VENUS_TRAIN_MODEL is
# unset. `key_env_alt`: a second variable name the key may be stored under.
PROVIDERS = {
    "verda": {"base_url_env": "VERDA_BASE_URL", "base_url": None, "key_env": "VERDA_API_KEY", "rpm": None},
    "nvidia": {"base_url_env": "NVIDIA_BASE_URL", "base_url": "https://integrate.api.nvidia.com/v1",
               "key_env": "NVIDIA_API_KEY", "rpm": 40},
    "anthropic": {"base_url_env": "ANTHROPIC_BASE_URL", "base_url": "https://api.anthropic.com",
                  "key_env": "ANTHROPIC_API_KEY", "rpm": None, "client": "anthropic",
                  "tool_choices": ("auto", "none"), "default_model": "claude-research"},
    "meta": {"base_url_env": "META_BASE_URL", "base_url": "https://api.meta.ai/v1", "key_env": "META_API_KEY",
             "key_env_alt": "MODEL_API_KEY", "rpm": None, "tool_choices": ("auto",), "default_model": "meta"},
    "gemini": {"base_url_env": "GEMINI_BASE_URL", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
               "key_env": "GEMINI_API_KEY", "rpm": 10, "default_model": "gemini"},
}
DEFAULT_PROVIDER = "verda"

# Preset -> (env var with the model id, default id[, provider]). A preset with a provider uses it unless the
# base_model names one. Nemotron/Gemma defaults are NVIDIA Build ids; Gemini's default id is unconfirmed (off by
# default; the live test checks it).
PRESETS = {
    "nemotron": ("VENUS_NEMOTRON_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b"),
    "gemma": ("VENUS_GEMMA_MODEL", "google/gemma-3-27b-it"),
    "claude-research": ("VENUS_CLAUDE_RESEARCH_MODEL", "claude-opus-5-5", "anthropic"),
    "claude-fast": ("VENUS_CLAUDE_FAST_MODEL", "claude-opus-5-5", "anthropic"),
    "meta": ("VENUS_META_MODEL", "muse-spark-1.3", "meta"),
    "gemini": ("VENUS_GEMINI_MODEL", "gemini-flash-latest", "gemini"),
}


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    base_url: str
    model: str
    key_env: str
    client: str = "openai"
    tool_choices: tuple = ALL_CHOICES


def resolve_model(base_model: dict, environ=None) -> ModelSpec:
    environ = os.environ if environ is None else environ
    model = base_model.get("model", "")
    preset = PRESETS.get(model)
    provider = base_model.get("provider") or (preset[2] if preset and len(preset) > 2 else None) or DEFAULT_PROVIDER
    if provider not in PROVIDERS:
        raise ModelError("model_config_missing", f"unknown provider {provider!r}; known: {sorted(PROVIDERS)}",
                         "base_model.provider")
    info = PROVIDERS[provider]

    if preset:
        model = environ.get(preset[0]) or preset[1]
    if not model:
        raise ModelError("model_config_missing", "base_model.model is empty", "base_model.model")

    base_url = base_model.get("base_url") or environ.get(info["base_url_env"]) or info["base_url"]
    if not base_url:
        raise ModelError("model_config_missing",
                         f"no base URL for provider {provider!r}: set {info['base_url_env']} or base_model.base_url",
                         "base_model.base_url")
    return ModelSpec(provider=provider, base_url=base_url.rstrip("/"), model=model,
                     key_env=base_model.get("key_env") or info["key_env"], client=info.get("client", "openai"),
                     tool_choices=tuple(info.get("tool_choices", ALL_CHOICES)))
