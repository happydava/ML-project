"""LLM adapter (FR-7.7): one interface for every provider, chosen in the admin panel.

Most providers (Groq, OpenRouter, Together, Cerebras, Mistral, Gemini, OpenAI, a local Ollama) speak the
OpenAI "chat/completions" protocol, so one code path covers them. Anthropic has its own protocol.
Only the standard library is used.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

PRESETS = {
    "groq": {"label": "Groq: открытые модели Llama, быстрый", "base_url": "https://api.groq.com/openai/v1",
             "model": "llama-3.3-70b-versatile", "key_url": "https://console.groq.com/keys", "needs_key": True},
    "openrouter": {"label": "OpenRouter: много открытых моделей, часть бесплатно", "base_url": "https://openrouter.ai/api/v1",
                   "model": "meta-llama/llama-3.3-70b-instruct:free", "key_url": "https://openrouter.ai/keys", "needs_key": True},
    "together": {"label": "Together AI: Llama, Qwen, DeepSeek", "base_url": "https://api.together.xyz/v1",
                 "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo", "key_url": "https://api.together.ai/settings/api-keys", "needs_key": True},
    "cerebras": {"label": "Cerebras: открытые модели, очень быстрый", "base_url": "https://api.cerebras.ai/v1",
                 "model": "llama-3.3-70b", "key_url": "https://cloud.cerebras.ai", "needs_key": True},
    "mistral": {"label": "Mistral: открытые и закрытые модели", "base_url": "https://api.mistral.ai/v1",
                "model": "mistral-small-latest", "key_url": "https://console.mistral.ai/api-keys", "needs_key": True},
    "gemini": {"label": "Google Gemini (не открытая модель, есть бесплатный тариф)",
               "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
               "model": "gemini-2.5-flash", "key_url": "https://aistudio.google.com/apikey", "needs_key": True},
    "ollama": {"label": "Ollama: модель на этом компьютере, без ключа и без интернета", "base_url": "http://localhost:11434/v1",
               "model": "qwen2.5:7b", "key_url": "https://ollama.com/download", "needs_key": False},
    "openai": {"label": "OpenAI", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini",
               "key_url": "https://platform.openai.com/api-keys", "needs_key": True},
    "anthropic": {"label": "Anthropic Claude (как в дипломе: класс Sonnet)", "base_url": "https://api.anthropic.com",
                  "model": "claude-sonnet-5-5", "key_url": "https://console.anthropic.com/settings/keys", "needs_key": True},
    "custom": {"label": "Другой сервис с протоколом OpenAI", "base_url": "", "model": "", "key_url": "", "needs_key": False},
}


class LLMError(Exception):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


def api_key(cfg: dict) -> str:
    return cfg.get("llm_api_key") or os.environ.get("DATERA_LLM_API_KEY", "")


def _request(url: str, headers: dict, body: dict | None, timeout: float) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json", "User-Agent": "datera-edu-mini", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[:300].replace("\n", " ")
        hint = {401: " Проверьте ключ.", 403: " Нет доступа: проверьте ключ и регион.", 404: " Проверьте адрес и название модели: нажмите «Показать доступные модели».",
                429: " Превышен лимит запросов, подождите и повторите."}.get(e.code, "")
        raise LLMError(f"Ошибка {e.code} от сервиса.{hint} {detail}", e.code) from None
    except urllib.error.URLError as e:
        raise LLMError(f"Нет соединения с {url}: {e.reason}") from None
    except (TimeoutError, json.JSONDecodeError) as e:
        raise LLMError(f"Сервис не ответил или вернул не JSON: {e}") from None


def chat(cfg: dict, system: str, user: str, json_mode: bool = True, timeout: float = 240) -> str:
    base, model, key = (cfg.get("llm_base_url") or "").rstrip("/"), cfg.get("llm_model") or "", api_key(cfg)
    if not base or not model:
        raise LLMError("В настройках не указан адрес сервиса или модель")
    if PRESETS.get(cfg.get("llm_provider"), {}).get("needs_key") and not key:
        raise LLMError("В настройках не указан API-ключ")
    if cfg.get("llm_provider") == "anthropic":
        data = _request(base + "/v1/messages", {"x-api-key": key, "anthropic-version": "2023-06-01"},
                        {"model": model, "max_tokens": 8000, "system": system,
                         "messages": [{"role": "user", "content": user}]}, timeout)
        return "".join(b.get("text", "") for b in data.get("content", []))
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    body = {"model": model, "temperature": float(cfg.get("llm_temperature") or 0.2),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    try:
        data = _request(base + "/chat/completions", headers, body, timeout)
    except LLMError as e:
        if e.code in (400, 422) and ("response_format" in body):   # some models do not support JSON mode or temperature
            body.pop("response_format"), body.pop("temperature", None)
            data = _request(base + "/chat/completions", headers, body, timeout)
        else:
            raise
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise LLMError("Сервис вернул ответ в неожиданном формате") from None


def list_models(cfg: dict) -> list[str]:
    base, key = (cfg.get("llm_base_url") or "").rstrip("/"), api_key(cfg)
    if cfg.get("llm_provider") == "anthropic":
        data = _request(base + "/v1/models", {"x-api-key": key, "anthropic-version": "2023-06-01"}, None, 20)
    else:
        data = _request(base + "/models", {"Authorization": f"Bearer {key}"} if key else {}, None, 20)
    return sorted(str(m.get("id", "")).removeprefix("models/") for m in data.get("data", data.get("models", [])) if m.get("id"))


def parse_json(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)      # reasoning models (Qwen3, DeepSeek-R1) think aloud first
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("в ответе нет JSON")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("JSON не объект")
    return data
