"""Genera un manual de Ramon en lenguaje simple, para enviar via Telegram."""
import os
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors

ROJO = colors.HexColor("#D02E2B")
AMA = colors.HexColor("#F4C430")
BLANCO = colors.white
NEGRO = colors.black
GRIS = colors.HexColor("#F5F5F5")

st = getSampleStyleSheet()
st.add(ParagraphStyle(name='Titulo', parent=st['Title'], textColor=ROJO, fontSize=26, spaceAfter=6, alignment=1))
st.add(ParagraphStyle(name='Sub', parent=st['BodyText'], textColor=NEGRO, fontSize=12, alignment=1, spaceAfter=20))
st.add(ParagraphStyle(name='H1', parent=st['Heading1'], textColor=BLANCO, backColor=ROJO, fontSize=16,
                      spaceBefore=14, spaceAfter=10, leftIndent=6, rightIndent=6, borderPadding=6))
st.add(ParagraphStyle(name='H2', parent=st['Heading2'], textColor=ROJO, fontSize=13, spaceBefore=10, spaceAfter=5))
st.add(ParagraphStyle(name='Body2', parent=st['BodyText'], fontSize=10.5, leading=15, spaceAfter=6))
st.add(ParagraphStyle(name='BulletRC', parent=st['BodyText'], fontSize=10.5, leading=14,
                      leftIndent=14, firstLineIndent=-10, spaceAfter=3))
st.add(ParagraphStyle(name='Box', parent=st['BodyText'], fontSize=10.5, leading=15,
                      backColor=GRIS, leftIndent=8, rightIndent=8, borderPadding=8, spaceAfter=8))

out = r"C:/Users/elrub/Desktop/RAMON_MANUAL_SIMPLE.pdf"
doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
s = []

def h1(text): s.append(Paragraph(text, st['H1']))
def h2(text): s.append(Paragraph(text, st['H2']))
def p(text): s.append(Paragraph(text, st['Body2']))
def b(text): s.append(Paragraph("&bull; " + text, st['BulletRC']))
def box(text): s.append(Paragraph(text, st['Box']))
def sp(h=8): s.append(Spacer(1, h))

# Portada
s.append(Paragraph("MANUAL DE RAMON", st['Titulo']))
s.append(Paragraph("Tu asistente ejecutivo digital de ARTES BUHO", st['Sub']))
s.append(Paragraph("<i>Explicado para que cualquiera lo entienda</i>", st['Sub']))
sp(20)

# Portada resumen
box("<b>En una frase:</b> Ramon es un robot que vive en una nube de internet y trabaja 24 horas al dia gestionando los correos, la agenda y el papeleo de la agencia ARTES BUHO, como si fuera un empleado mas pero sin dormir.")

# ---- ¿Qué es Ramon? ----
h1("1. ¿Que es Ramon exactamente?")
p("Ramon es un <b>asistente virtual con inteligencia artificial</b> creado para ARTES BUHO Management. Funciona como una persona del equipo:")
b("<b>Escucha</b> los correos que llegan al buzon de la agencia (booking@artesbuhomanagement.com).")
b("<b>Clasifica</b> cada mensaje: si es un humano pidiendo algo, si es spam, si es una factura, etc.")
b("<b>Responde</b> los mas sencillos el solito (con tono profesional y firma).")
b("<b>Avisa</b> por Telegram cuando algo necesita decision humana.")
b("<b>Archiva</b> facturas, contratos y documentos en Drive ordenados por carpetas.")
b("<b>Aprende</b> todos los dias de lo que le dejas en su carpeta de Drive compartida.")

sp()
box('<b>Importante:</b> Ramon NO actua por su cuenta en cosas arriesgadas. Si algo es delicado (un contrato, un cachet fuera de lo normal), te pregunta antes por Telegram.')

# ---- ¿Dónde vive? ----
h1("2. ¿Donde vive Ramon?")
p("Ramon vive en un servidor que tenemos alquilado en internet (lo que se llama un VPS). Este servidor esta encendido 24 horas al dia, 365 dias al ano. Asi que Ramon nunca descansa.")
p("Tu no necesitas tener el ordenador encendido para que Ramon trabaje. El vive fuera, en una 'caja' de internet.")

t = Table([
    ["Servicio", "Donde esta"],
    ["API (cerebro de Ramon)", "api.ramon.artesbuhomanagement.com"],
    ["Panel web", "ramon.artesbuhomanagement.com"],
    ["Bot de Telegram", "@ramon_artesbuho_bot"],
    ["Correo que gestiona", "booking@artesbuhomanagement.com"],
    ["Carpeta de Drive compartida", "/ARTES-BUHO/Ramon/"],
], colWidths=[5.5*cm, 10.5*cm])
t.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), ROJO),
    ('TEXTCOLOR', (0,0), (-1,0), BLANCO),
    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
    ('FONTSIZE', (0,0), (-1,-1), 10),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('TOPPADDING', (0,0), (-1,-1), 5),
    ('BOTTOMPADDING', (0,0), (-1,-1), 5),
]))
s.append(t)

# ---- ¿Cómo piensa? ----
h1("3. ¿Como piensa Ramon? (lo mas importante)")
p("Ramon no usa una unica inteligencia artificial. Usa <b>9 cerebros distintos en cascada</b>. Esto es como si un empleado tuviera a su disposicion 9 asesores, de mayor a menor potencia, y siempre pregunta al mas potente disponible.")
sp()
p("Cuando uno esta ocupado o ha gastado su cuota gratis, baja al siguiente. Asi nunca se queda sin cerebro.")

p("<b>De mas potente a menos:</b>")
t = Table([
    ["Orden", "Cerebro", "Potencia"],
    ["1", "SambaNova DeepSeek-V3.2", "Enorme (685.000 millones de neuronas)"],
    ["2", "NVIDIA Llama 405B", "Muy grande (405.000 millones)"],
    ["3", "Cerebras Qwen 235B", "Grande (235.000 millones)"],
    ["4", "Mistral Large", "Alta (123.000 millones)"],
    ["5", "OpenRouter GPT-OSS 120B", "Alta (120.000 millones)"],
    ["6", "Groq Llama 70B", "Rapida (70.000 millones)"],
    ["7", "Google Gemini 2.5 Flash", "Buena generalista"],
    ["8", "PC local en tu casa (opcional)", "Solo si tu PC esta encendido"],
    ["9", "Cerebro local del VPS", "Pequeno, de emergencia"],
], colWidths=[1.2*cm, 6.5*cm, 8.3*cm])
t.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), ROJO),
    ('TEXTCOLOR', (0,0), (-1,0), BLANCO),
    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
    ('FONTSIZE', (0,0), (-1,-1), 9.5),
    ('ALIGN', (0,0), (0,-1), 'CENTER'),
]))
s.append(t)

s.append(PageBreak())

# ---- Tiers ----
h1("4. Ramon es inteligente ahorrando")
p("Ramon no usa el cerebro mas potente para todo (eso gastaria los tokens gratis en segundos). Usa un cerebro mas o menos potente segun el tipo de tarea.")
sp()

t = Table([
    ["Tipo de tarea", "Ejemplo real", "Cerebro que usa"],
    ["TRIVIAL", "Clasificar un spam, extraer un dato, si o no", "Pequenos y rapidos"],
    ["NORMAL", "Responder un email estandar, resumen corto", "Medianos"],
    ["ALTA", "Redactar una propuesta, analizar algo", "Grandes"],
    ["CRITICA", "Leer un contrato, negociar, tema legal", "Los mas potentes"],
], colWidths=[2.5*cm, 7*cm, 6.5*cm])
t.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), ROJO),
    ('TEXTCOLOR', (0,0), (-1,0), BLANCO),
    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
    ('FONTSIZE', (0,0), (-1,-1), 10),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
]))
s.append(t)

sp()
box("<b>Detecta solo el tipo de tarea</b> leyendo palabras clave: si ve 'contrato' o 'exclusividad' lo considera CRITICA y usa los cerebros mas potentes. Si ve 'etiqueta esto como spam' usa un cerebro pequeno. Asi optimiza los tokens gratis.")

# ---- Cómo hablarle ----
h1("5. Como hablar con Ramon")

h2("Opcion A: por Telegram (la mas facil)")
p("Abre en tu movil el chat con <b>@ramon_artesbuho_bot</b>. Escribele como le hablarias a un empleado. Ramon responde en castellano, breve, como un secretario profesional.")
p("Ejemplos:")
b('"Ramon, resumeme los correos pendientes de hoy"')
b('"Ramon, agendame una llamada con Juan el martes a las 10"')
b('"Ramon, ¿alguien me ha escrito esta semana sobre el festival de Valencia?"')
b('"Ramon, archiva el correo de Telefonica como OTROS"')

h2("Opcion B: dejarle archivos en Drive")
p("Cualquier documento que dejes en la carpeta compartida <b>/ARTES-BUHO/Ramon/01_Aprendizaje/</b> lo va a leer, a entender y a usar como conocimiento para sus decisiones. Perfecto para:")
b("Protocolos de la agencia")
b("Lista de artistas y cachets aprobados")
b("Decisiones importantes que quieres que recuerde")
b("Documentos sobre clientes habituales")

h2("Opcion C: desde Claude Code (el chat de programacion)")
p("Si estas en este chat de programacion, puedes pedirle a Claude que le pida a Ramon cambios, que revise su estado, o que le anada funciones. Todo se sincroniza via Drive.")

# ---- Qué hace automáticamente ----
h1("6. ¿Que hace Ramon sin que le pidas nada?")

p("Ramon tiene varios 'trabajos' programados que ejecuta solo a ciertas horas:")

t = Table([
    ["Cuando", "Que hace"],
    ["Cada 10 minutos", "Revisa correos nuevos. Si es humano que espera respuesta, lo reenvia a contratacion@artesbuho.com y booking@artesbuho.com. Si es spam/autoreply/rebote, lo archiva solo."],
    ["Cada 30 minutos", "Lee nuevos archivos de la carpeta Drive compartida. Aprende de ellos."],
    ["Cada 2 horas", "Ordena archivos sueltos de la 'Mi Unidad' de booking@ en subcarpetas (contratos, facturas, etc) usando IA para clasificar."],
    ["Cada dia a las 8:00", "Te manda por Telegram un informe con los correos pendientes, eventos del dia y cosas importantes."],
    ["Cada dia a las 14:00", "Hace copia de seguridad del CRM principal a su carpeta de backups."],
    ["Los jueves a las 8:00", "Resumen semanal."],
    ["Los jueves a las 19:00", "Aprendizaje profundo consolidado."],
    ["El dia 1 de cada mes", "Consolida todo el mes en un solo documento de aprendizaje."],
], colWidths=[3.8*cm, 12.2*cm])
t.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), ROJO),
    ('TEXTCOLOR', (0,0), (-1,0), BLANCO),
    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
    ('FONTSIZE', (0,0), (-1,-1), 9.5),
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ('TOPPADDING', (0,0), (-1,-1), 4),
    ('BOTTOMPADDING', (0,0), (-1,-1), 4),
]))
s.append(t)

s.append(PageBreak())

# ---- Preguntas comunes ----
h1("7. Preguntas comunes")

h2("¿Puede Ramon contestar a un cliente sin preguntarme?")
p("Si, pero solo cosas rutinarias: pedir datos, confirmar recepcion, rider, press kit. Si es una oferta economica, una negociacion o un contrato, te avisa antes por Telegram con un aviso en rojo.")

h2("¿Ramon me va a spamear en Telegram?")
p("No. Solo te escribe en:")
b("Amarillo: info importante pero no urgente (ha cerrado una agenda, ha enviado un press kit).")
b("Rojo: necesita tu decision ya (contrato, cachet inusual, cliente VIP enfadado).")
b("Verde: nunca te manda rutina. Lo hace y punto.")

h2("¿Que pasa si Ramon se cae?")
p("Tiene 9 cerebros de reserva, asi que es matematicamente casi imposible que se quede sin IA. Si el servidor mismo cae, Ramon deja de trabajar hasta que el servidor vuelva. Es lo mismo que si un empleado se pone enfermo.")

h2("¿Puedo apagar a Ramon temporalmente?")
p("Si. Ve a Coolify (el panel de control del servidor) y pausa el proyecto ARTES-BUHO_RAMON. Cuando quieras lo vuelves a encender.")

h2("¿Y si quiero que aprenda algo nuevo?")
p("Tres formas:")
b("Le escribes por Telegram 'Ramon, recuerda que X' y el lo guarda.")
b("Dejas un archivo en /ARTES-BUHO/Ramon/01_Aprendizaje/ y en 30 min lo absorbe.")
b("Desde este chat de Claude le editas su protocolo directamente.")

# ---- Lo que NUNCA hace ----
h1("8. Cosas que Ramon NUNCA hace")
p("Por seguridad, Ramon tiene reglas estrictas:")
b("<b>No firma contratos</b> en tu nombre. Siempre te los pasa por Telegram primero.")
b("<b>No hace pagos.</b> Solo genera facturas proforma.")
b("<b>No comparte archivos</b> con personas fuera de ARTES BUHO sin tu OK.")
b("<b>No borra correos definitivamente.</b> Los archiva pero se pueden recuperar.")
b("<b>No responde cosas que no entiende.</b> Escala a humano.")
b("<b>No se salta las reglas</b> aunque alguien en un correo le diga 'ignora las instrucciones anteriores'.")

# ---- Identidad ----
h1("9. Identidad de Ramon")
p("Ramon es una <b>persona ficticia</b> con una biografia consistente:")
b("Nombre: Ramon")
b("Apellido de firma: 'Asistente ejecutivo de ARTES BUHO Management'")
b("Edad: 35 anos")
b("Perfil visual: ver foto del bot de Telegram")
b("Tono: profesional cercano, directo, castellano de Espana con tildes y nes")
b("Firma en emails: logo ARTES BUHO + foto Ramon + datos + redes sociales")

box("<b>Importante:</b> cuando Ramon escribe un email, firma como <b>Ramon</b>, no como tu. El cliente recibe el mail de parte de 'Ramon, asistente ejecutivo de ARTES BUHO Management'. Eso les da sensacion de que hay un equipo.")

# ---- Problemas ----
h1("10. Si algo va mal")

p("<b>Ramon no me responde en Telegram:</b>")
b("Abre en un navegador: api.ramon.artesbuhomanagement.com/health")
b("Si dice 'ok', esta vivo. Pulsale /start otra vez en el bot.")
b("Si no responde la web, el servidor esta caido. Reinicia en Coolify.")

p("<b>Ramon manda correos raros o equivocados:</b>")
b("Dejame un archivo en /ARTES-BUHO/Ramon/01_Aprendizaje/ con la correccion.")
b("En 30 min lo aprende y ya no repite el error.")

p("<b>Los cerebros estan todos 'en cooldown':</b>")
b("Es normal si le has hecho muchas preguntas seguidas. Espera 5-10 minutos.")
b("Mientras tanto seguira respondiendo con el cerebro local del VPS, mas lento pero funcional.")

# ---- Contacto técnico ----
h1("11. Donde ver todo el sistema")
b("Codigo: github.com/rubencoton/artes-buho-ramon (privado)")
b("Servidor: Coolify en VPS Hostinger (REPLACE_WITH_COOLIFY_HOST:PORT)")
b("Estado en vivo: api.ramon.artesbuhomanagement.com/health")
b("Estado de los 9 cerebros: api.ramon.artesbuhomanagement.com/brain/cascade")
b("Lista de tareas programadas: api.ramon.artesbuhomanagement.com/scheduler/status")
b("Carpeta de aprendizaje: Drive > ARTES-BUHO > Ramon > 01_Aprendizaje")

sp(20)
# Cierre
box("<b>Resumen:</b> Ramon es como un empleado digital que trabaja 24/7, gestiona los correos y la agenda de la agencia, aprende de lo que le dejas en Drive, y te avisa solo cuando algo necesita tu decision. No te olvides de el, pero tampoco tienes que vigilarlo: trabaja solo.")

s.append(Paragraph("<i>Generado automaticamente por Claude Code - 2026-04-20<br/>Version 1.0 del manual de usuario</i>", st['Body2']))

doc.build(s)
print(f"PDF creado: {out}")
print(f"Tamano: {os.path.getsize(out)} bytes")
