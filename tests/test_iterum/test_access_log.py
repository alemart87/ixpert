"""Tests del log de auditoria legal."""


def test_view_creates_access_log(app, login_as, user_analista):
    from iterum.models import NPSAccessLog

    client = login_as(user_analista)
    r = client.get('/iterum/dashboard')
    assert r.status_code == 200

    with app.app_context():
        entries = NPSAccessLog.query.filter_by(user_id=user_analista.id).all()
        assert len(entries) >= 1
        assert any(e.action == 'view' for e in entries)


def test_audit_creates_access_log(app, login_as, user_analista):
    from models import db
    from iterum.models import NPSSurvey, NPSAccessLog
    from iterum.services.dedup import survey_hash
    from datetime import datetime

    with app.app_context():
        s = NPSSurvey(
            response_date=datetime(2026, 5, 1),
            channel='whatsapp', nps_score=2, category='detractor',
            comment='mal', agent_doc='1',
            unique_hash=survey_hash(datetime(2026, 5, 1), '1', 2, 'mal', 'whatsapp'),
        )
        db.session.add(s); db.session.commit()
        survey_id = s.id

    client = login_as(user_analista)
    r = client.post(f'/iterum/api/audit/{survey_id}',
                    json={'verdict': 'err', 'classification': 'X'},
                    headers={'Content-Type': 'application/json'})
    assert r.status_code == 200

    with app.app_context():
        updates = NPSAccessLog.query.filter_by(action='update', entity_type='audit').all()
        assert len(updates) >= 1
