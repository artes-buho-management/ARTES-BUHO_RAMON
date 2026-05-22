# DNS en Squarespace - artesbuhomanagement.com

## Registros a anadir

Panel Squarespace -> Domains -> `artesbuhomanagement.com` -> **DNS Settings**
-> seccion **Custom Records** -> **Add Record**.

| # | Type | Host        | Data            | TTL    |
|---|------|-------------|-----------------|--------|
| 1 | A    | `ramon`     | `REPLACE_WITH_VPS_IP` | 1 Hour |
| 2 | A    | `api.ramon` | `REPLACE_WITH_VPS_IP` | 1 Hour |

**IMPORTANTE**:
- `Host` es solo el subdominio (sin el dominio principal).
- Squarespace anade el dominio automaticamente.
- No borres registros existentes (MX de Gmail, TXT de verificacion, etc).

## Verificar propagacion

Desde PowerShell o bash:

```bash
nslookup ramon.artesbuhomanagement.com 8.8.8.8
nslookup api.ramon.artesbuhomanagement.com 8.8.8.8
```

Respuesta esperada: `Address: REPLACE_WITH_VPS_IP`.

Tiempo tipico: 5-15 min. Maximo: 1 hora.

## Posibles problemas

- **"Record already exists"**: revisa si ya hay un CNAME para ese subdominio
  y borralo antes de anadir el A.
- **"Invalid host"**: no pongas `ramon.artesbuhomanagement.com` en Host,
  solo `ramon`.
- **SSL no se genera**: Coolify necesita que el DNS ya resuelva al VPS
  antes de pedir el certificado. Si fallo la primera vez, espera 10 min y
  dale a **Redeploy** en Coolify.
