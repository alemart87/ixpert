"""Background job runner para procesar uploads grandes sin trancar requests.

Estrategia minimalista (sin Redis/Celery):
- ThreadPoolExecutor compartido a nivel proceso.
- El estado vive en nps_upload.status (pending/processing/done/failed).
- El frontend hace polling a /iterum/api/upload/<id>/status.

Limitaciones conocidas:
- Si gunicorn corre con multiples workers, el job vive en el worker que recibio
  el POST. Como el estado esta en DB, otros workers pueden consultar status sin
  problema (lo unico que no pueden es matar el job).
- Si el worker se reinicia mid-job, el upload queda en 'processing' colgado.
  Hay un sweeper que marca como 'failed' uploads en processing por mas de
  PROCESSING_TIMEOUT_MINUTES.
"""
from __future__ import annotations

import logging
import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

logger = logging.getLogger('iterum.jobs')

# Un pool chico es suficiente: cada upload tipicamente 1-10s.
MAX_WORKERS = int(os.environ.get('ITERUM_JOB_WORKERS', '2'))
PROCESSING_TIMEOUT_MINUTES = 15

_executor: ThreadPoolExecutor | None = None


def get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=MAX_WORKERS,
            thread_name_prefix='iterum-job',
        )
    return _executor


def submit_upload_processing(app, upload_id: int, file_path: str):
    """Encola el procesamiento. Devuelve inmediatamente."""
    executor = get_executor()
    executor.submit(_process_upload_safe, app, upload_id, file_path)


def _process_upload_safe(app, upload_id: int, file_path: str):
    """Wrapper que captura excepciones y siempre actualiza el estado."""
    with app.app_context():
        try:
            _process_upload(upload_id, file_path)
        except Exception as e:
            logger.exception('[iterum.jobs] upload=%s failed', upload_id)
            _mark_failed(upload_id, str(e), traceback.format_exc())
        finally:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except OSError:
                pass


def _process_upload(upload_id: int, file_path: str):
    """Procesa un upload: parsea XLSX, inserta surveys deduplicando."""
    from models import db
    from iterum.models import NPSUpload, NPSSurvey
    from iterum.services.excel_parser import parse_xlsx_stream
    from iterum.services.dedup import survey_hash

    upload = db.session.get(NPSUpload, upload_id)
    if not upload:
        logger.warning('[iterum.jobs] upload=%s no existe', upload_id)
        return

    upload.status = 'processing'
    db.session.commit()

    rows_total = 0
    rows_new = 0
    rows_duplicate = 0
    rows_invalid = 0
    period_start = None
    period_end = None

    # Set de hashes en memoria para dedupe intra-lote
    seen_hashes: set[str] = set()

    # Pre-cargar hashes existentes en DB para dedupe inter-lote
    # Optimizacion: solo cargar los del mismo periodo aprox seria mas eficiente,
    # pero para arrancar simple cargamos todos. Volumen banco: ~50k/mes.
    existing = {h[0] for h in db.session.query(NPSSurvey.unique_hash).all()}

    BATCH_SIZE = 500
    batch: list[NPSSurvey] = []

    for row in parse_xlsx_stream(file_path):
        rows_total += 1
        if row.get('_invalid'):
            rows_invalid += 1
            continue

        h = survey_hash(
            row['response_date'], row['agent_doc'], row['nps_score'],
            row['comment'], row['channel'],
        )
        if h in existing or h in seen_hashes:
            rows_duplicate += 1
            continue

        seen_hashes.add(h)
        rows_new += 1

        d = row['response_date'].date()
        if period_start is None or d < period_start:
            period_start = d
        if period_end is None or d > period_end:
            period_end = d

        batch.append(NPSSurvey(
            upload_id=upload_id,
            response_date=row['response_date'],
            channel=row['channel'],
            cell=row['cell'],
            agent_name=row['agent_name'],
            agent_doc=row['agent_doc'],
            nps_score=row['nps_score'],
            category=row['category'],
            comment=row['comment'],
            client_name=row.get('client_name'),
            client_doc=row.get('client_doc'),
            gender=row.get('gender'),
            effort=row.get('effort'),
            resolution=row.get('resolution'),
            resolved=row.get('resolved'),
            motive=row.get('motive'),
            gestion_type=row.get('gestion_type'),
            origin=row.get('origin'),
            problem_description=row.get('problem_description'),
            why_1=row.get('why_1'),
            why_2=row.get('why_2'),
            why_3=row.get('why_3'),
            root_cause_type=row.get('root_cause_type'),
            responsibility=row.get('responsibility'),
            unique_hash=h,
        ))

        if len(batch) >= BATCH_SIZE:
            db.session.bulk_save_objects(batch)
            db.session.commit()
            batch = []

    if batch:
        db.session.bulk_save_objects(batch)
        db.session.commit()

    upload.status = 'done'
    upload.rows_total = rows_total
    upload.rows_new = rows_new
    upload.rows_duplicate = rows_duplicate
    upload.rows_invalid = rows_invalid
    upload.period_start = period_start
    upload.period_end = period_end
    upload.processed_at = datetime.now(timezone.utc)
    db.session.commit()

    logger.info('[iterum.jobs] upload=%s done total=%d new=%d dup=%d inv=%d',
                upload_id, rows_total, rows_new, rows_duplicate, rows_invalid)


def _mark_failed(upload_id: int, message: str, trace: str = ''):
    from models import db
    from iterum.models import NPSUpload
    try:
        upload = db.session.get(NPSUpload, upload_id)
        if upload:
            upload.status = 'failed'
            upload.error_message = (message + ('\n\n' + trace if trace else ''))[:4000]
            db.session.commit()
    except Exception:
        db.session.rollback()


def sweep_stale_processing(app):
    """Marca como failed uploads atascados en 'processing' por timeout.

    Se llama en startup y opcionalmente desde un cron. Idempotente.
    """
    from models import db
    from iterum.models import NPSUpload
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=PROCESSING_TIMEOUT_MINUTES)
    with app.app_context():
        try:
            stale = NPSUpload.query.filter(
                NPSUpload.status == 'processing',
                NPSUpload.created_at < cutoff,
            ).all()
            for u in stale:
                u.status = 'failed'
                u.error_message = (u.error_message or '') + \
                    f'\n[sweeper] timeout {PROCESSING_TIMEOUT_MINUTES}min'
            if stale:
                db.session.commit()
                logger.info('[iterum.jobs] sweep marked %d stale uploads as failed', len(stale))
        except Exception:
            db.session.rollback()
