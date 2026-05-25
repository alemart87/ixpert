"""Tests de calculo de KPIs."""
from datetime import datetime


def _seed(session, surveys):
    from iterum.models import NPSSurvey
    from iterum.services.dedup import survey_hash
    objs = []
    for s in surveys:
        objs.append(NPSSurvey(
            response_date=s['date'],
            channel=s['channel'],
            cell=s.get('cell'),
            agent_name=s.get('agent_name'),
            agent_doc=s.get('agent_doc'),
            nps_score=s['nps'],
            category=('promotor' if s['nps'] >= 9 else 'pasivo' if s['nps'] >= 7 else 'detractor'),
            comment=s.get('comment'),
            unique_hash=survey_hash(s['date'], s.get('agent_doc'), s['nps'],
                                    s.get('comment'), s['channel']),
        ))
    session.bulk_save_objects(objs)
    session.commit()


def test_dashboard_kpis_empty(app):
    with app.app_context():
        from iterum.services import scoring
        k = scoring.dashboard_kpis()
        assert k['total'] == 0
        assert k['nps'] is None


def test_dashboard_kpis_basic(app, db_session):
    _seed(db_session, [
        {'date': datetime(2026, 5, 1), 'channel': 'whatsapp', 'nps': 10},
        {'date': datetime(2026, 5, 2), 'channel': 'whatsapp', 'nps': 9},
        {'date': datetime(2026, 5, 3), 'channel': 'whatsapp', 'nps': 0},
        {'date': datetime(2026, 5, 4), 'channel': 'call', 'nps': 8},
    ])
    from iterum.services import scoring
    k = scoring.dashboard_kpis()
    assert k['total'] == 4
    # 2 promotores, 1 pasivo, 1 detractor → NPS = 50 - 25 = 25
    assert k['nps'] == 25.0


def test_agent_ranking_includes_all_by_default(app, db_session):
    """El ranking original muestra TODOS los agentes (sin minimo), porque
    el banco tiene muchos asesores con 1-2 encuestas mensuales."""
    _seed(db_session, [
        {'date': datetime(2026, 5, 1), 'channel': 'whatsapp', 'agent_doc': '111', 'nps': 10},
        {'date': datetime(2026, 5, 2), 'channel': 'whatsapp', 'agent_doc': '111', 'nps': 10},
        {'date': datetime(2026, 5, 3), 'channel': 'whatsapp', 'agent_doc': '222', 'nps': 10},
        {'date': datetime(2026, 5, 4), 'channel': 'whatsapp', 'agent_doc': '222', 'nps': 9},
        {'date': datetime(2026, 5, 5), 'channel': 'whatsapp', 'agent_doc': '222', 'nps': 10},
        {'date': datetime(2026, 5, 6), 'channel': 'whatsapp', 'agent_doc': '333', 'nps': 10},
    ])
    from iterum.services import scoring
    r = scoring.agent_ranking()
    docs = {x['agent_doc'] for x in r}
    # Sin min_responses=1 default: TODOS aparecen, incluso el de 1 encuesta
    assert docs == {'111', '222', '333'}


def test_agent_ranking_respects_min_responses(app, db_session):
    """Se puede subir el umbral via min_responses si se quiere filtrar."""
    _seed(db_session, [
        {'date': datetime(2026, 5, 1), 'channel': 'whatsapp', 'agent_doc': '111', 'nps': 10},
        {'date': datetime(2026, 5, 3), 'channel': 'whatsapp', 'agent_doc': '222', 'nps': 10},
        {'date': datetime(2026, 5, 4), 'channel': 'whatsapp', 'agent_doc': '222', 'nps': 9},
        {'date': datetime(2026, 5, 5), 'channel': 'whatsapp', 'agent_doc': '222', 'nps': 10},
    ])
    from iterum.services import scoring
    r = scoring.agent_ranking(min_responses=3)
    docs = {x['agent_doc'] for x in r}
    assert docs == {'222'}  # 111 tiene solo 1, queda fuera


def test_filter_by_channel(app, db_session):
    _seed(db_session, [
        {'date': datetime(2026, 5, 1), 'channel': 'whatsapp', 'nps': 10},
        {'date': datetime(2026, 5, 2), 'channel': 'call', 'nps': 0},
    ])
    from iterum.services import scoring
    only_wa = scoring.dashboard_kpis(channel='whatsapp')
    assert only_wa['total'] == 1
    assert only_wa['nps'] == 100.0


def test_coaching_urgency(app, db_session):
    from iterum.services import scoring
    # Sin datos → low
    assert scoring.coaching_urgency('999') == 'low'

    _seed(db_session, [
        {'date': datetime(2026, 5, 1), 'channel': 'whatsapp', 'agent_doc': '111', 'nps': 0},
        {'date': datetime(2026, 5, 2), 'channel': 'whatsapp', 'agent_doc': '111', 'nps': 0},
        {'date': datetime(2026, 5, 3), 'channel': 'whatsapp', 'agent_doc': '111', 'nps': 10},
    ])
    # 2 detractores / 3 = 66% → high
    assert scoring.coaching_urgency('111') == 'high'


def test_ranking_works_with_only_agent_name(app, db_session):
    """Regression: el XLSX del banco solo trae AGENTE_ATENCION (username),
    no agent_doc. El ranking debe identificar agentes por name si no hay doc."""
    from iterum.models import NPSSurvey
    from iterum.services.dedup import survey_hash
    from datetime import datetime

    objs = []
    for i in range(3):
        d = datetime(2026, 5, 1 + i)
        objs.append(NPSSurvey(
            response_date=d, channel='whatsapp', nps_score=10,
            category='promotor', comment=f'c{i}',
            agent_name='GERARDOB', agent_doc=None,
            unique_hash=survey_hash(d, None, 10, f'c{i}', 'whatsapp'),
        ))
    db_session.bulk_save_objects(objs)
    db_session.commit()

    from iterum.services import scoring
    r = scoring.agent_ranking()
    assert len(r) == 1
    assert r[0]['agent_name'] == 'GERARDOB'
    assert r[0]['total'] == 3
    assert r[0]['nps'] == 100.0


def test_agent_ranking_includes_resolution_and_cell(app, db_session):
    from iterum.models import NPSSurvey
    from iterum.services.dedup import survey_hash
    objs = [
        NPSSurvey(response_date=datetime(2026, 5, i+1), channel='whatsapp',
                  cell='Cell1', agent_name='X', nps_score=10, category='promotor',
                  resolution='Si', effort='Facil',
                  unique_hash=survey_hash(datetime(2026, 5, i+1), None, 10, str(i), 'whatsapp'))
        for i in range(3)
    ] + [
        NPSSurvey(response_date=datetime(2026, 5, 10), channel='whatsapp',
                  cell='Cell1', agent_name='X', nps_score=2, category='detractor',
                  resolution='No', effort='Muy dificil',
                  unique_hash=survey_hash(datetime(2026, 5, 10), None, 2, 'd', 'whatsapp')),
    ]
    db_session.bulk_save_objects(objs)
    db_session.commit()
    from iterum.services import scoring
    r = scoring.agent_ranking()
    assert len(r) == 1
    a = r[0]
    assert a['cell'] == 'Cell1'
    assert a['channel'] == 'whatsapp'
    assert a['total'] == 4
    assert a['resolution_pct'] == 75  # 3/4
    assert a['effort_easy_pct'] == 75  # 3/4 Facil


def test_agent_ranking_sort_by_resolucion(app, db_session):
    from iterum.models import NPSSurvey
    from iterum.services.dedup import survey_hash
    from datetime import datetime as dt
    objs = []
    # A: resolution 100%, NPS 0
    for i in range(2):
        objs.append(NPSSurvey(response_date=dt(2026, 5, i+1), channel='whatsapp',
                              agent_name='A', nps_score=8, category='pasivo',
                              resolution='Si',
                              unique_hash=survey_hash(dt(2026, 5, i+1), None, 8, f'a{i}', 'whatsapp')))
    # B: resolution 0%, NPS 100
    objs.append(NPSSurvey(response_date=dt(2026, 5, 5), channel='whatsapp',
                          agent_name='B', nps_score=10, category='promotor',
                          resolution='No',
                          unique_hash=survey_hash(dt(2026, 5, 5), None, 10, 'b', 'whatsapp')))
    db_session.bulk_save_objects(objs)
    db_session.commit()
    from iterum.services import scoring
    r = scoring.agent_ranking(sort='resolucion')
    assert r[0]['agent_name'] == 'A'  # 100% resolucion va primero
    r2 = scoring.agent_ranking(sort='nps')
    assert r2[0]['agent_name'] == 'B'  # 100 nps va primero
