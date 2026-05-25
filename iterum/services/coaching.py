"""Servicios de coaching (asignacion, estado, urgencia)."""
import json
from datetime import datetime, timezone

from models import db
from iterum.models import NPSCoaching
from iterum.services.scoring import coaching_urgency


VALID_STATUSES = {'pending', 'done', 'skipped'}
VALID_URGENCIES = {'low', 'med', 'high'}


def create_coaching(*, agent_doc: str, coach_id: int,
                    agent_name: str | None = None,
                    topic: str | None = None,
                    notes: str | None = None,
                    related_survey_ids: list[int] | None = None,
                    scheduled_at: datetime | None = None,
                    urgency: str | None = None) -> NPSCoaching:
    if urgency is None:
        urgency = coaching_urgency(agent_doc)
    if urgency not in VALID_URGENCIES:
        raise ValueError(f'urgency invalido: {urgency}')

    c = NPSCoaching(
        agent_doc=agent_doc,
        agent_name=agent_name,
        coach_id=coach_id,
        urgency=urgency,
        topic=topic,
        notes=notes,
        related_survey_ids=json.dumps(related_survey_ids) if related_survey_ids else None,
        scheduled_at=scheduled_at,
    )
    db.session.add(c)
    db.session.commit()
    return c


def update_coaching(coaching_id: int, **kwargs) -> NPSCoaching:
    c = db.session.get(NPSCoaching, coaching_id)
    if not c:
        raise ValueError(f'coaching {coaching_id} no existe')

    if 'status' in kwargs:
        st = kwargs['status']
        if st not in VALID_STATUSES:
            raise ValueError(f'status invalido: {st}')
        c.status = st
        if st == 'done' and c.completed_at is None:
            c.completed_at = datetime.now(timezone.utc)
    if 'notes' in kwargs:
        c.notes = kwargs['notes']
    if 'topic' in kwargs:
        c.topic = kwargs['topic']
    if 'urgency' in kwargs and kwargs['urgency'] in VALID_URGENCIES:
        c.urgency = kwargs['urgency']
    if 'scheduled_at' in kwargs:
        c.scheduled_at = kwargs['scheduled_at']

    c.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return c


def list_coaching(*, coach_id=None, status=None, agent_doc=None, limit=200):
    q = NPSCoaching.query
    if coach_id:
        q = q.filter(NPSCoaching.coach_id == coach_id)
    if status:
        q = q.filter(NPSCoaching.status == status)
    if agent_doc:
        q = q.filter(NPSCoaching.agent_doc == agent_doc)
    return q.order_by(NPSCoaching.created_at.desc()).limit(limit).all()
