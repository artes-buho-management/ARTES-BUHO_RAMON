# RAMON - Asistente Ejecutivo de ARTES BUHO

**Ultima actualizacion**: 2026-04-20
**Marca**: ARTES BUHO Management
**Contraparte gemela**: [ROCIO_SECRETARIA](../ROCIO_SECRETARIA) (marca RUBEN COTON)

---

## Que es RAMON

Asistente ejecutivo autonomo de **ARTES BUHO Management**.

Misma filosofia que Rocio (Protocolo v4: autonomia, semaforo de decisiones,
aprendizaje continuo, dos instancias Consultora-Ejecutiva) pero al servicio
de la **agencia** (multiples artistas, promotores, contratos) en lugar de
un solo artista.

> Rocio libera a **Ruben** del trabajo administrativo.
> Ramon libera a **la agencia** del trabajo operativo sobre toda la cartera.

## Diferencias clave frente a Rocio

| Area                  | ROCIO (RUBEN COTON)                          | RAMON (ARTES BUHO)                                        |
|-----------------------|----------------------------------------------|-----------------------------------------------------------|
| Cuenta Google         | REPLACE_WITH_OWNER_EMAIL                       | **booking@artesbuhomanagement.com**                       |
| Hub OAuth             | RUBEN-COTON_API-GOOGLE                       | **ARTES-BUHO_API-GOOGLE**                                 |
| CRM                   | Sheet unico de Ruben                         | **CRM multi-artista** (roster ARTES BUHO)                 |
| Drive raiz            | `/Rocio/...`                                 | **`/ARTES-BUHO/...`**                                     |
| Telegram bot          | @rocio_rubencoton_bot                        | **@ramon_artesbuho_bot** (por crear)                      |
| Dominio               | rocio.rubencoton.com                         | **ramon.artesbuhomanagement.com**                         |
| Firmas email          | Rocio (booking Ruben) / RUBEN COTON          | **Ramon (booking agencia) / ARTES BUHO Management**       |
| Alcance bookings      | Bodas + profesionales RUBEN COTON            | **Roster completo de artistas + promotores + distritos**  |
| Contratos             | Solo Ruben                                   | **Firma digital por artista** (FIRMA-DIGITAL hub)         |
| Integracion Holded    | Factuacion Ruben                             | **Factuacion agencia** (multi-cliente)                    |
| Fuentes de leads      | Palau Alameda, Real Madrid, promotores fijos | **DISTRITOS-MADRID, BUSCA-CONTACTOS, promotores libres**  |

## Filosofia heredada (Protocolo v4)

1. **Autonomia por defecto.** Ramon decide y ejecuta. Solo escala cuando
   el semaforo marca rojo.
2. **Semaforo de decisiones.**
   - Verde -> ejecuta sin preguntar.
   - Amarillo -> ejecuta y notifica.
   - Rojo -> bloquea y espera validacion humana.
3. **Dos Ramones.**
   - **Consultora** (Claude Code): disena flujos, prompts, aprendizaje.
   - **Ejecutiva** (VPS Coolify): corre 24/7, responde emails, agenda.
4. **Aprendizaje continuo.** Archivos en Drive:
   - `Aprendizaje_Ramon.md` (maestro)
   - `Aprendizaje_desde_Chat.md` (Consultora -> Ejecutiva)
   - `Aprendizaje_desde_VPS.md` (Ejecutiva -> Consultora)
5. **No inventar datos.** Si falta contexto, preguntar o marcar PENDIENTE.
6. **Humanizacion.** Todo email sale con tono humano, no robotico.

## Arquitectura

```
ramon.artesbuhomanagement.com          -> UI (panel web agencia)
api.ramon.artesbuhomanagement.com      -> Backend FastAPI
                                       -> PostgreSQL (Coolify)
                                       -> Hub ARTES-BUHO_API-GOOGLE
                                          (Gmail + Calendar + Drive + Sheets)
                                       -> Gemini 2.5 Flash (brain)
                                       -> Telegram bot @ramon_artesbuho_bot
                                       -> Holded (facturacion agencia)
                                       -> FIRMA-DIGITAL (contratos artistas)
```

## Stack

- **Backend**: FastAPI + SQLAlchemy + Alembic + APScheduler
- **DB**: PostgreSQL 18
- **UI**: HTML + Tailwind (v0), migrable a Next.js
- **Brain**: Gemini 2.5 Flash (fallback Ollama local)
- **Deploy**: Coolify en VPS Hostinger
- **OAuth Google**: via hub `ARTES-BUHO_API-GOOGLE` (no duplicar)

## Estructura del repo

```
ARTES-BUHO_RAMON/
├── README.md
├── docker-compose.yml
├── .env.ramon.example         # plantilla. El real = .env.ramon.local (gitignored)
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── core/              # settings, database, scheduler, horario, availability
│       ├── integrations/      # gmail, calendar, drive, sheets_crm, holded, telegram, firma_digital
│       ├── decisions/         # semaforo (verde/amarillo/rojo)
│       ├── prompts/           # plantillas por tipo de email y artista
│       ├── tasks/             # jobs programados
│       ├── learning/          # sync aprendizaje con Drive
│       └── assets/            # logos y press kits por artista
├── ui/
│   ├── Dockerfile
│   └── index.html
├── scripts/
│   ├── sync_consultora.py     # pull/push aprendizaje
│   └── generar_manual_ramon.py
└── docs/
    ├── SETUP.md
    ├── PROTOCOLO_V4_RAMON.md
    └── CONEXIONES.md          # detalle de claves, folders, sheets
```

## Variables de entorno obligatorias

Ver `.env.ramon.example`. En `.env.ramon.local` (gitignored):

- `GEMINI_API_KEY`
- `GOOGLE_OAUTH_*` -> desde hub ARTES-BUHO_API-GOOGLE
- `TELEGRAM_BOT_TOKEN` -> @ramon_artesbuho_bot (por crear)
- `TELEGRAM_CHAT_ID` -> chat de Ruben
- `DRIVE_FOLDER_RAMON` -> raiz `/ARTES-BUHO/Ramon/` (por crear)
- `CRM_ROSTER_SHEET_ID` -> hoja con roster de artistas (por crear)
- `PROMOTORES_FOLDER_ID` -> materiales promotores
- `LOGOS_ARTISTAS_FOLDER_ID` -> logos por artista
- `HOLDED_API_KEY` -> cuenta agencia
- `FIRMA_DIGITAL_URL` -> endpoint hub ARTES-BUHO_FIRMA-DIGITAL

## Desarrollo local

```bash
cd "C:\Users\elrub\Desktop\CARPETA CODEX\01_PROYECTOS\ARTES-BUHO_RAMON"
copy .env.ramon.example .env.ramon.local
# editar .env.ramon.local con claves reales
docker compose up -d
```

## Endpoints base

- `GET  /health`             estado del servicio
- `GET  /oauth/callback`     callback OAuth Google
- `POST /classify`           clasificar email entrante (semaforo)
- `POST /respond`            generar respuesta con tono humano
- `POST /book`               agendar videollamada
- `GET  /artists`            roster de ARTES BUHO
- `POST /contracts/sign`     lanzar contrato a firma digital

## Flujo Git en este PC

Push directo puede estar bloqueado. Usar siempre:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File "C:\Users\elrub\Desktop\CARPETA CODEX\03_SCRIPTS_UTILIDAD\publicar_desde_local.ps1" `
  -RepoPath "C:\Users\elrub\Desktop\CARPETA CODEX\01_PROYECTOS\ARTES-BUHO_RAMON" `
  -Remote origin -Branch main
```

## Estado

- HECHO: scaffold de carpetas y README con filosofia adaptada.
- HECHO: docker-compose base.
- HECHO: repo privado `rubencoton/artes-buho-ramon`.
- PENDIENTE: crear bot Telegram @ramon_artesbuho_bot.
- PENDIENTE: crear carpeta Drive `/ARTES-BUHO/Ramon/`.
- PENDIENTE: crear Sheet roster de artistas.
- PENDIENTE: portar modulos de `integrations/` adaptando a cuentas ARTES BUHO.
- PENDIENTE: redactar `PROTOCOLO_V4_RAMON.md` y `CONEXIONES.md`.
- PENDIENTE: deploy en Coolify bajo `ramon.artesbuhomanagement.com`.

## Siguiente paso

1. Crear bot Telegram @ramon_artesbuho_bot.
2. Crear Drive root `/ARTES-BUHO/Ramon/` y Sheet roster.
3. Empezar a portar `integrations/gmail.py` apuntando a booking@artesbuhomanagement.com.
