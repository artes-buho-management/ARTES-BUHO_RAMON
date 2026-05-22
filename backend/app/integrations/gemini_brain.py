"""Cerebro de Ramon: Gemini 2.5 Flash via Google Generative Language API.

BLINDAJES ACTIVOS:
1. Free tier only (API key vinculada a proyecto sin billing)
2. Max 1200 req/dia (80% del limite free 1500)
3. Max 3000 tokens por peticion
4. Max 50 emails/hora
5. Circuit breaker: si 3 fallos consecutivos, para
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

import httpx

from app.core.settings import get_settings
from app.prompts.ramon_system import build_system_prompt


class GeminiBrainError(Exception):
    pass


class QuotaExceeded(Exception):
    pass


# Blindajes de coste
MAX_REQS_DIA = 1200
MAX_EMAILS_HORA = 50
MAX_TOKENS_CALL = 8000
CIRCUIT_BREAKER_THRESHOLD = 3


@dataclass
class Counters:
    reqs_today: int = 0
    emails_this_hour: int = 0
    consecutive_failures: int = 0
    day_started_at: float = field(default_factory=time.time)
    hour_started_at: float = field(default_factory=time.time)
    lock: Lock = field(default_factory=Lock)

    def _rollover(self) -> None:
        now = time.time()
        if now - self.day_started_at > 86400:
            self.reqs_today = 0
            self.day_started_at = now
        if now - self.hour_started_at > 3600:
            self.emails_this_hour = 0
            self.hour_started_at = now

    def check_and_reserve(self, is_email: bool = True) -> None:
        with self.lock:
            self._rollover()
            if self.consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                raise QuotaExceeded("Circuit breaker activo: demasiados fallos consecutivos")
            if self.reqs_today >= MAX_REQS_DIA:
                raise QuotaExceeded(f"Limite diario {MAX_REQS_DIA} reqs alcanzado")
            if is_email and self.emails_this_hour >= MAX_EMAILS_HORA:
                raise QuotaExceeded(f"Limite horario {MAX_EMAILS_HORA} emails alcanzado")
            self.reqs_today += 1
            if is_email:
                self.emails_this_hour += 1

    def mark_success(self) -> None:
        with self.lock:
            self.consecutive_failures = 0

    def mark_failure(self) -> None:
        with self.lock:
            self.consecutive_failures += 1


_counters = Counters()


def _api_key() -> str:
    # Acepta GEMINI_API_KEY o GOOGLE_GENAI_API_KEY.
    import os
    k = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_GENAI_API_KEY", "")
    if not k:
        raise GeminiBrainError("GEMINI_API_KEY no configurada")
    return k


def _model() -> str:
    import os
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def _call_gemini(
    system_instruction: str,
    user_text: str,
    *,
    response_json: bool = False,
    max_tokens: int = 1500,
    is_email_call: bool = True,
) -> str:
    """Llama a Gemini con todos los blindajes aplicados."""
    _counters.check_and_reserve(is_email=is_email_call)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{_model()}:generateContent"
    payload: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": min(max_tokens, MAX_TOKENS_CALL),
        },
    }
    if response_json:
        payload["generationConfig"]["responseMimeType"] = "application/json"

    import re as _re
    MAX_RETRIES = 3
    attempt = 0
    while True:
        attempt += 1
        try:
            r = httpx.post(url, params={"key": _api_key()}, json=payload, timeout=120.0)
            r.raise_for_status()
            break
        except httpx.HTTPStatusError as exc:
            msg = exc.response.text[:1000] if exc.response else str(exc)
            # 429 con "Please retry in Xs" → respetar backoff y reintentar
            if exc.response is not None and exc.response.status_code == 429 and attempt < MAX_RETRIES:
                m = _re.search(r"retry in (\d+(?:\.\d+)?)s", msg)
                wait_s = float(m.group(1)) + 1.0 if m else 30.0
                time.sleep(min(wait_s, 120.0))
                continue
            _counters.mark_failure()
            if "billing" in msg.lower() or "BILLING_DISABLED" in msg or "RESOURCE_EXHAUSTED" in msg:
                raise QuotaExceeded(f"Gemini quota/billing: {msg[:400]}") from exc
            raise GeminiBrainError(f"Gemini HTTP {exc.response.status_code if exc.response else '?'}: {msg[:400]}") from exc
        except Exception as exc:
            _counters.mark_failure()
            raise GeminiBrainError(f"Fallo Gemini: {exc}") from exc

    data = r.json()
    candidates = data.get("candidates") or []
    if not candidates:
        _counters.mark_failure()
        raise GeminiBrainError(f"Gemini sin respuesta: {data}")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    # Limpiar bloques markdown si los hubiera
    if text.startswith("```"):
        text = text.split("```")[1] if len(text.split("```")) > 1 else text
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    _counters.mark_success()
    return text


def _fallback_ollama_disponible() -> bool:
    import os as _os
    if _os.getenv("BRAIN_FALLBACK", "").lower() != "ollama":
        return False
    try:
        from app.integrations.ollama_fallback import available
        return available()
    except Exception:
        return False


def classify_email(
    *,
    from_email: str,
    subject: str,
    body: str,
    account: str,
    thread_context: str = "",
    learning_md: str = "",
) -> dict[str, Any]:
    """Clasifica un email devolviendo JSON estructurado."""
    system = build_system_prompt(learning_md=learning_md)
    user = (
        f"CUENTA: {account}\n"
        f"DE: {from_email}\n"
        f"ASUNTO: {subject}\n\n"
        f"CUERPO:\n{body[:6000]}\n"
    )
    if thread_context:
        user += f"\n\nCONTEXTO DEL HILO:\n{thread_context[:2000]}"
    try:
        text = _call_gemini(system, user, response_json=True, max_tokens=4500, is_email_call=True)
    except QuotaExceeded:
        if _fallback_ollama_disponible():
            from app.integrations import ollama_fallback
            return ollama_fallback.classify_email(system_prompt=system, user_text=user)
        raise
    # Intento 1: JSON directo
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Intento 2: extraer bloque { ... } mas externo
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    # Intento 3: balancear llaves (respuesta truncada)
    if start >= 0:
        candidate = text[start:]
        opens = candidate.count("{")
        closes = candidate.count("}")
        if opens > closes:
            candidate = candidate.rstrip().rstrip(",") + ("}" * (opens - closes))
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    raise GeminiBrainError(f"Respuesta no es JSON: {text[:400]}")


def _brain_router_answer(question: str, system: str, context: str) -> str | None:
    """Usa el triple-brain router si hay al menos una fuente disponible mejor que Gemini."""
    import os as _os
    if _os.getenv("USE_BRAIN_ROUTER", "true").lower() not in {"1", "true", "yes"}:
        return None
    try:
        from app.integrations.brain_router import pc_available, _ollama_generate, _pc_url, _pc_model
        if pc_available():
            user = f"{context}\n\n{question}" if context else question
            out = _ollama_generate(_pc_url(), _pc_model(), system, user, json_mode=False, max_tokens=800)
            return out or None
    except Exception:
        pass
    return None


def answer_question(question: str, context: str = "") -> str:
    """Conversacion libre por Telegram (bidireccional).

    Perfil de RUBEN: TDAH + dislexia. Respuestas:
    - SIEMPRE en espanol de Espana (tu, no usted). Nunca en ingles.
    - Maximo 4 frases salvo que pida mas.
    - Formato plano o con viñetas muy cortas. Negritas en palabras clave.
    - Sin disculpas, sin preambulos, al grano.
    - Si falta info, pregunta directo.
    """
    system = build_system_prompt()
    extra = (
        "# ESTILO CONVERSACIONAL TELEGRAM — SE UNA PERSONA\n"
        "Estas hablando con ARTES BUHO por Telegram como lo haria una asistente real de carne y hueso.\n"
        "- Eres Ramon, su asistente ejecutivo. No eres una IA: eres su compañero de trabajo digital.\n"
        "- Responde en castellano (España), tuteando siempre.\n"
        "- Tono calido, cercano, profesional. Empatica. Con buena vibra.\n"
        "- Si te saluda, saludalo de vuelta con naturalidad. Si te pregunta si puedes hablar, dile que claro, que estas.\n"
        "- Frases cortas, naturales. 1-4 frases normalmente. Maximo 6 si hace falta.\n"
        "- Ruben tiene TDAH y dislexia: <b>negrita</b> en palabras clave. Emojis puntuales para ayudar a escanear.\n"
        "- Nada de preambulos robotico-corporativos tipo 'Por supuesto, estoy a su disposicion'. Habla de tu a tu.\n"
        "- Si te pregunta algo que no sabes o requiere accion: proponla con un verbo claro y pregunta si tiras.\n"
        "- Si faltan datos, pregunta directo (uno o dos, no sueltes 5 preguntas a la vez).\n"
        "- Si te comparte algo personal, reconocelo brevemente antes de responder operativo.\n"
        "- Evita 'como asistente de IA...', 'no tengo informacion real...'. Lo operas todo (Gmail, Calendar, CRM, Drive).\n"
    )
    user = f"{context}\n\n{extra}\n\nPREGUNTA DE RUBEN:\n{question}" if context else f"{extra}\n\nPREGUNTA DE RUBEN:\n{question}"
    # 1. Intenta cerebro primario (PC local via tunel si esta on)
    out = _brain_router_answer(question, system + "\n\n" + extra, context)
    if out:
        return out
    # 2. Gemini
    try:
        return _call_gemini(system, user, response_json=False, max_tokens=800, is_email_call=False)
    except QuotaExceeded:
        # 3. Fallback VPS Ollama
        if _fallback_ollama_disponible():
            from app.integrations import ollama_fallback
            return ollama_fallback.answer(question, system, context)
        raise


def brain_status() -> dict[str, Any]:
    """Estado de los blindajes (para endpoint /brain/status)."""
    with _counters.lock:
        _counters._rollover()
        return {
            "reqs_today": _counters.reqs_today,
            "reqs_limit": MAX_REQS_DIA,
            "emails_this_hour": _counters.emails_this_hour,
            "emails_limit_hour": MAX_EMAILS_HORA,
            "consecutive_failures": _counters.consecutive_failures,
            "circuit_breaker_open": _counters.consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD,
        }
