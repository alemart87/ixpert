"""Tests de audit + root cause + coaching."""
from datetime import datetime, date


def _make_survey(db_session, **kw):
    from iterum.models import NPSSurvey
    from iterum.services.dedup import survey_hash
    kw.setdefault('response_date', datetime(2026, 5, 1))
    kw.setdefault('channel', 'whatsapp')
    kw.setdefault('nps_score', 5)
    kw.setdefault('category', 'detractor')
    kw.setdefault('comment', 'test')
    kw.setdefault('agent_doc', '999')
    kw['unique_hash'] = survey_hash(kw['response_date'], kw['agent_doc'],
                                     kw['nps_score'], kw['comment'], kw['channel'])
    s = NPSSurvey(**kw)
    db_session.add(s); db_session.commit()
    return s


def test_audit_upsert(app, db_session, user_analista):
    from iterum.services.audit import upsert_audit
    s = _make_survey(db_session)
    a = upsert_audit(survey_id=s.id, reviewer_id=user_analista.id,
                     verdict='warn', classification='Tiempo respuesta',
                     notes='Demoro')
    assert a.verdict == 'warn'
    a2 = upsert_audit(survey_id=s.id, reviewer_id=user_analista.id,
                      verdict='err', classification='Otro', notes='X')
    assert a.id == a2.id
    assert a2.verdict == 'err'


def test_audit_invalid_verdict(app, db_session, user_analista):
    from iterum.services.audit import upsert_audit
    s = _make_survey(db_session)
    import pytest
    with pytest.raises(ValueError):
        upsert_audit(survey_id=s.id, reviewer_id=user_analista.id, verdict='invalido')


def test_root_cause_upsert(app, db_session, user_analista):
    from iterum.services.root_cause import upsert_root_cause
    s = _make_survey(db_session)
    rc = upsert_root_cause(
        survey_id=s.id, created_by_id=user_analista.id,
        whys=['a', 'b', 'c'], root_cause='Falla X',
        due_date=date(2026, 6, 1), status='in_progress',
    )
    assert rc.why_1 == 'a'
    assert rc.why_4 == ''  # padding
    assert rc.status == 'in_progress'


def test_coaching_create_and_update(app, db_session, user_analista):
    from iterum.services.coaching import create_coaching, update_coaching
    c = create_coaching(
        agent_doc='123', coach_id=user_analista.id,
        agent_name='X', topic='Mejorar empatia',
    )
    assert c.status == 'pending'
    c2 = update_coaching(c.id, status='done', notes='ok')
    assert c2.status == 'done'
    assert c2.completed_at is not None
