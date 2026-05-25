"""Servicios de Causa Raiz (5 Porques)."""
from datetime import date, datetime, timezone

from models import db
from iterum.models import NPSRootCause, NPSSurvey


VALID_STATUSES = {'open', 'in_progress', 'done'}


def upsert_root_cause(*, survey_id: int, created_by_id: int,
                      whys: list[str], root_cause: str | None = None,
                      action_owner_id: int | None = None,
                      due_date: date | None = None,
                      status: str = 'open') -> NPSRootCause:
    if status not in VALID_STATUSES:
        raise ValueError(f'status invalido: {status}')
    survey = db.session.get(NPSSurvey, survey_id)
    if not survey:
        raise ValueError(f'survey {survey_id} no existe')

    # Padding a 5 elementos
    whys = (whys or []) + [''] * (5 - len(whys or []))
    whys = whys[:5]

    rc = NPSRootCause.query.filter_by(survey_id=survey_id).first()
    if rc is None:
        rc = NPSRootCause(survey_id=survey_id, created_by_id=created_by_id)
        db.session.add(rc)

    rc.why_1, rc.why_2, rc.why_3, rc.why_4, rc.why_5 = whys
    rc.root_cause = root_cause
    rc.action_owner_id = action_owner_id
    rc.due_date = due_date
    rc.status = status
    rc.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return rc


def list_open_root_causes(limit=200):
    return NPSRootCause.query.filter(
        NPSRootCause.status != 'done'
    ).order_by(NPSRootCause.due_date.asc().nulls_last()).limit(limit).all()
