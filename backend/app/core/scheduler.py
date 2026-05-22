"""Scheduler interno de Ramon (APScheduler).

Jobs programados:
 - 08:00 L-V (festivos Coslada excluidos) → rutina diaria + informe 08:15
 - Lunes 08:05                            → escaneo profundo 30d (capa 2)
 - Dia 1 de cada mes 07:30                → consolidacion aprendizaje + analisis estrategico
 - Cada 30s                               → polling Telegram (bot bidireccional)
 - Cada 2h (10-22)                        → revision ligera emails (capa 3)
"""
from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz

from app.core.settings import get_settings


log = logging.getLogger("ramon.scheduler")

_scheduler: BackgroundScheduler | None = None


def _tz():
    return pytz.timezone(get_settings().timezone)


def _job_rutina_diaria():
    from app.tasks.orquestador import ejecutar_y_enviar
    from app.tasks.informe_diario import generar_y_guardar_pdf
    from app.core.calendar_utils import is_workday, today_local

    if not is_workday(today_local()):
        log.info("scheduler: dia no laborable, skip rutina")
        return
    try:
        payload = ejecutar_y_enviar()
        if not payload.get("skipped"):
            try:
                generar_y_guardar_pdf(payload)
            except Exception as exc:
                log.warning(f"PDF informe fallo: {exc}")
    except Exception as exc:
        log.error(f"rutina fallo: {exc}")


def _job_escaneo_semanal():
    from app.tasks.escaneo import escaneo_capa_2
    try:
        escaneo_capa_2()
    except Exception as exc:
        log.error(f"escaneo semanal fallo: {exc}")


def _job_informe_semanal():
    from app.tasks.informe_semanal import enviar
    try:
        enviar()
    except Exception as exc:
        log.error(f"informe semanal fallo: {exc}")


def _job_sync_bloqueos():
    """Diario: crea bloqueos auto para dias con all-day events nuevos."""
    from app.core.availability import sincronizar_bloqueos
    try:
        sincronizar_bloqueos(dry_run=False)
    except Exception as exc:
        log.error(f"sync bloqueos fallo: {exc}")


def _job_meet_notes():
    """Cada hora: procesa transcripciones Meet recientes y genera notas."""
    from app.tasks.meet_notes import procesar_pendientes
    try:
        procesar_pendientes(horas=2)
    except Exception as exc:
        log.error(f"meet notes fallo: {exc}")


def _job_entrenamiento_semanal():
    """Domingo 05:00: re-entrena con historico reciente para refinar perfil."""
    from app.tasks.entrenamiento import entrenar_profundo
    try:
        entrenar_profundo(max_msgs_por_cuenta=150, chunk_size=20, pausa_s=8)
    except Exception as exc:
        log.error(f"entrenamiento semanal fallo: {exc}")


def _pc_online_ahora() -> bool:
    """Ventana típica de disponibilidad del PC local de Ruben:
    L-V 08:00-20:00 (ventana principal, 12h).
    Sab-Dom 08:00-20:00 (opcional, se intenta).
    Además comprobamos si el tunnel responde realmente.
    """
    from datetime import datetime
    import pytz
    from app.core.settings import get_settings
    tz = pytz.timezone(get_settings().timezone)
    now = datetime.now(tz)
    if not (8 <= now.hour < 20):
        return False
    # Ventana horaria OK. Verifica tunnel.
    try:
        from app.integrations.brain_router import pc_available
        return pc_available()
    except Exception:
        return False


def _job_entrenamiento_continuo():
    """Cada 30 min dentro de la franja PC (L-V 08-20). Si PC on, usa qwen2.5:14b."""
    import os as _os
    if _os.getenv("RAMON_TRAIN_CONTINUO", "true").lower() not in {"1", "true", "yes"}:
        return
    # Solo dentro de ventana + PC realmente online
    if not _pc_online_ahora():
        log.debug("entrenamiento_continuo: PC no disponible, skip")
        return
    from app.tasks.entrenamiento import entrenar_profundo
    try:
        entrenar_profundo(max_msgs_por_cuenta=20, chunk_size=5, pausa_s=15)
    except Exception as exc:
        log.error(f"entrenamiento continuo fallo: {exc}")


def _job_entrenamiento_profundo_pc():
    """Entrenamiento profundo grande: solo cuando PC esté online. Cada día a las 11:00 L-V."""
    if not _pc_online_ahora():
        log.info("entrenamiento_profundo_pc: PC no disponible, reintento al siguiente ciclo")
        return
    from app.tasks.entrenamiento import entrenar_profundo
    try:
        entrenar_profundo(max_msgs_por_cuenta=150, chunk_size=15, pausa_s=5)
    except Exception as exc:
        log.error(f"entrenamiento profundo PC fallo: {exc}")


def _job_ingesta_tick():
    """Cada 30 min: un tick de ingesta del ecosistema Google."""
    from app.tasks.ingesta_ecosistema import tick
    try:
        tick()
    except Exception as exc:
        log.error(f"ingesta tick fallo: {exc}")


def _job_revisar_spam():
    """Cada 2h: revisa carpeta SPAM y mueve spam real a RAMON/BASURA."""
    from app.tasks.revisar_spam import revisar
    try:
        revisar(max_msgs=20)
    except Exception as exc:
        log.error(f"revisar spam fallo: {exc}")


def _job_archivador_continuo():
    """Cada 20 min: clasifica y archiva un lote pequeño del inbox (nuevos+viejos)."""
    from app.tasks.archivador_continuo import archivar_lote
    try:
        archivar_lote(max_por_lote=8)
    except Exception as exc:
        log.error(f"archivador continuo fallo: {exc}")


def _job_vaciar_cola_telegram():
    """Cada 5 min: si estamos dentro de franja, entrega mensajes en cola."""
    from app.core.horario import vaciar_cola
    try:
        vaciar_cola()
    except Exception as exc:
        log.error(f"vaciar cola fallo: {exc}")


def _job_consolidacion_mensual():
    from app.learning.aprendizaje import consolidar_mensual
    from app.decisions.semaforo import exportar_a_xlsx
    try:
        consolidar_mensual()
    except Exception as exc:
        log.error(f"consolidacion mensual fallo: {exc}")
    try:
        exportar_a_xlsx()
    except Exception as exc:
        log.error(f"export decisiones fallo: {exc}")


def _job_revision_ligera():
    from app.tasks.orquestador import ejecutar_rutina_diaria
    from app.core.calendar_utils import is_workday, today_local, now_local
    if not is_workday(today_local()):
        return
    h = now_local().hour
    if h < 10 or h > 22:
        return
    try:
        ejecutar_rutina_diaria(force=False)
    except Exception as exc:
        log.error(f"revision ligera fallo: {exc}")


def _job_polling_telegram():
    from app.integrations.telegram_bidireccional import poll_once
    try:
        poll_once()
    except Exception as exc:
        log.debug(f"telegram poll: {exc}")


def _job_holded_refresh():
    """Cada 6h: refresca perfil Holded (últimas 200 facturas)."""
    from app.tasks.aprendizaje_holded import ejecutar_refresh
    try:
        ejecutar_refresh()
    except Exception as exc:
        log.error(f"holded refresh fallo: {exc}")


def _job_holded_historico_semanal():
    """Domingo 04:00: aprendizaje histórico completo Holded."""
    from app.tasks.aprendizaje_holded import ejecutar_historico
    try:
        ejecutar_historico()
    except Exception as exc:
        log.error(f"holded histórico fallo: {exc}")


def _job_rescate_correos():
    """L-V 10:30: procesa 7 correos históricos pendientes de respuesta."""
    from app.tasks.rescate_correos import rescatar_lote
    from app.core.calendar_utils import is_workday, today_local
    if not is_workday(today_local()):
        return
    try:
        rescatar_lote(max_hilos=7, dias=90)
    except Exception as exc:
        log.error(f"rescate correos fallo: {exc}")


def _job_auditor_etiquetas():
    """Cada 3h: limpia conflictos de etiquetas mutuamente excluyentes."""
    from app.tasks.auditor_etiquetas import auditar
    try:
        auditar(max_msgs=150)
    except Exception as exc:
        log.error(f"auditor etiquetas fallo: {exc}")


def _job_observador_drive_facturas():
    """Cada 4h: observa (solo lectura) carpeta Drive de facturas."""
    from app.tasks.observador_drive_facturas import observar
    try:
        observar()
    except Exception as exc:
        log.error(f"observador drive facturas fallo: {exc}")


def _job_ping_pc():
    """Cada 10 min: registra si el PC local está online (para diagnóstico y jobs opor-
    tunistas). No consume apenas recursos. Si detecta subida del PC tras estar caído,
    puede disparar un entrenamiento oportunista."""
    import time as _t
    try:
        from app.integrations.brain_router import pc_available
        online = pc_available()
        prev = getattr(_job_ping_pc, "_last", None)
        _job_ping_pc._last = online  # type: ignore[attr-defined]
        if online and prev is False:
            log.info("PC local acaba de encenderse → disparo entrenamiento oportunista")
            try:
                from app.tasks.entrenamiento import entrenar_profundo
                entrenar_profundo(max_msgs_por_cuenta=30, chunk_size=10, pausa_s=8)
            except Exception as exc:
                log.warning(f"entrenamiento oportunista fallo: {exc}")
    except Exception as exc:
        log.debug(f"ping pc: {exc}")


def build_scheduler() -> BackgroundScheduler:
    settings = get_settings()
    tz = _tz()
    sched = BackgroundScheduler(timezone=tz)

    sched.add_job(
        _job_rutina_diaria,
        CronTrigger(hour=settings.morning_hour, minute=settings.morning_minute, day_of_week="mon-fri", timezone=tz),
        id="rutina_diaria", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_escaneo_semanal,
        CronTrigger(hour=8, minute=5, day_of_week="mon", timezone=tz),
        id="escaneo_semanal", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_informe_semanal,
        CronTrigger(hour=8, minute=0, day_of_week="fri", timezone=tz),
        id="informe_semanal", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_sync_bloqueos,
        CronTrigger(hour=7, minute=50, day_of_week="mon-fri", timezone=tz),
        id="sync_bloqueos", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_meet_notes,
        IntervalTrigger(minutes=60, timezone=tz),
        id="meet_notes", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_vaciar_cola_telegram,
        IntervalTrigger(minutes=5, timezone=tz),
        id="vaciar_cola_tg", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_entrenamiento_semanal,
        # Movido a viernes 19:00 (PC normalmente online)
        CronTrigger(hour=19, minute=0, day_of_week="fri", timezone=tz),
        id="entrenamiento_semanal", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_entrenamiento_profundo_pc,
        # Cada día L-V a las 11:00 intenta entrenamiento profundo (si PC on)
        CronTrigger(hour=11, minute=0, day_of_week="mon-fri", timezone=tz),
        id="entrenamiento_profundo_pc", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_ingesta_tick,
        IntervalTrigger(minutes=15, timezone=tz),
        id="ingesta_tick", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_revisar_spam,
        IntervalTrigger(hours=2, timezone=tz),
        id="revisar_spam", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_archivador_continuo,
        IntervalTrigger(minutes=20, timezone=tz),
        id="archivador_continuo", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_entrenamiento_continuo,
        IntervalTrigger(minutes=30, timezone=tz),
        id="entrenamiento_continuo", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_consolidacion_mensual,
        CronTrigger(hour=7, minute=30, day="1", timezone=tz),
        id="consolidacion_mensual", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_revision_ligera,
        CronTrigger(hour="10,12,14,16,18,20,22", minute=0, day_of_week="mon-fri", timezone=tz),
        id="revision_ligera", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_polling_telegram,
        IntervalTrigger(seconds=30, timezone=tz),
        id="telegram_polling", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_holded_refresh,
        IntervalTrigger(hours=6, timezone=tz),
        id="holded_refresh", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_holded_historico_semanal,
        # PC ON 05:30-21:30: movido de domingo 04:00 a domingo 06:00
        CronTrigger(hour=6, minute=0, day_of_week="sun", timezone=tz),
        id="holded_historico", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_rescate_correos,
        CronTrigger(hour=10, minute=30, day_of_week="mon-fri", timezone=tz),
        id="rescate_correos", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_auditor_etiquetas,
        IntervalTrigger(hours=3, timezone=tz),
        id="auditor_etiquetas", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_ping_pc,
        IntervalTrigger(minutes=10, timezone=tz),
        id="ping_pc", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_observador_drive_facturas,
        IntervalTrigger(hours=4, timezone=tz),
        id="observador_drive_facturas", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_drive_organizer,
        IntervalTrigger(hours=2, timezone=tz),
        id="drive_organizer", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_crm_backup,
        CronTrigger(day_of_week="mon", hour=14, minute=0, timezone=tz),
        id="crm_backup_semanal", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_gmail_router,
        IntervalTrigger(minutes=10, timezone=tz),
        id="gmail_router_booking", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_backup_cerebro,
        # PC ON 05:30-21:30: movido de 03:00 a 06:00
        CronTrigger(hour=6, minute=0, timezone=tz),
        id="backup_cerebro_drive", replace_existing=True, max_instances=1, coalesce=True,
    )
    sched.add_job(
        _job_training_audit,
        IntervalTrigger(minutes=5, timezone=tz),
        id="training_audit_5m", replace_existing=True, max_instances=1, coalesce=True,
    )
    return sched


def _job_training_audit() -> None:
    """Cada 6h, SOLO si training activo, genera auditoria y avisa."""
    import logging as _log
    try:
        from app.tasks import training_mode
        from app.integrations.telegram_bot import send_message
        if not training_mode.is_training_active():
            return
        result = training_mode.run_audit()
        m = result.get("metrics_24h", {})
        msg = (f"<b>Auditoria entrenamiento Ramon</b>\n"
               f"Horas restantes: {result['training'].get('hours_remaining')}\n"
               f"Emails 24h: {m.get('emails')}\n"
               f"Decisiones 24h: {m.get('decisions')}\n"
               f"Telegram 24h: {m.get('telegram')}\n"
               f"Cascada IA: {result.get('cascade_configured')}/9 OK\n"
               f"Informe en Drive: /01_Aprendizaje/training_audit_*.md")
        try: send_message(msg)
        except Exception: pass
        _log.getLogger("ramon.scheduler").info(f"training_audit: {m}")
    except Exception as exc:
        _log.getLogger("ramon.scheduler").warning(f"training_audit fallo: {exc}")


def _job_backup_cerebro() -> None:
    """Backup diario 03:00 de la memoria (DB) a Drive /ARTES-BUHO/Ramon/05_Backups/."""
    import logging as _log
    try:
        from app.tasks import backup_cerebro
        result = backup_cerebro.run_backup()
        _log.getLogger("ramon.scheduler").info(f"backup_cerebro: {result}")
    except Exception as exc:
        _log.getLogger("ramon.scheduler").warning(f"backup_cerebro fallo: {exc}")


def _job_gmail_router() -> None:
    """Router Gmail booking cada 10 min (clasifica + reenvia RESPONDE)."""
    import logging as _log
    try:
        from app.tasks import gmail_router
        result = gmail_router.process_cycle(max_threads=20)
        _log.getLogger("ramon.scheduler").info(f"gmail_router stats={result.get('stats')}")
    except Exception as exc:
        _log.getLogger("ramon.scheduler").warning(f"gmail_router fallo: {exc}")


def _job_drive_organizer() -> None:
    """Organizador automatico de 'Mi unidad' cada 2 horas."""
    import logging as _log
    try:
        from app.tasks import drive_organizer
        stats = drive_organizer.process_one_cycle(max_files=25)
        _log.getLogger("ramon.scheduler").info(f"drive_organizer stats={stats.get('results')} elapsed={stats.get('elapsed_s')}s")
    except Exception as exc:
        _log.getLogger("ramon.scheduler").warning(f"drive_organizer fallo: {exc}")


def _job_crm_backup() -> None:
    """Copia SEMANAL de los 7 CRMs los lunes 14:00."""
    import logging as _log
    try:
        from app.tasks import drive_crm_backup
        result = drive_crm_backup.run_backup()
        _log.getLogger("ramon.scheduler").info(
            f"crm_backup semanal: ok={result.get('ok_count')}/{result.get('total')}"
        )
    except Exception as exc:
        _log.getLogger("ramon.scheduler").warning(f"crm_backup fallo: {exc}")


def start() -> BackgroundScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler
    _scheduler = build_scheduler()
    _scheduler.start()
    log.info("Ramon scheduler iniciado con %d jobs", len(_scheduler.get_jobs()))
    return _scheduler


def stop() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def get() -> BackgroundScheduler | None:
    return _scheduler


def status() -> dict:
    sc = get()
    if sc is None:
        return {"running": False}
    return {
        "running": sc.running,
        "jobs": [
            {"id": j.id, "next_run": j.next_run_time.isoformat() if j.next_run_time else None}
            for j in sc.get_jobs()
        ],
        "now": datetime.now(_tz()).isoformat(),
    }
