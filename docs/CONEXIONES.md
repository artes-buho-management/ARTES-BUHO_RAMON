# CONEXIONES DE RAMON

Checklist de todo lo que hay que crear / enlazar antes de que Ramon pueda operar.

## Google Workspace (cuenta agencia)

- [ ] Acceso confirmado a **booking@artesbuhomanagement.com**
- [ ] OAuth via hub **ARTES-BUHO_API-GOOGLE**
  - [ ] Scopes: Gmail (read+send), Calendar, Drive, Sheets
- [ ] Carpeta Drive raiz: `/ARTES-BUHO/Ramon/`
  - [ ] Subcarpeta `01_Aprendizaje/` con:
    - `Aprendizaje_Ramon.md`
    - `Aprendizaje_desde_Chat.md`
    - `Aprendizaje_desde_VPS.md`
  - [ ] Subcarpeta `02_Logos_Artistas/`
  - [ ] Subcarpeta `03_Press_Kits/`
  - [ ] Subcarpeta `04_Contratos/`
- [ ] Sheet `CRM_ROSTER_ARTISTAS` con columnas:
  - artista | email | manager | cachet_base | disponibilidad | notas

## Telegram

- [ ] Crear bot con BotFather: **@ramon_artesbuho_bot**
- [ ] Guardar `TELEGRAM_BOT_TOKEN`
- [ ] Guardar `TELEGRAM_CHAT_ID` de Ruben

## IA (cascada en orden de prioridad)

1. **Nivel 1 - PC local** (mejor calidad, coste 0)
   - [ ] Ollama instalado en PC ASUS con `qwen2.5:14b`
   - [ ] Tunel activo (cloudflared / tailscale)
   - [ ] `PC_OLLAMA_URL` apuntando al tunel
2. **Nivel 2 - Gemini 2.5 Flash** (free hasta cuota)
   - [ ] API key en Google AI Studio con proyecto SIN billing
   - [ ] `GEMINI_API_KEY` configurada
3. **Nivel 3 - VPS Ollama** (backup siempre-on)
   - [ ] Contenedor Ollama en VPS con `qwen2.5:1.5b`
   - [ ] `OLLAMA_URL` accesible desde backend

## Holded (factuacion agencia)

- [ ] API key de la cuenta ARTES BUHO
- [ ] Mapeo artista -> cliente Holded

## Firma digital

- [ ] Integracion con hub **ARTES-BUHO_FIRMA-DIGITAL**
- [ ] Plantillas de contrato por tipo de bolo

## Deploy

- [ ] VPS Hostinger + Coolify
- [ ] Dominio: `ramon.artesbuhomanagement.com` + subdominio API
- [ ] Postgres en Coolify
- [ ] Certificados SSL automaticos (Coolify)
