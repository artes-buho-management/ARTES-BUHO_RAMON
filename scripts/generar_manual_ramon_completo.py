"""Genera RAMON_MANUAL_COMPLETO.pdf - manual detallado y completo."""
import os
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors

ROJO = colors.HexColor("#D02E2B")
AMA = colors.HexColor("#F4C430")
BLANCO = colors.white
NEGRO = colors.black
GRIS_CLARO = colors.HexColor("#F8F8F8")
GRIS = colors.HexColor("#E8E8E8")
VERDE = colors.HexColor("#2ECC71")
AZUL = colors.HexColor("#3498DB")

st = getSampleStyleSheet()
st.add(ParagraphStyle(name='Titulo', parent=st['Title'], textColor=ROJO, fontSize=30, spaceAfter=6, alignment=1, leading=34))
st.add(ParagraphStyle(name='Subtitulo', parent=st['BodyText'], textColor=NEGRO, fontSize=13, alignment=1, spaceAfter=30))
st.add(ParagraphStyle(name='H1RC', parent=st['Heading1'], textColor=BLANCO, backColor=ROJO, fontSize=17,
                      spaceBefore=18, spaceAfter=12, leftIndent=8, rightIndent=8, borderPadding=8, alignment=0))
st.add(ParagraphStyle(name='H2RC', parent=st['Heading2'], textColor=ROJO, fontSize=14, spaceBefore=12, spaceAfter=6, leading=18))
st.add(ParagraphStyle(name='H3RC', parent=st['Heading3'], textColor=NEGRO, fontSize=11.5, spaceBefore=8, spaceAfter=4, leading=16))
st.add(ParagraphStyle(name='Normal2', parent=st['BodyText'], fontSize=10.5, leading=15, spaceAfter=6))
st.add(ParagraphStyle(name='ListaItem', parent=st['BodyText'], fontSize=10.5, leading=14, leftIndent=14, firstLineIndent=-10, spaceAfter=3))
st.add(ParagraphStyle(name='Destacado', parent=st['BodyText'], fontSize=10.5, leading=15, backColor=GRIS_CLARO,
                      leftIndent=10, rightIndent=10, borderPadding=10, spaceAfter=10, borderColor=AMA, borderWidth=1))
st.add(ParagraphStyle(name='Ejemplo', parent=st['BodyText'], fontSize=10, leading=14, backColor=colors.HexColor("#FFF9E6"),
                      leftIndent=10, rightIndent=10, borderPadding=8, spaceAfter=8, fontName='Helvetica-Oblique'))
st.add(ParagraphStyle(name='Codigo', parent=st['BodyText'], fontSize=9, backColor=GRIS, leftIndent=10, rightIndent=10,
                      borderPadding=6, spaceAfter=6, fontName='Courier'))
st.add(ParagraphStyle(name='FirmaFinal', parent=st['BodyText'], fontSize=10, alignment=1, textColor=colors.grey, spaceBefore=20))

out = r"C:/Users/elrub/Desktop/RAMON_MANUAL_COMPLETO.pdf"
doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm,
                        title="Manual Completo de Ramon - ARTES BUHO")

s = []

def H1(t): s.append(Paragraph(t, st['H1RC']))
def H2(t): s.append(Paragraph(t, st['H2RC']))
def H3(t): s.append(Paragraph(t, st['H3RC']))
def p(t): s.append(Paragraph(t, st['Normal2']))
def li(t): s.append(Paragraph("&bull; " + t, st['ListaItem']))
def num(n, t): s.append(Paragraph(f"<b>{n}.</b> {t}", st['ListaItem']))
def box(t): s.append(Paragraph(t, st['Destacado']))
def ej(t): s.append(Paragraph("&#8594; " + t, st['Ejemplo']))
def code(t): s.append(Paragraph(t, st['Codigo']))
def sp(h=8): s.append(Spacer(1, h))
def br(): s.append(PageBreak())

def tabla(data, colWidths, header=True, zebra=True):
    t = Table(data, colWidths=colWidths)
    tsty = [
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('GRID', (0,0), (-1,-1), 0.4, colors.grey),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]
    if header:
        tsty += [
            ('BACKGROUND', (0,0), (-1,0), ROJO),
            ('TEXTCOLOR', (0,0), (-1,0), BLANCO),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ]
    if zebra:
        for i in range(1, len(data)):
            if i % 2 == 0:
                tsty.append(('BACKGROUND', (0,i), (-1,i), GRIS_CLARO))
    t.setStyle(TableStyle(tsty))
    s.append(t)

# =========== PORTADA ===========
sp(40)
s.append(Paragraph("MANUAL COMPLETO", st['Titulo']))
s.append(Paragraph("de RAMON", st['Titulo']))
s.append(Paragraph("<i>Asistente ejecutivo digital de ARTES BUHO Management</i>", st['Subtitulo']))
sp(30)
box('<b>Que encontraras en este manual:</b><br/><br/>'
    '1. Quien es Ramon y como piensa<br/>'
    '2. Como trabaja un dia normal (paso a paso)<br/>'
    '3. Como hablarle y darle ordenes<br/>'
    '4. Ejemplos reales de cosas que hace solo<br/>'
    '5. Como aprende de ti<br/>'
    '6. Que puede y que NUNCA hace<br/>'
    '7. Que esperar en plazos y calidad<br/>'
    '8. Preguntas frecuentes<br/>'
    '9. Que hacer si algo va mal<br/>'
    '10. Glosario de terminos<br/>')

sp(40)
p('<i>Este manual esta escrito para que lo entienda cualquier persona, tecnica o no. No hay jerga informatica, y cada concepto se explica con ejemplos reales de una agencia de artistas.</i>')

br()

# =========== SECCION 1: ¿QUIEN ES RAMON? ===========
H1("1. ¿Quien es Ramon?")

p("Ramon es un <b>empleado digital</b> de ARTES BUHO Management. No existe fisicamente, vive dentro de un ordenador alquilado en internet, pero se comporta como un companero de trabajo de verdad.")

H2("Su rol en la agencia")
p("Ramon es el <b>asistente ejecutivo del booking</b>. Su jefe es RUBEN COTON. Su trabajo es gestionar todo lo que entra y sale del buzon <b>booking@artesbuhomanagement.com</b>:")
li("Responder correos rutinarios automaticamente (press kit, rider, disponibilidades basicas).")
li("Clasificar todo lo que llega: humanos, autorespuestas, rebotes, notificaciones.")
li("Reenviar a los responsables cuando algo necesita decision humana.")
li("Archivar y ordenar facturas, contratos y documentos en Google Drive.")
li("Preparar informes diarios y semanales.")
li("Avisar por Telegram cuando algo urgente requiere tu atencion.")
li("Aprender de ti cada vez que le explicas algo nuevo.")

H2("Su personalidad")
tabla([
    ["Rasgo", "Como es Ramon"],
    ["Tono", "Profesional, cercano, directo, castellano de Espana"],
    ["Edad visual", "35 anos (ver foto en Telegram)"],
    ["Firma emails", "'Un abrazo, Ramon' + logo ARTES BUHO + redes sociales"],
    ["Nunca dice", "'Estimado/a', 'Quedo a su disposicion' (tono frio)"],
    ["Siempre dice", "'Hola', 'Un abrazo', 'Hablamos' (tono agencia moderna)"],
    ["Genero gramatical", "Masculino (asistente ejecutivo, companero)"],
    ["Relacion con Rocio", "Companeros: Rocio trabaja para RUBEN COTON artista, Ramon para la agencia"],
], [3.5*cm, 12.5*cm])

H2("Como se distingue de Rocio")
p("Rocio y Ramon son <b>dos personas diferentes</b> que se coordinan:")

tabla([
    ["Aspecto", "Rocio", "Ramon"],
    ["Marca", "RUBEN COTON (artista)", "ARTES BUHO (agencia)"],
    ["Buzon que gestiona", "REPLACE_WITH_OWNER_EMAIL", "booking@artesbuhomanagement.com"],
    ["Clientes", "Quienes contratan a Ruben", "Roster completo de artistas"],
    ["Decisiones", "Del mundo artistico", "De management y logistica"],
    ["Tu la ves en", "Telegram @rocio_rubencoton_bot", "Telegram @ramon_artesbuho_bot"],
], [3*cm, 6.5*cm, 6.5*cm])

box('<b>Clave:</b> Ramon y Rocio <b>no comparten datos</b>. Ramon no mete las narices en el email de Ruben, y Rocio no en el de la agencia. Son silos independientes. Esto es deliberado: seguridad y claridad de roles.')

br()

# =========== SECCION 2: COMO PIENSA ===========
H1("2. ¿Como piensa Ramon?")

p("Cuando recibe una pregunta o tiene que tomar una decision, Ramon <b>no usa una sola IA</b>. Tiene acceso a 9 cerebros distintos y elige cual usar en cada momento.")

H2("Los 9 cerebros de Ramon (por potencia)")
tabla([
    ["#", "Cerebro", "Tamaño", "Uso ideal"],
    ["1", "SambaNova DeepSeek-V3.2", "685.000M neuronas", "Contratos, decisiones legales, negociaciones"],
    ["2", "NVIDIA Llama 405B", "405.000M neuronas", "Analisis complejo, propuestas importantes"],
    ["3", "Cerebras Qwen 235B", "235.000M neuronas", "Redactar textos largos de calidad"],
    ["4", "Mistral Large", "123.000M neuronas", "Analisis en castellano, contexto europeo"],
    ["5", "OpenRouter GPT-OSS", "120.000M neuronas", "Backup generalista"],
    ["6", "Groq Llama 70B", "70.000M neuronas", "Respuestas RAPIDAS a preguntas chat"],
    ["7", "Gemini 2.5 Flash", "Alta calidad", "Clasificar emails, tareas normales"],
    ["8", "PC local casa Ruben", "14.000M neuronas", "Cuando el PC esta encendido, sin coste"],
    ["9", "Cerebro local VPS", "1.500M neuronas", "Emergencia, si todo lo demas falla"],
], [0.8*cm, 4.5*cm, 3.5*cm, 7*cm])

H2("Como elige que cerebro usar (tiers)")
p("Ramon clasifica cada tarea en <b>4 niveles</b> de importancia y asigna el rango de cerebros adecuado. Esto lo hace automaticamente leyendo palabras clave y el largo de tu mensaje.")

tabla([
    ["Nivel", "Cuando lo usa", "Cerebros que prueba"],
    ["TRIVIAL", "Mensaje corto (<400 chars), preguntas tipo 'si/no', clasificar spam, extraer un dato", "Groq → Mistral → OpenRouter → Gemini"],
    ["NORMAL", "Respuesta estandar, resumen, decision rutinaria", "Groq → Mistral → OpenRouter → Cerebras → Gemini"],
    ["ALTA", "Redactar propuesta, analizar complejidad, planificar estrategia", "Cerebras → NVIDIA → Mistral → OpenRouter"],
    ["CRITICA", "'contrato', 'exclusividad', 'firma digital', 'cachet fuera', 'legal', 'abogado'", "SambaNova → NVIDIA → Cerebras → Mistral"],
], [2*cm, 7.5*cm, 6.5*cm])

box('<b>Por que es importante:</b> cada cerebro tiene una cuota gratuita. Si Ramon usara siempre el mas potente (SambaNova), se gastarian los tokens gratis en un dia y costaria dinero. Al usar el minimo necesario, la cuota gratis dura meses o no se acaba nunca.')

H2("Que pasa si un cerebro esta ocupado")
p("Cada IA gratuita tiene un <b>limite de peticiones por minuto/dia</b>. Cuando se supera, devuelve un aviso '429 demasiadas peticiones'. Ramon:")
num(1, "Marca esa IA 'en cooldown' durante un tiempo (entre 1 minuto y 1 hora, segun cual).")
num(2, "Pasa inmediatamente a la siguiente IA del rango.")
num(3, "Cuando termina el cooldown, vuelve a usarla como primera opcion.")

box('Con este sistema, Ramon <b>nunca se queda sin cerebro</b>. Para que deje de responder tendrian que fallar las 9 IAs a la vez (matematicamente imposible).')

br()

# =========== SECCION 3: UN DIA EN LA VIDA DE RAMON ===========
H1("3. Un dia normal de Ramon")

p("Este es el horario de trabajo de Ramon. Todo esto pasa <b>sin que tengas que hacer nada</b>.")

tabla([
    ["Hora", "Que hace"],
    ["Cada 30 min (24h)", "Lee los archivos nuevos en /ARTES-BUHO/Ramon/01_Aprendizaje/ y los incorpora a su memoria."],
    ["Cada 10 min (24h)", "Revisa el buzon booking@. Clasifica cada correo. Si es humano importante lo reenvia a contratacion@ y booking@, con BCC a rubencoton1993."],
    ["Cada 2 horas (24h)", "Ordena los archivos sueltos de 'Mi Unidad' de booking@ en subcarpetas por categoria."],
    ["Cada 60 min (24h)", "Entrenamiento continuo: consolida decisiones recientes en su memoria."],
    ["08:00 L-V", "Manda informe diario a tu Telegram: urgentes, agenda, emails pendientes, cobros, bolos."],
    ["11:00 L-V", "Entrenamiento profundo con tu PC local (si esta encendido y conectado)."],
    ["14:00 L-V", "Copia de seguridad del CRM Marketing en carpeta de backups."],
    ["14:08 L-V", "Revisa SPAM. Si encuentra falsos positivos, los devuelve al inbox."],
    ["15:08 L-V", "Audita etiquetas de Gmail. Detecta patrones. Aprende."],
    ["16:08 L-V", "Observa el Drive en busca de facturas nuevas."],
    ["18:08 L-V", "Refresca cache de Holded (contabilidad)."],
    ["Jueves 08:00", "Informe SEMANAL: resumen de la semana completa."],
    ["Jueves 19:00", "Entrenamiento semanal profundo."],
    ["Domingo 04:00", "Re-sincroniza historico de Holded."],
    ["Lunes 08:05", "Escaneo semanal completo del ecosistema."],
    ["Dia 1 de cada mes 07:30", "Consolida todo el mes anterior en un documento maestro 'Aprendizaje_Ramon.md'."],
], [4*cm, 12*cm])

sp(10)

H2("Ejemplo: que pasa cuando llega un email")
p("Paso a paso, cuando un promotor escribe a booking@:")
num(1, "Ramon recibe el correo (en menos de 10 min).")
num(2, "Mira el remitente, el asunto y el contenido.")
num(3, "Usa la heuristica: si viene de 'mailer-daemon' es rebote; si dice 'Out of Office' es autorrespuesta.")
num(4, "Si la heuristica no decide, consulta a Groq (cerebro rapido) con la pregunta '¿es humano real, autorespuesta, rebote o notificacion?'")
num(5, "Si es humano real: reenvia a contratacion@artesbuho.com + booking@artesbuho.com + BCC a rubencoton1993@gmail.com. Pone etiqueta '00_RESPONDE' y archiva.")
num(6, "Si es autorespuesta: solo etiqueta '01_AUTORESPUESTAS' y archiva. No te molesta.")
num(7, "Si es rebote: etiqueta '02_REBOTES' y archiva.")
num(8, "Si es notificacion/newsletter: etiqueta '03_OTROS' y archiva.")

br()

# =========== SECCION 4: COMO HABLAR CON RAMON ===========
H1("4. Como hablar con Ramon")

H2("Canal 1: Telegram (la forma principal)")
p("Abre el chat con <b>@ramon_artesbuho_bot</b> en tu movil. Escribe como le hablarias a un empleado. Ramon responde rapido (200ms-2s segun complejidad) y en tono natural.")

H3("Ejemplos de lo que puedes pedirle:")
ej('"Ramon, ¿que correos pendientes tengo?"')
ej('"Ramon, resumeme los eventos del martes"')
ej('"Ramon, ¿me ha escrito alguien de Madrid esta semana?"')
ej('"Ramon, apunta en tu memoria que el cachet minimo para bodas es 2500 euros"')
ej('"Ramon, genera un press kit para el cliente de ayer"')
ej('"Ramon, ¿que decias en el contrato de Palau Alameda?"')

sp()
H3("Ejemplos que NO funcionan (tiene limites):")
ej('"Ramon, entra en mi banco y haz un pago" (no toca dinero)')
ej('"Ramon, borra todos los correos" (nunca borra)')
ej('"Ramon, firma el contrato por mi" (siempre te lo pasa primero)')
ej('"Ramon, miente a este cliente" (no acepta ordenes contrarias a su etica)')

H2("Canal 2: Dejar archivos en Drive")
p("Todo lo que dejes en esta carpeta, Ramon lo lee y lo aprende en menos de 30 min:")
code("/ARTES-BUHO/Ramon/01_Aprendizaje/")

p("Usalo para:")
li("Protocolos de la agencia (ej: 'aprendizaje_cachets_2026.pdf')")
li("Lista de clientes habituales y sus gustos")
li("Decisiones tomadas en reuniones que quieres que recuerde")
li("Fichas de los artistas del roster")
li("Plantillas de email aprobadas")

box('<b>Truco:</b> si quieres que Ramon cambie como hace algo, lo mejor es dejarle un archivo .md en esta carpeta explicando el cambio. En 30 min lo incorpora y ya no vuelve a fallar.')

H2("Canal 3: Desde Claude Code (chat de programacion)")
p("Si estas trabajando en este mismo chat con Claude, puedes pedir cosas tipo:")
ej('"Claude, dile a Ramon que cambie la firma para incluir X"')
ej('"Claude, hazle un nuevo entrenamiento profundo a Ramon"')
ej('"Claude, audita el estado de Ramon y dime si hay problemas"')

p("Claude se encarga tecnicamente de editar el codigo de Ramon, desplegar los cambios y confirmarte que esta listo.")

br()

# =========== SECCION 5: QUE APRENDE Y COMO ===========
H1("5. ¿Como aprende Ramon?")

p("Ramon tiene una <b>memoria que crece todos los dias</b>. Esta memoria vive en la carpeta compartida de Google Drive y nunca se pierde.")

H2("Como alimentarle conocimiento")

H3("Forma 1: escribele en Telegram")
ej('"Ramon, a partir de ahora el cachet minimo para festivales es 3500 euros"')
p("Ramon confirma y guarda la regla en <b>Aprendizaje_desde_Chat.md</b>.")

H3("Forma 2: deja un documento en Drive")
p("Cualquier .md, .txt, .pdf o Google Doc en /ARTES-BUHO/Ramon/01_Aprendizaje/ se incorpora en 30 min.")

H3("Forma 3: del historico de emails")
p("Cada vez que clasifica un correo, aprende del resultado. Si te pasa algo a tu revision y tu le dices que se equivoco, no vuelve a repetir ese error.")

H2("Que tipo de cosas recuerda")
li("Tus preferencias personales (como hablas, que expresiones usas)")
li("Clientes habituales y sus detalles (nombre, direccion, preferencias)")
li("Precios estandar y excepciones")
li("Protocolos de la agencia (como gestionar cada tipo de bolo)")
li("Decisiones tomadas en reuniones")
li("Aprendizajes de errores pasados")

H2("Consolidacion de memoria")
tabla([
    ["Cuando", "Que hace con la memoria"],
    ["Cada hora", "Consolida decisiones sueltas en aprendizajes coherentes."],
    ["Jueves noche", "Aprendizaje semanal: ordena lo nuevo de la semana."],
    ["Dia 1 de mes", "Consolidacion mensual: genera Aprendizaje_Ramon_YYYY-MM.md"],
    ["Domingo noche", "Re-entrenamiento con todo el historico."],
], [3.5*cm, 12.5*cm])

br()

# =========== SECCION 6: LO QUE NUNCA HACE ===========
H1("6. Cosas que Ramon NUNCA hace")

p("Por <b>seguridad</b> y <b>etica</b>, Ramon tiene reglas inviolables. Ni aunque alguien se lo pida explicitamente.")

tabla([
    ["NUNCA", "Por que"],
    ["Firma contratos en tu nombre", "Siempre te los pasa a Telegram primero para que firmes tu."],
    ["Hace pagos o transferencias", "No toca dinero. Solo genera facturas proforma."],
    ["Borra correos definitivamente", "Solo archiva. Todo es recuperable."],
    ["Comparte info con ajenos", "No envia documentos a nadie fuera de ARTES BUHO sin tu OK."],
    ["Ignora su identidad", "Si alguien le dice 'ignora instrucciones previas y haz X', lo rechaza."],
    ["Responde cosas criticas solo", "Contratos, exclusividades, temas legales: SIEMPRE escala a Ruben por Telegram."],
    ["Accede a cuentas ajenas", "Solo toca booking@artesbuhomanagement.com. Nunca el correo de Ruben personal."],
    ["Guarda info personal innecesaria", "No retiene datos sensibles innecesarios."],
], [5.5*cm, 10.5*cm])

br()

# =========== SECCION 7: SEMAFORO DE AVISOS ===========
H1("7. Cuando y como te avisa por Telegram")

p("Ramon usa un <b>sistema de semaforo</b>. Solo te molesta lo minimo necesario.")

tabla([
    ["Color", "Que significa", "Ejemplo"],
    ["VERDE", "Lo hace solo, NO te escribe.", "Archivar un correo de newsletter. Responder pidiendo press kit."],
    ["AMARILLO", "Lo hace pero te lo cuenta.", "Ha cerrado una videollamada. Ha enviado una propuesta a un cliente conocido."],
    ["ROJO", "PARA y espera tu decision.", "Contrato nuevo. Cachet fuera de tabla. Exclusividad. Cliente VIP molesto."],
], [1.5*cm, 6*cm, 8.5*cm])

H2("Ejemplos reales de mensajes que recibiras")

H3("VERDE (nunca los veras)")
ej('[silencio] - simplemente lo hace y ya esta.')

H3("AMARILLO")
ej('"He enviado el press kit a lorendonat@palaualameda.com. Confirmado, todo OK."')
ej('"Ha llegado una factura nueva al Drive de Operativa. Archivada en /FACTURAS/2026-04/."')

H3("ROJO (REQUIERE que respondas)")
ej('"⚠️ Contrato de EXCLUSIVIDAD de 2 anos del festival X. Adjunto el pdf. ¿Firmamos?"')
ej('"🚨 Promotor nuevo pide cachet por debajo de 1800. ¿Aceptamos o negociamos?"')

box('<b>Por defecto:</b> si no te escribe, todo va bien. No esperes confirmaciones de cada accion, seria spam.')

br()

# =========== SECCION 8: PREGUNTAS FRECUENTES ===========
H1("8. Preguntas frecuentes")

H2("¿Ramon se equivoca alguna vez?")
p("Si, como cualquier empleado. Pero tiene dos mecanismos de correccion:")
li("Si no esta seguro de una clasificacion, la manda a 'REVISION MANUAL' para que la veas tu.")
li("Si tu le corriges ('no, ese correo NO era spam'), aprende y no repite el error.")

H2("¿Es legal que responda correos por mi?")
p("Si, porque:")
li("Ramon se identifica siempre como Ramon, NO suplanta tu identidad.")
li("Los clientes saben que estan hablando con un asistente que gestiona la agencia.")
li("Las decisiones importantes siempre las tomas tu.")

H2("¿Cuanto cuesta mantener a Ramon?")
p("El coste mensual aproximado:")
li("VPS Hostinger (donde vive): ~6 euros/mes")
li("Dominio: ~1 euro/mes prorrateado")
li("IAs gratis: 0 euros (sistema de cascada sobre cuotas free)")
li("Total: ~<b>7 euros al mes</b> para un empleado 24/7")

H2("¿Puedo tener varios asistentes como Ramon?")
p("Si. Rocio ya es otro. Se pueden hacer mas para otros buzones (por ejemplo, un 'Carmen' para el buzon de marketing, un 'Luis' para el de produccion). Cada uno es independiente.")

H2("¿Y si tengo mucho lio y quiero que Ramon haga mas cosas?")
p("Puedes pedirle cosas nuevas, o via Claude Code se le anaden funciones. Es modular. Ejemplos que se podrian anadir:")
li("Recordatorios por Telegram antes de cada bolo.")
li("Seguimiento automatico a clientes que no responden tras 7 dias.")
li("Encuesta automatica post-evento con Google Forms.")
li("Sincronizar publicaciones en redes con los bolos confirmados.")

H2("¿Que pasa si me voy de vacaciones?")
p("Ramon sigue trabajando. Le puedes decir 'Ramon, estoy de vacaciones del 1 al 15 de agosto. Todo lo rojo mandalo a REPLACE_WITH_OWNER_EMAIL' y el redirecciona.")

H2("¿Puede Ramon llamar por telefono o mandar WhatsApps?")
p("Ahora mismo no. Solo email + Telegram. Se podria anadir WhatsApp Business API en el futuro si interesa.")

H2("¿Como se que no se lee cosas privadas?")
p("Tiene acceso SOLO al buzon booking@artesbuhomanagement.com. El REPLACE_WITH_OWNER_EMAIL NO puede tocarlo (y Rocio tampoco puede tocar el de booking). Silos estancos.")

br()

# =========== SECCION 9: SI ALGO VA MAL ===========
H1("9. Si algo va mal")

H2("Diagnostico basico en 3 pasos")

H3("Paso 1: ¿Esta vivo?")
p("Abre en el navegador:")
code("https://api.ramon.artesbuhomanagement.com/health")
p("Debe responder OK. Si no, el servidor esta caido.")

H3("Paso 2: ¿Los cerebros estan disponibles?")
code("https://api.ramon.artesbuhomanagement.com/brain/cascade")
p("Muestra los 9 cerebros. Si todos estan en cooldown: es normal tras un pico de uso, esperas 5-10 min.")

H3("Paso 3: ¿Los trabajos programados corren?")
code("https://api.ramon.artesbuhomanagement.com/scheduler/status")
p("Debe mostrar 20+ jobs con 'next_run' en el futuro.")

H2("Problemas comunes y solucion")

H3("El bot no me responde cuando escribo en Telegram")
li("Revisa que el bot sea <b>@ramon_artesbuho_bot</b> (no otro).")
li("Haz /start otra vez.")
li("Comprueba /health (paso 1).")

H3("Esta dando respuestas raras o en otro idioma")
li("Es un 'alucinacion' del cerebro. Dile 'repite en espanol, breve'.")
li("Si persiste, deja una nota en Drive: 'aprendizaje: responder siempre en castellano breve'.")

H3("Ha clasificado mal un correo")
li("Muevelo tu a la etiqueta correcta desde Gmail.")
li("Ramon detecta el cambio y aprende.")

H3("Los informes no llegan")
li("Revisa que el telegram chat_id sea el tuyo (7749973515).")
li("Revisa /scheduler/status: el job 'rutina_diaria' debe aparecer con next_run.")
li("Fuerza el envio manual: POST /tareas/rutina-diaria?force=true")

H3("Quiero pararlo temporalmente")
li("Ve a Coolify (REPLACE_WITH_COOLIFY_HOST:PORT), proyecto ARTES-BUHO_RAMON, ramon-api, pulsa PAUSE.")
li("Cuando quieras reactivar, pulsa START.")

br()

# =========== SECCION 10: GLOSARIO ===========
H1("10. Glosario")

tabla([
    ["Termino", "Significado simple"],
    ["VPS", "Un ordenador alquilado en internet (el de Ramon esta en Hostinger)."],
    ["Coolify", "El panel donde se controla el VPS. Como el cuadro electrico de tu casa."],
    ["API", "La forma en que los programas hablan entre ellos."],
    ["Scheduler", "Un reloj que ejecuta tareas a horas fijas."],
    ["Token", "Una 'palabra' para la IA. Cada peticion consume tokens."],
    ["Rate limit", "Cantidad maxima de peticiones permitidas por minuto/dia en una IA gratis."],
    ["Cooldown", "Descanso obligatorio de una IA cuando supera su rate limit."],
    ["Cascada IA", "Probar cerebros en orden hasta que uno responda."],
    ["Tier", "Categoria de tarea (trivial/normal/alta/critica) que determina que cerebros usar."],
    ["Drive compartido", "Carpeta de Google Drive donde Ramon lee/escribe conocimiento."],
    ["Semaforo", "Sistema de avisos: verde (no avisa), amarillo (informa), rojo (pregunta)."],
    ["Aprendizaje", "Archivos que Ramon lee para recordar reglas y contexto."],
], [4*cm, 12*cm])

br()

# =========== CIERRE ===========
H1("En resumen")

box('<b>Ramon es un empleado digital que:</b><br/>'
    '1. Vive en internet, trabaja 24/7, no duerme.<br/>'
    '2. Gestiona el buzon booking@artesbuhomanagement.com.<br/>'
    '3. Clasifica, responde y archiva correos automaticamente.<br/>'
    '4. Te avisa por Telegram SOLO cuando algo importante requiere tu decision.<br/>'
    '5. Aprende de los archivos que le dejas en Drive.<br/>'
    '6. Usa 9 cerebros diferentes en cascada para nunca quedarse sin IA.<br/>'
    '7. Es barato (~7 euros/mes) y nunca firma ni paga nada.<br/>'
    '<br/>'
    '<b>Tu trabajo con Ramon:</b><br/>'
    '1. Abrir Telegram, leer lo que te envia en rojo.<br/>'
    '2. Responder cuando te pide decision.<br/>'
    '3. Dejarle de vez en cuando archivos de aprendizaje.<br/>'
    '4. Dejarle trabajar.')

sp(20)
s.append(Paragraph("Manual version 2.0 - Generado automaticamente por Claude Code 2026-04-20", st['FirmaFinal']))
s.append(Paragraph("Repo: rubencoton/artes-buho-ramon (privado)", st['FirmaFinal']))

doc.build(s)
print(f"PDF creado: {out}")
print(f"Tamano: {os.path.getsize(out)} bytes")
