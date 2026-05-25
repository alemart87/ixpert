"""Servicios de auditoria operativa (veredictos de analistas sobre encuestas)."""
from datetime import datetime, timezone

from models import db
from iterum.models import NPSAudit, NPSSurvey


VALID_VERDICTS = {'ok', 'warn', 'err'}


def upsert_audit(*, survey_id: int, reviewer_id: int, verdict: str,
                 classification: str | None = None, notes: str | None = None) -> NPSAudit:
    """Crea o actualiza el veredicto de una encuesta."""
    if verdict not in VALID_VERDICTS:
        raise ValueError(f'verdict invalido: {verdict}')
    survey = db.session.get(NPSSurvey, survey_id)
    if not survey:
        raise ValueError(f'survey {survey_id} no existe')

    audit = NPSAudit.query.filter_by(survey_id=survey_id).first()
    if audit is None:
        audit = NPSAudit(survey_id=survey_id, reviewer_id=reviewer_id)
        db.session.add(audit)

    audit.verdict = verdict
    audit.classification = classification
    audit.notes = notes
    audit.reviewer_id = reviewer_id
    audit.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return audit


def list_audits(*, reviewer_id=None, verdict=None, limit=200):
    q = NPSAudit.query
    if reviewer_id:
        q = q.filter(NPSAudit.reviewer_id == reviewer_id)
    if verdict:
        q = q.filter(NPSAudit.verdict == verdict)
    return q.order_by(NPSAudit.updated_at.desc()).limit(limit).all()
