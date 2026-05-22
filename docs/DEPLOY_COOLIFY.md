# DEPLOY DE RAMON EN COOLIFY (VPS Hostinger)

VPS: **REPLACE_WITH_VPS_IP** (mismo que Rocio).
Dominio base: **artesbuhomanagement.com** (Squarespace).

Subdominios que vas a usar:

- `ramon.artesbuhomanagement.com`       -> UI panel
- `api.ramon.artesbuhomanagement.com`   -> Backend FastAPI

---

## PASO 1 - DNS en Squarespace (5 min)

1. Entra en Squarespace -> **Domains** -> `artesbuhomanagement.com` -> **DNS**.
2. Anade **dos registros A** (NO CNAME, porque el root tambien puede estar en Squarespace):

| Tipo | Host                 | Valor            | TTL     |
|------|----------------------|------------------|---------|
| A    | `ramon`              | `REPLACE_WITH_VPS_IP`  | 1 hora  |
| A    | `api.ramon`          | `REPLACE_WITH_VPS_IP`  | 1 hora  |

3. Guarda. La propagacion suele tardar 5-15 min (a veces hasta 1 h).

Comprobacion rapida desde tu PC:

```bash
nslookup ramon.artesbuhomanagement.com
nslookup api.ramon.artesbuhomanagement.com
```

Ambas deben devolver `REPLACE_WITH_VPS_IP`.

---

## PASO 2 - Crear proyecto en Coolify (5 min)

1. Entra en tu panel Coolify.
2. **+ New Project** -> nombre: `ARTES-BUHO_RAMON`.
3. Dentro del proyecto -> **+ Add Resource** -> **Docker Compose Empty** (o "Public Repository" si ya ves el repo privado).
4. Fuente:
   - **Repository**: `https://github.com/rubencoton/artes-buho-ramon`
   - **Branch**: `main`
   - **Build pack**: Docker Compose
   - **Docker Compose file**: `docker-compose.prod.yml`
5. **Environment variables** (pestana Environment). Pegar desde `.env.ramon.local` pero adaptando:
   - `RAMON_ENV=production`
   - Postgres lo monta Coolify -> copiar `DATABASE_URL` que te genera Coolify.
6. **Domains**:
   - Servicio `backend` -> `api.ramon.artesbuhomanagement.com` (puerto 8000)
   - Servicio `ui`      -> `ramon.artesbuhomanagement.com`      (puerto 80)
   - Coolify saca cert Let's Encrypt automatico.
7. **Deploy**.

---

## PASO 3 - Verificar (2 min)

```bash
curl https://api.ramon.artesbuhomanagement.com/health
# -> {"status":"ok","assistant":"ramon","brand":"ARTES BUHO"}

curl https://api.ramon.artesbuhomanagement.com/brain/status
# -> estado de la cascada IA (pc_local / gemini / vps_ollama)
```

Abre `https://ramon.artesbuhomanagement.com` en el navegador -> ves el panel.

---

## PASO 4 - Bot Telegram 24/7

1. En BotFather: `/newbot` -> nombre `Ramon ARTES BUHO` -> usuario `ramon_artesbuho_bot`.
2. Copia el token -> en Coolify anade var `TELEGRAM_BOT_TOKEN`.
3. Abre el bot en Telegram, pulsa `/start`.
4. Desde tu PC:
   ```bash
   curl https://api.ramon.artesbuhomanagement.com/telegram/detect-chat-id
   ```
5. Copia el `chat_id` devuelto -> anade `TELEGRAM_CHAT_ID` en Coolify -> redeploy.

Desde aqui el bot queda **24/7** en el VPS via APScheduler.

---

## PASO 5 - Cascada IA

Orden que queda activo en produccion:

1. **PC local** (qwen2.5:14b) -> si tu PC tiene tunel cloudflared expuesto a `PC_OLLAMA_URL`.
2. **Gemini 2.5 Flash** -> si hay `GEMINI_API_KEY`.
3. **VPS Ollama** (qwen2.5:1.5b) -> contenedor ya existente en tu VPS (el mismo que usa Rocio).

Para el nivel 3 reutilizamos el Ollama del VPS. En Coolify:

- Si el Ollama de Rocio esta en la misma red Docker -> `OLLAMA_URL=http://ollama:11434`.
- Si esta en otro proyecto Coolify -> usar el hostname interno que te da Coolify.

---

## Puertos en local (referencia)

Ramon usa puertos distintos a Rocio para poder correr los dos a la vez en el PC:

| Servicio   | Rocio  | Ramon  |
|------------|--------|--------|
| Postgres   | 5432   | 5433   |
| Backend    | 8000   | 8001   |
| UI         | 3000   | 3001   |

En produccion (Coolify) esto da igual: cada contenedor en su red.
