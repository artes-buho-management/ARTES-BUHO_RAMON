# Ramon - cerebro local en PC
# Arranca Ollama + Cloudflare quick tunnel + actualiza Coolify con la URL nueva
# Diseñado para correr al inicio de sesion Windows.

$ErrorActionPreference = "Continue"
$LogDir = "$env:USERPROFILE\Desktop\CARPETA CODEX\01_PROYECTOS\ARTES-BUHO_RAMON\tmp"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$MainLog = "$LogDir\ramon_brain_pc_$(Get-Date -Format 'yyyy-MM-dd').log"
$CfLog   = "$LogDir\cloudflared_ramon.log"

function Log {
    param($Msg)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts $Msg" | Tee-Object -FilePath $MainLog -Append
}

# Config Coolify
$COOLIFY_URL   = $env:COOLIFY_URL   # ej: http://your-coolify-host:8000
$COOLIFY_TOKEN = $env:COOLIFY_TOKEN # token API Coolify
$RAMON_APP     = $env:COOLIFY_APP_ID # UUID de la app en Coolify

# 1. Asegurar Ollama corriendo con OLLAMA_HOST=0.0.0.0
[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0:11434", "User")
if (-not (Get-Process ollama -ErrorAction SilentlyContinue)) {
    Log "Arrancando Ollama..."
    Start-Process "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 5
} else {
    Log "Ollama ya corriendo"
}

# Verificar Ollama responde
try {
    $tags = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 5
    Log "Ollama OK ($($tags.models.Count) modelos)"
} catch {
    Log "ERROR: Ollama no responde - $_"
    exit 1
}

# 2. Limpiar tunel anterior si existe
Get-Process cloudflared -ErrorAction SilentlyContinue | ForEach-Object {
    Log "Matando cloudflared anterior PID $($_.Id)"
    Stop-Process -Id $_.Id -Force
}
Start-Sleep -Seconds 2

# 3. Lanzar Cloudflare Quick Tunnel
$cf = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb3d8bbwe\cloudflared.exe"
if (-not (Test-Path $cf)) {
    Log "ERROR: cloudflared no encontrado en $cf"
    exit 1
}

Remove-Item -Path $CfLog -Force -ErrorAction SilentlyContinue
$cfProc = Start-Process $cf `
    -ArgumentList "tunnel --url http://localhost:11434" `
    -RedirectStandardError $CfLog `
    -WindowStyle Hidden -PassThru
Log "cloudflared lanzado PID=$($cfProc.Id)"

# 4. Esperar URL en el log
$url = $null
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline -and -not $url) {
    Start-Sleep -Seconds 2
    if (Test-Path $CfLog) {
        $content = Get-Content $CfLog -Raw -ErrorAction SilentlyContinue
        if ($content -match "https://[a-zA-Z0-9-]+\.trycloudflare\.com") {
            $url = $matches[0]
        }
    }
}

if (-not $url) {
    Log "ERROR: no se detecto URL del tunel en 30s"
    exit 1
}
Log "Tunel activo: $url"

# 5. Actualizar PC_OLLAMA_URL en Coolify
$body = @{
    key = "PC_OLLAMA_URL"
    value = $url
    is_preview = $false
    is_literal = $true
} | ConvertTo-Json

try {
    $resp = Invoke-RestMethod -Uri "$COOLIFY_URL/api/v1/applications/$RAMON_APP/envs" `
        -Method Patch `
        -Headers @{ Authorization = "Bearer $COOLIFY_TOKEN" } `
        -ContentType "application/json" `
        -Body $body
    Log "Coolify env PC_OLLAMA_URL actualizado: $url"
} catch {
    # PATCH falla si no existe -> intenta POST
    try {
        $resp = Invoke-RestMethod -Uri "$COOLIFY_URL/api/v1/applications/$RAMON_APP/envs" `
            -Method Post `
            -Headers @{ Authorization = "Bearer $COOLIFY_TOKEN" } `
            -ContentType "application/json" `
            -Body $body
        Log "Coolify env PC_OLLAMA_URL CREADO: $url"
    } catch {
        Log "ERROR Coolify env: $_"
    }
}

# 6. Notificar Telegram
$msgUrl = "https://api.telegram.org/botREPLACE_WITH_TELEGRAM_BOT_TOKEN/sendMessage"
$tgBody = @{
    chat_id = "7749973515"
    text = "Cerebro local Ramon ACTIVO en PC. Modelo qwen2.5:14b. Tunel: $url. PC encendido = max potencia. Si apago el PC, Ramon cae a cascada cloud automatico."
} | ConvertTo-Json -Compress
try {
    Invoke-RestMethod -Uri $msgUrl -Method Post -ContentType "application/json" -Body $tgBody | Out-Null
    Log "Telegram notificado"
} catch {
    Log "Telegram fallo: $_"
}

Log "OK - Cerebro PC operativo. URL=$url"

# 7. Lanzar tambien uvicorn local de Ramon (Ramon vive en PC)
$BackendPath = "$env:USERPROFILE\Desktop\CARPETA CODEX\01_PROYECTOS\ARTES-BUHO_RAMON\backend"
$EnvFile = "$env:USERPROFILE\Desktop\CARPETA CODEX\01_PROYECTOS\ARTES-BUHO_RAMON\.env.ramon.local"

# Matar uvicorn anterior si esta
Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*uvicorn*ramon*" -or $_.CommandLine -like "*app.main:app*"
} | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

# Lanzar Ramon API
$pyArgs = @(
    "-c",
    "from dotenv import load_dotenv; load_dotenv(r'$EnvFile'); import uvicorn; uvicorn.run('app.main:app', host='127.0.0.1', port=8001, log_level='info')"
)
$ramonLog = "$LogDir\ramon_api_$(Get-Date -Format 'yyyy-MM-dd').log"
Push-Location $BackendPath
$ramonProc = Start-Process python -ArgumentList $pyArgs -PassThru -RedirectStandardOutput $ramonLog -RedirectStandardError "$ramonLog.err" -WindowStyle Hidden
Pop-Location
Log "Ramon API lanzado PID=$($ramonProc.Id) - http://127.0.0.1:8001"

# Verificar que arranco
Start-Sleep -Seconds 6
try {
    $h = Invoke-RestMethod -Uri "http://127.0.0.1:8001/health" -TimeoutSec 5
    Log "Ramon API responde: $($h.status) v=$($h.version) env=$($h.environment)"
} catch {
    Log "Ramon API NO responde: $_"
}
