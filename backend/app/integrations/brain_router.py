"""Cascada de cerebros IA de Ramon.

Orden estricto POR POTENCIA DESCENDENTE. Cuando un nivel falla, rate-limit
(429) o agota cuota free, la cascada baja automaticamente al siguiente.

Cuotas free conocidas (2026-04):
1. SambaNova   DeepSeek-V3.2        (685B)  ~10 req/min, free
2. Cerebras    qwen-3-235b          (235B)  30 req/min, 14.4K req/dia, 1M tok/dia
3. OpenRouter  gpt-oss-120b:free    (120B)  50 req/dia con modelos :free
4. Groq        llama-3.3-70b         (70B)  30 req/min, 14.4K req/dia, 500K tok/dia
5. Mistral     large-latest        (123B)  1 req/seg, 500K tok/mes free
6. Gemini      2.5 Flash             (-)    15 RPM, 1500 req/dia
7. PC local    qwen2.5:14b           (14B)  sin limite (local)
8. VPS Ollama  qwen2.5:1.5b         (1.5B)  sin limite (local VPS)

Estrategia de "exprimir al maximo": cuando un provider devuelve 429 (Too Many
Requests), se marca en COOLDOWN por N segundos y la cascada salta al siguiente.
Tras el cooldown, vuelve a intentarse desde el nivel mas alto disponible. Asi
cada provider se usa todo lo que permita su cuota antes de rotar.

Todos los providers cloud usan formato OpenAI-compatible (chat/completions).
Gemini usa SDK propio (gemini_brain.py). Ollama usa su API nativa.

Env vars (todas opcionales - si falta key, ese nivel se omite):
- SAMBANOVA_API_KEY + SAMBANOVA_MODEL (default DeepSeek-V3.2)
- CEREBRAS_API_KEY  + CEREBRAS_MODEL  (default qwen-3-235b-a22b-instruct-2507)
- OPENROUTER_API_KEY + OPENROUTER_MODEL (default openai/gpt-oss-120b:free)
- GROQ_API_KEY      + GROQ_MODEL      (default llama-3.3-70b-versatile)
- MISTRAL_API_KEY   + MISTRAL_MODEL   (default mistral-large-latest)
- GEMINI_API_KEY    + GEMINI_MODEL    (default gemini-2.5-flash)
- PC_OLLAMA_URL     + PC_OLLAMA_MODEL (default qwen2.5:14b)
- OLLAMA_URL        + OLLAMA_MODEL    (default qwen2.5:1.5b)
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx


log = logging.getLogger("ramon.brain")


# ========================================================================
# Cooldown tracker - cuando un provider da 429, se marca en cooldown.
# Mientras este en cooldown, la cascada lo salta sin llamar a la API.
# Al expirar el cooldown, vuelve a ser candidato normal.
# ========================================================================

_COOLDOWN_SECONDS = {
    "sambanova": 60,    # free tier estricto por minuto
    "nvidia":    3600,  # 1000 req/mes, cuando agota cooldown 1h
    "cerebras":  60,
    "mistral":   5,     # 1 req/seg
    "openrouter": 3600, # 50 req/dia
    "groq":      60,
    "gemini":    300,   # 1500 req/dia
}

_cooldowns: dict[str, float] = {}   # provider -> timestamp cuando termina cooldown


def _in_cooldown(provider: str) -> bool:
    end = _cooldowns.get(provider, 0)
    return end > time.time()


def _mark_cooldown(provider: str, seconds: int | None = None) -> None:
    s = seconds if seconds is not None else _COOLDOWN_SECONDS.get(provider, 60)
    _cooldowns[provider] = time.time() + s
    log.info(f"{provider} en cooldown {s}s (hasta {time.strftime('%H:%M:%S', time.localtime(_cooldowns[provider]))})")


def cooldowns_snapshot() -> dict[str, float]:
    """Segundos restantes de cooldown por provider. 0 = activo."""
    now = time.time()
    return {k: max(0, round(v - now, 1)) for k, v in _cooldowns.items()}


# ========================================================================
# Helpers genericos OpenAI-compatible (para SambaNova, Cerebras, OpenRouter,
# Groq, Mistral - todos exponen /v1/chat/completions con el mismo shape).
# ========================================================================

def _openai_compat_call(
    base_url: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    json_mode: bool = False,
    max_tokens: int = 2000,
    extra_headers: dict | None = None,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        # 0.4 = respuestas mas dinamicas/variadas sin perder coherencia
        "temperature": 0.4,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    # timeout 30s + 1 retry sobre error de red (no sobre 4xx/5xx del provider)
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            r = httpx.post(base_url.rstrip("/") + "/chat/completions",
                           json=payload, headers=headers, timeout=30.0)
            r.raise_for_status()
            data = r.json()
            choices = data.get("choices") or []
            if not choices:
                return ""
            return (choices[0].get("message", {}).get("content") or "").strip()
        except httpx.HTTPStatusError:
            raise  # Error del provider (429, etc) -> no retry, deja que cascada baje
        except (httpx.ReadError, httpx.ConnectError, httpx.ReadTimeout) as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(0.5)
                continue
            raise
    if last_exc:
        raise last_exc
    return ""


def _ollama_generate(url: str, model: str, system: str, user: str,
                     json_mode: bool = False, max_tokens: int = 2000) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": max_tokens},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_mode:
        payload["format"] = "json"
    r = httpx.post(f"{url.rstrip('/')}/api/chat", json=payload, timeout=180.0)
    r.raise_for_status()
    data = r.json()
    return (data.get("message", {}).get("content") or "").strip()


# ========================================================================
# Nivel 1 - SambaNova DeepSeek-V3.2 (685B)
# ========================================================================

def _samba_key() -> str: return os.getenv("SAMBANOVA_API_KEY", "").strip()
def _samba_model() -> str: return os.getenv("SAMBANOVA_MODEL", "DeepSeek-V3.2")

def sambanova_available() -> bool:
    return bool(_samba_key())

def _sambanova_call(system: str, user: str, json_mode: bool = False, max_tokens: int = 2000) -> str:
    return _openai_compat_call("https://api.sambanova.ai/v1", _samba_key(), _samba_model(),
                               system, user, json_mode=json_mode, max_tokens=max_tokens)


# ========================================================================
# Nivel 2 - NVIDIA NIM llama-3.1-405b (405B, 1000 req/mes free)
# ========================================================================

def _nvidia_key() -> str: return os.getenv("NVIDIA_API_KEY", "").strip()
def _nvidia_model() -> str: return os.getenv("NVIDIA_MODEL", "meta/llama-3.1-405b-instruct")

def nvidia_available() -> bool:
    return bool(_nvidia_key())

def _nvidia_call(system: str, user: str, json_mode: bool = False, max_tokens: int = 2000) -> str:
    return _openai_compat_call("https://integrate.api.nvidia.com/v1", _nvidia_key(), _nvidia_model(),
                               system, user, json_mode=json_mode, max_tokens=max_tokens)


# ========================================================================
# Nivel 3 - Cerebras qwen-3-235b (235B)
# ========================================================================

def _cerebras_key() -> str: return os.getenv("CEREBRAS_API_KEY", "").strip()
def _cerebras_model() -> str: return os.getenv("CEREBRAS_MODEL", "qwen-3-235b-a22b-instruct-2507")

def cerebras_available() -> bool:
    return bool(_cerebras_key())

def _cerebras_call(system: str, user: str, json_mode: bool = False, max_tokens: int = 2000) -> str:
    return _openai_compat_call("https://api.cerebras.ai/v1", _cerebras_key(), _cerebras_model(),
                               system, user, json_mode=json_mode, max_tokens=max_tokens)


# ========================================================================
# Nivel 3 - OpenRouter gpt-oss-120b:free
# ========================================================================

def _openrouter_key() -> str: return os.getenv("OPENROUTER_API_KEY", "").strip()
def _openrouter_model() -> str: return os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b:free")

def openrouter_available() -> bool:
    return bool(_openrouter_key())

def _openrouter_call(system: str, user: str, json_mode: bool = False, max_tokens: int = 2000) -> str:
    return _openai_compat_call(
        "https://openrouter.ai/api/v1", _openrouter_key(), _openrouter_model(),
        system, user, json_mode=json_mode, max_tokens=max_tokens,
        extra_headers={
            "HTTP-Referer": "https://ramon.artesbuhomanagement.com",
            "X-Title": "Ramon ARTES BUHO",
        },
    )


# ========================================================================
# Nivel 4 - Groq llama-3.3-70b (70B)
# ========================================================================

def _groq_key() -> str: return os.getenv("GROQ_API_KEY", "").strip()
def _groq_model() -> str: return os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

def groq_available() -> bool:
    return bool(_groq_key())

def _groq_call(system: str, user: str, json_mode: bool = False, max_tokens: int = 2000) -> str:
    return _openai_compat_call("https://api.groq.com/openai/v1", _groq_key(), _groq_model(),
                               system, user, json_mode=json_mode, max_tokens=max_tokens)


# ========================================================================
# Nivel 5 - Mistral mistral-large-latest (123B)
# ========================================================================

def _mistral_key() -> str: return os.getenv("MISTRAL_API_KEY", "").strip()
def _mistral_model() -> str: return os.getenv("MISTRAL_MODEL", "mistral-large-latest")

def mistral_available() -> bool:
    return bool(_mistral_key())

def _mistral_call(system: str, user: str, json_mode: bool = False, max_tokens: int = 2000) -> str:
    return _openai_compat_call("https://api.mistral.ai/v1", _mistral_key(), _mistral_model(),
                               system, user, json_mode=json_mode, max_tokens=max_tokens)


# ========================================================================
# Nivel 6 - Gemini 2.5 Flash (via gemini_brain.py existente)
# ========================================================================

def gemini_available() -> bool:
    return bool(os.getenv("GEMINI_API_KEY", "").strip())

def _gemini_call(system: str, user: str, json_mode: bool = False, max_tokens: int = 2000) -> str:
    from app.integrations.gemini_brain import _call_gemini
    return _call_gemini(system, user, response_json=json_mode, max_tokens=max_tokens, is_email_call=False)


# ========================================================================
# Nivel 7 - PC local via tunel (qwen2.5:14b)
# ========================================================================

def _pc_url() -> str: return os.getenv("PC_OLLAMA_URL", "").rstrip("/")
def _pc_model() -> str: return os.getenv("PC_OLLAMA_MODEL", "qwen2.5:14b")

def pc_available() -> bool:
    url = _pc_url()
    if not url:
        return False
    try:
        r = httpx.get(f"{url}/api/tags", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


# ========================================================================
# Nivel 8 - VPS Ollama (qwen2.5:1.5b)
# ========================================================================

def _vps_ollama_url() -> str: return os.getenv("OLLAMA_URL", "http://ollama:11434").rstrip("/")
def _vps_ollama_model() -> str: return os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")

def vps_available() -> bool:
    url = _vps_ollama_url()
    if not url:
        return False
    try:
        r = httpx.get(f"{url}/api/tags", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


# ========================================================================
# ROUTER PRINCIPAL - cascada potencia descendente con fallback automatico
# ========================================================================

# ========================================================================
# Routing por INTENSIDAD DE TAREA (ahorra tokens usando modelo justo)
#
# TRIVIAL  - etiquetado, si/no, extraccion dato simple. Modelos pequenos.
# NORMAL   - respuestas estandar, resumen, decisiones rutinarias. Medianos.
# ALTA     - redaccion de propuestas, analisis complejo. Grandes.
# CRITICA  - contratos, negociacion, decisiones legales/economicas. Top.
#
# Cada tier prueba los providers en su orden propio. Si uno falla/cooldown,
# baja al siguiente DEL MISMO TIER. Si todos los del tier agotados, escala
# al tier superior (asi siempre se responde sin quedarse sin cerebro).
# ========================================================================

# Wrapper para PC local (Ollama via cloudflare tunnel) en formato OpenAI-compat
def _pc_local_call(system: str, user: str, json_mode: bool = False, max_tokens: int = 2000) -> str:
    return _ollama_generate(_pc_url(), _pc_model(), system, user,
                            json_mode=json_mode, max_tokens=max_tokens)


_ALL_PROVIDERS: dict[str, tuple[Any, Any]] = {
    "pc_local":   (pc_available,         _pc_local_call),
    "sambanova":  (sambanova_available,  _sambanova_call),
    "nvidia":     (nvidia_available,     _nvidia_call),
    "cerebras":   (cerebras_available,   _cerebras_call),
    "mistral":    (mistral_available,    _mistral_call),
    "openrouter": (openrouter_available, _openrouter_call),
    "groq":       (groq_available,       _groq_call),
    "gemini":     (gemini_available,     _gemini_call),
}

# Orden de providers por tier (primero = preferido, ultimo = fallback)
# pc_local SIEMPRE primero: cuesta 0, no tiene cuotas, modelo qwen2.5:14b grande
_TIERS: dict[str, list[str]] = {
    "trivial": ["pc_local", "groq", "mistral", "openrouter", "gemini"],
    "normal":  ["pc_local", "groq", "mistral", "openrouter", "cerebras", "gemini"],
    "alta":    ["pc_local", "cerebras", "nvidia", "mistral", "openrouter", "gemini"],
    "critica": ["pc_local", "sambanova", "nvidia", "cerebras", "mistral"],
}

# Cascada completa por potencia (usada como fallback final si un tier agota)
_LEVELS: list[tuple[str, Any, Any]] = [
    ("pc_local",   pc_available,         _pc_local_call),
    ("sambanova",  sambanova_available,  _sambanova_call),
    ("nvidia",     nvidia_available,     _nvidia_call),
    ("cerebras",   cerebras_available,   _cerebras_call),
    ("mistral",    mistral_available,    _mistral_call),
    ("openrouter", openrouter_available, _openrouter_call),
    ("groq",       groq_available,       _groq_call),
    ("gemini",     gemini_available,     _gemini_call),
]


def _classify_tier(user_prompt: str) -> str:
    """Heuristica de clasificacion por palabras clave y longitud."""
    p = user_prompt.lower()
    # CRITICA - decisiones legales/economicas
    for kw in ("contrato", "firma digital", "factura alta", "negocia", "legal",
               "riesgo ", "cachet fuera", "exclusividad", "abogado"):
        if kw in p:
            return "critica"
    # ALTA - redaccion / analisis
    for kw in ("redacta ", "propuesta", "analiza ", "planifica", "estrategia",
               "resume el contrato", "revisa rider", "presupuesto completo"):
        if kw in p:
            return "alta"
    # TRIVIAL - clasificaciones cortas
    if len(user_prompt) < 200 and any(kw in p for kw in (
        "clasifica", "etiqueta", "si o no", "responde solo", "extrae el",
        "confirma si ", "devuelve un json", "spam", "archivar"
    )):
        return "trivial"
    # Prompts cortos por defecto -> trivial (groq rapido)
    if len(user_prompt) < 400:
        return "trivial"
    # Por defecto
    return "normal"


def _try_providers(provider_names: list[str], system: str, user: str,
                   json_mode: bool, max_tokens: int) -> tuple[str, str] | None:
    """Intenta una lista ordenada de providers cloud. Devuelve (out, name) o None."""
    for name in provider_names:
        pair = _ALL_PROVIDERS.get(name)
        if not pair:
            continue
        avail_fn, call_fn = pair
        if not avail_fn():
            continue
        if _in_cooldown(name):
            continue
        try:
            out = call_fn(system, user, json_mode=json_mode, max_tokens=max_tokens)
            if out:
                return out, name
        except httpx.HTTPStatusError as exc:
            sc = exc.response.status_code
            if sc == 429:
                _mark_cooldown(name)
            else:
                log.info(f"{name} HTTP {sc}: {exc.response.text[:120]}")
            continue
        except Exception as exc:
            log.warning(f"{name} fallo: {exc}")
            continue
    return None


def generate(system: str, user: str, *, json_mode: bool = False,
             max_tokens: int = 2000, tier: str | None = None) -> tuple[str, str]:
    """Genera respuesta usando routing por tier (si se pasa) o cascada completa.

    tier: "trivial" | "normal" | "alta" | "critica" | None
    - Si tier es None: clasifica automaticamente por heuristica del prompt
    - Si tier especificado: usa la lista de providers de ese tier
    - Si todos los providers del tier fallan, escala a cascada completa

    Devuelve (respuesta, cerebro_usado). cerebro_usado incluye el tier:
    "groq@normal", "sambanova@critica", etc.
    """
    # 1. Clasificar si no viene tier explicito
    if tier is None:
        tier = _classify_tier(user)
    if tier not in _TIERS:
        tier = "normal"

    # 2. Intentar providers del tier
    res = _try_providers(_TIERS[tier], system, user, json_mode, max_tokens)
    if res:
        out, name = res
        return out, f"{name}@{tier}"

    # 3. Fallback: cascada completa por potencia (ultima red de seguridad)
    for name, avail_fn, call_fn in _LEVELS:
        if not avail_fn() or _in_cooldown(name):
            continue
        try:
            out = call_fn(system, user, json_mode=json_mode, max_tokens=max_tokens)
            if out:
                return out, f"{name}@fallback"
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                _mark_cooldown(name)
            continue
        except Exception:
            continue

    # 4. PC local
    if pc_available():
        try:
            out = _ollama_generate(_pc_url(), _pc_model(), system, user,
                                   json_mode=json_mode, max_tokens=max_tokens)
            if out:
                return out, f"pc_local@fallback"
        except Exception as exc:
            log.warning(f"PC local fallo: {exc}")

    # 5. VPS Ollama
    if vps_available():
        try:
            out = _ollama_generate(_vps_ollama_url(), _vps_ollama_model(), system, user,
                                   json_mode=json_mode, max_tokens=max_tokens)
            if out:
                return out, f"vps_ollama@fallback"
        except Exception as exc:
            log.warning(f"VPS Ollama fallo: {exc}")

    return "", "error"


def classify_json(system: str, user: str, max_tokens: int = 2500) -> tuple[dict, str]:
    """Version JSON. Devuelve (dict, cerebro)."""
    raw, cerebro = generate(system, user, json_mode=True, max_tokens=max_tokens)
    if not raw:
        return {}, cerebro
    try:
        return json.loads(raw), cerebro
    except json.JSONDecodeError:
        s, e = raw.find("{"), raw.rfind("}")
        if s >= 0 and e > s:
            try:
                return json.loads(raw[s:e + 1]), cerebro
            except Exception:
                pass
        return {"_raw": raw[:500]}, cerebro


def status() -> dict[str, Any]:
    cds = cooldowns_snapshot()
    return {
        "sambanova":  {"rank": 1, "model": _samba_model(),      "configured": sambanova_available(),
                       "cooldown_s": cds.get("sambanova", 0)},
        "nvidia":     {"rank": 2, "model": _nvidia_model(),     "configured": nvidia_available(),
                       "cooldown_s": cds.get("nvidia", 0)},
        "cerebras":   {"rank": 3, "model": _cerebras_model(),   "configured": cerebras_available(),
                       "cooldown_s": cds.get("cerebras", 0)},
        "mistral":    {"rank": 4, "model": _mistral_model(),    "configured": mistral_available(),
                       "cooldown_s": cds.get("mistral", 0)},
        "openrouter": {"rank": 5, "model": _openrouter_model(), "configured": openrouter_available(),
                       "cooldown_s": cds.get("openrouter", 0)},
        "groq":       {"rank": 6, "model": _groq_model(),       "configured": groq_available(),
                       "cooldown_s": cds.get("groq", 0)},
        "gemini":     {"rank": 7, "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                       "configured": gemini_available(), "cooldown_s": cds.get("gemini", 0)},
        "pc_local":   {"rank": 8, "model": _pc_model(),
                       "url": _pc_url() or "(sin configurar)", "available": pc_available()},
        "vps_ollama": {"rank": 9, "model": _vps_ollama_model(),
                       "url": _vps_ollama_url(), "available": vps_available()},
    }
