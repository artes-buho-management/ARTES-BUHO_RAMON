"""Cerebro alternativo local (Ollama) para cuando Gemini agota cuota.

Activar con env var BRAIN_FALLBACK=ollama. Ramón probará Gemini primero; si cae
en QuotaExceeded o circuit breaker, cae automáticamente a Ollama local.

Requisitos:
- Ollama corriendo en OLLAMA_URL (default http://localhost:11434).
- Modelo descargado (recomendado qwen2.5:14b-instruct, llama3.1:8b, mistral).

En el VPS Coolify, Ollama se puede levantar como segundo servicio docker.
Si no hay Ollama disponible, el fallback devuelve error claro pero NO gasta cuota.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx


def _ollama_url() -> str:
    return os.getenv("OLLAMA_URL", "http://localhost:11434")


def _model() -> str:
    return os.getenv("OLLAMA_MODEL", "qwen2.5:14b-instruct")


def available() -> bool:
    """True si Ollama responde."""
    try:
        r = httpx.get(f"{_ollama_url()}/api/tags", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def generate(system: str, user: str, *, json_mode: bool = False, max_tokens: int = 2000) -> str:
    """Llamada simple a Ollama con system + user."""
    payload: dict[str, Any] = {
        "model": _model(),
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": max_tokens},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_mode:
        payload["format"] = "json"
    r = httpx.post(f"{_ollama_url()}/api/chat", json=payload, timeout=180.0)
    r.raise_for_status()
    data = r.json()
    return (data.get("message", {}).get("content") or "").strip()


def classify_email(*, system_prompt: str, user_text: str) -> dict[str, Any]:
    """Versión Ollama del clasificador. Intenta devolver JSON igual a Gemini."""
    text = generate(system_prompt, user_text, json_mode=True, max_tokens=2500)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        if s >= 0 and e > s:
            return json.loads(text[s:e + 1])
        raise


def answer(question: str, system_prompt: str, context: str = "") -> str:
    user = f"{context}\n\n{question}" if context else question
    return generate(system_prompt, user, json_mode=False, max_tokens=800)
