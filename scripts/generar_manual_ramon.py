"""Genera RAMON_MANUAL.pdf en el Desktop."""
import os
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors

ROJO = colors.HexColor("#D02E2B")
BLANCO = colors.white
NEGRO = colors.black

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='H1RC', parent=styles['Heading1'], textColor=ROJO, fontSize=22, spaceAfter=12))
styles.add(ParagraphStyle(name='H2RC', parent=styles['Heading2'], textColor=ROJO, fontSize=15, spaceAfter=8, spaceBefore=12))
styles.add(ParagraphStyle(name='H3RC', parent=styles['Heading3'], textColor=NEGRO, fontSize=12, spaceAfter=4, spaceBefore=8))
styles.add(ParagraphStyle(name='Body2', parent=styles['BodyText'], fontSize=10, leading=14, spaceAfter=6))

out = r"C:/Users/elrub/Desktop/RAMON_MANUAL.pdf"
doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
story = []

def header_table(data, colw, head_row=True):
    t = Table(data, colWidths=colw)
    ts = [
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]
    if head_row:
        ts += [
            ('BACKGROUND', (0,0), (-1,0), ROJO),
            ('TEXTCOLOR', (0,0), (-1,0), BLANCO),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ]
    t.setStyle(TableStyle(ts))
    return t

story.append(Paragraph("RAMON - Manual de uso", styles['H1RC']))
story.append(Paragraph("Asistente Ejecutivo de ARTES BUHO Management - v1.0 - 2026-04-20", styles['Body2']))
story.append(Spacer(1, 8))

# Estado
story.append(Paragraph("ESTADO ACTUAL", styles['H2RC']))
story.append(header_table([
    ["Servicio", "URL / Info", "Estado"],
    ["API", "api.ramon.artesbuhomanagement.com", "OK"],
    ["Panel", "ramon.artesbuhomanagement.com", "OK"],
    ["Bot Telegram", "@ramon_artesbuho_bot", "24/7"],
    ["Cuenta Google", "booking@artesbuhomanagement.com", "Gmail+Cal+Drive"],
    ["Drive raiz", "/ARTES-BUHO/Ramon/ (shared)", "OK"],
    ["Scheduler", "21 jobs corriendo", "OK"],
    ["Firma email", "Logo ARTES BUHO + foto Ramon", "OK"],
], [4*cm, 9*cm, 3.5*cm]))

# Cascada IA
story.append(Paragraph("CASCADA IA (9 niveles)", styles['H2RC']))
story.append(Paragraph("Ordenada por potencia descendente. Si un nivel falla o agota cuota (429), salta al siguiente automaticamente y marca cooldown para no reintentar.", styles['Body2']))
story.append(header_table([
    ["#", "Provider", "Modelo", "Params"],
    ["1", "SambaNova", "DeepSeek-V3.2", "685B"],
    ["2", "NVIDIA NIM", "llama-3.1-405b-instruct", "405B"],
    ["3", "Cerebras", "qwen-3-235b-a22b-instruct", "235B"],
    ["4", "Mistral", "mistral-large-latest", "123B"],
    ["5", "OpenRouter", "gpt-oss-120b:free", "120B"],
    ["6", "Groq", "llama-3.3-70b-versatile", "70B"],
    ["7", "Gemini", "gemini-2.5-flash", "-"],
    ["8", "PC local", "qwen2.5:14b", "14B"],
    ["9", "VPS Ollama", "qwen2.5:1.5b", "1.5B"],
], [1*cm, 3.5*cm, 8.5*cm, 3.5*cm]))

# Tiers
story.append(Paragraph("4 TIERS por intensidad de tarea", styles['H2RC']))
story.append(Paragraph("Ramon clasifica automaticamente cada peticion y usa un rango de IAs segun complejidad. Asi los modelos top (SambaNova, NVIDIA) se reservan para lo importante.", styles['Body2']))
story.append(header_table([
    ["Tier", "Cuando", "IAs que usa"],
    ["TRIVIAL", "Etiquetar email, si/no, extraer dato, <200 chars", "Groq - Mistral - OpenRouter - Gemini"],
    ["NORMAL", "Respuesta estandar, resumen corto, decision rutinaria", "Groq - Mistral - OpenRouter - Cerebras - Gemini"],
    ["ALTA", "Redactar propuesta, analizar, planificar estrategia", "Cerebras - NVIDIA - Mistral - OpenRouter"],
    ["CRITICA", "Contrato, negociacion, legal, firma digital, exclusividad", "SambaNova - NVIDIA - Cerebras - Mistral"],
], [2.5*cm, 6.5*cm, 7.5*cm]))

story.append(Paragraph("Keywords que disparan cada tier:", styles['H3RC']))
story.append(Paragraph("- CRITICA: contrato, firma digital, factura alta, negocia, legal, riesgo, cachet fuera, exclusividad, abogado", styles['Body2']))
story.append(Paragraph("- ALTA: redacta, propuesta, analiza, planifica, estrategia, resume el contrato, revisa rider, presupuesto completo", styles['Body2']))
story.append(Paragraph("- TRIVIAL (+ <200 chars): clasifica, etiqueta, si o no, responde solo, extrae el, confirma si, devuelve un json, spam, archivar", styles['Body2']))
story.append(Paragraph("- NORMAL: default", styles['Body2']))

story.append(PageBreak())

# Entrenamientos
story.append(Paragraph("ENTRENAMIENTOS AUTOMATICOS", styles['H2RC']))
story.append(Paragraph("Ramon aprende solo, cada cierto tiempo, de los archivos que dejas en la carpeta compartida de Drive (/ARTES-BUHO/Ramon/01_Aprendizaje/).", styles['Body2']))
story.append(header_table([
    ["Job", "Frecuencia", "Que hace"],
    ["ingesta_tick", "cada 30 min", "Lee Drive compartido para nuevos archivos de conocimiento"],
    ["entrenamiento_continuo", "cada 60 min", "Consolidar decisiones recientes"],
    ["rutina_diaria", "08:00", "Informe del dia a Telegram"],
    ["entrenamiento_profundo_pc", "11:00", "Entrena con PC local (qwen 14B) si tunel activo"],
    ["revisar_spam", "diario 14:08", "Revisa SPAM y recupera falsos positivos"],
    ["auditor_etiquetas", "horario 15:08", "Audita etiquetas Gmail y aprende patrones"],
    ["observador_drive_facturas", "horario 16:08", "Detecta facturas nuevas en Drive"],
    ["holded_refresh", "horario 18:08", "Refresca cache de Holded"],
    ["informe_semanal", "jueves 08:00", "Resumen semana a Telegram + Drive"],
    ["entrenamiento_semanal", "jueves 19:00", "Aprendizaje profundo consolidado"],
    ["holded_historico", "domingo 04:00", "Re-sincroniza Holded historico"],
    ["escaneo_semanal", "lunes 08:05", "Escaneo completo del ecosistema"],
    ["consolidacion_mensual", "dia 1 - 07:30", "Consolida todo el mes en Aprendizaje_Ramon.md"],
], [4.5*cm, 2.8*cm, 9*cm]))

# Como usar
story.append(Paragraph("COMO USAR RAMON", styles['H2RC']))

story.append(Paragraph("1. Desde Telegram", styles['H3RC']))
story.append(Paragraph("Abre <b>@ramon_artesbuho_bot</b> y escribe lo que necesites. Ramon clasifica la intensidad y te responde usando el cerebro optimo.", styles['Body2']))

story.append(Paragraph("2. Desde este chat Claude Code", styles['H3RC']))
story.append(Paragraph("Dile a Claude Code lo que quieras que Ramon aprenda o cambie. Se sincroniza via Drive compartido (carpeta 01_Aprendizaje).", styles['Body2']))

story.append(Paragraph("3. API directa", styles['H3RC']))
story.append(Paragraph("POST api.ramon.artesbuhomanagement.com/brain/cascade/ask con body {'question':'...','tier':'alta'} (tier opcional, se auto-clasifica si lo omites).", styles['Body2']))

story.append(Paragraph("4. Endpoints utiles", styles['H3RC']))
story.append(header_table([
    ["Endpoint", "Funcion"],
    ["GET /health", "Esta vivo?"],
    ["GET /brain/cascade", "Estado cascada + cooldowns"],
    ["GET /brain/tiers", "Configuracion de los 4 tiers"],
    ["POST /brain/cascade/ask", "Preguntar (con o sin tier)"],
    ["GET /gmail/profile", "Perfil Gmail booking@"],
    ["GET /calendar/upcoming", "Proximos eventos"],
    ["GET /scheduler/status", "21 jobs programados"],
    ["POST /drive/init-structure", "Reinicia estructura Drive"],
    ["POST /tareas/rutina-diaria?force=true", "Forzar informe diario ahora"],
], [6.5*cm, 10*cm]))

# Reparacion
story.append(Paragraph("SI ALGO FALLA", styles['H2RC']))
story.append(Paragraph("<b>Bot no responde:</b> revisa /health. Si HTTP 200 pero bot mudo, revisa /scheduler/status.", styles['Body2']))
story.append(Paragraph("<b>Todas las IAs caen:</b> ver /brain/cascade. Si todas con cooldown: espera 5-60 min. Hay 9 niveles, imposible caer todas salvo caida total de internet del VPS.", styles['Body2']))
story.append(Paragraph("<b>Redeploy:</b> Coolify (REPLACE_WITH_COOLIFY_HOST:PORT) - proyecto ARTES-BUHO_RAMON - ramon-api - Redeploy.", styles['Body2']))
story.append(Paragraph("<b>Logs:</b> Coolify - ramon-api - Logs.", styles['Body2']))
story.append(Paragraph("<b>Rebuild completo:</b> git push en C:/Users/elrub/Desktop/CARPETA CODEX/01_PROYECTOS/ARTES-BUHO_RAMON - Coolify detecta el push y despliega solo.", styles['Body2']))

# Footer
story.append(Spacer(1, 20))
story.append(Paragraph("<i>Generado por Claude Code - 2026-04-20 - Repo: rubencoton/artes-buho-ramon (privado)</i>", styles['Body2']))

doc.build(story)
print(f"PDF creado: {out}")
print(f"Tamano: {os.path.getsize(out)} bytes")
