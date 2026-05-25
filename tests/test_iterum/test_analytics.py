"""Tests de analytics enriquecidos (dashboard, patrones, causa raiz, coaching)."""
from datetime import datetime


def _seed(session, rows):
    from iterum.models import NPSSurvey
    from iterum.services.dedup import survey_hash
    import uuid
    objs = []
    for r in rows:
        objs.append(NPSSurvey(
            response_date=r.get('date', datetime(2026, 5, 1)),
            channel=r.get('channel', 'whatsapp'),
            cell=r.get('cell'),
            agent_name=r.get('agent_name', 'X'),
            nps_score=r['nps'],
            category=('promotor' if r['nps'] >= 9 else 'pasivo' if r['nps'] >= 7 else 'detractor'),
            comment=r.get('comment'),
            client_name=r.get('client_name'),
            gender=r.get('gender'),
            effort=r.get('effort'),
            resolution=r.get('resolution'),
            motive=r.get('motive'),
            origin=r.get('origin'),
            why_1=r.get('why_1'),
            root_cause_type=r.get('root_cause_type'),
            responsibility=r.get('responsibility'),
            unique_hash=survey_hash(r.get('date', datetime(2026, 5, 1)), None,
                                    r['nps'], str(uuid.uuid4()), 'whatsapp'),
        ))
    session.bulk_save_objects(objs)
    session.commit()


def test_dashboard_full_with_resolucion(app, db_session):
    _seed(db_session, [
        {'nps': 10, 'resolution': 'Si'},
        {'nps': 9, 'resolution': 'Si'},
        {'nps': 5, 'resolution': 'No', 'motive': 'Demora'},
        {'nps': 2, 'resolution': 'No', 'motive': 'Demora', 'responsibility': 'Asesor'},
    ])
    from iterum.services import analytics
    k = analytics.dashboard_full()
    assert k['total'] == 4
    assert k['resolucion_count'] == 2
    assert k['resolucion_total'] == 4
    assert k['resolucion_pct'] == 50
    assert k['top_motivo'] == 'Demora'
    assert k['top_responsable'] == 'Asesor'


def test_gender_breakdown(app, db_session):
    _seed(db_session, [
        {'nps': 10, 'gender': 'Femenino'},
        {'nps': 9, 'gender': 'Femenino'},
        {'nps': 2, 'gender': 'Femenino'},
        {'nps': 10, 'gender': 'Masculino'},
        {'nps': 5, 'gender': 'No Detectado'},
    ])
    from iterum.services import analytics
    r = analytics.gender_breakdown()
    fem = next(x for x in r if x['gender'] == 'Femenino')
    assert fem['total'] == 3
    assert fem['promotor'] == 2
    assert fem['detractor'] == 1


def test_keyword_patterns_detects(app, db_session):
    _seed(db_session, [
        {'nps': 0, 'comment': 'Tarda mucho el sistema y no resuelven nada'},
        {'nps': 0, 'comment': 'Demora demasiado'},
        {'nps': 0, 'comment': 'No me dan solucion'},
    ])
    from iterum.services import analytics
    r = analytics.keyword_patterns()
    labels = {x['label'] for x in r}
    assert 'Tiempo de respuesta / demora' in labels
    assert 'No resolución del problema' in labels


def test_root_cause_analytics(app, db_session):
    _seed(db_session, [
        {'nps': 0, 'root_cause_type': 'Empatia/comunicacion', 'responsibility': 'Asesor', 'motive': 'Demora'},
        {'nps': 0, 'root_cause_type': 'Empatia/comunicacion', 'responsibility': 'Asesor', 'motive': 'Demora'},
        {'nps': 0, 'root_cause_type': 'Proceso mal disenado', 'responsibility': 'Proceso', 'motive': 'Pin'},
    ])
    from iterum.services import analytics
    r = analytics.root_cause_analytics()
    tipo = {x['label']: x['count'] for x in r['tipo_causa']}
    assert tipo['Empatia/comunicacion'] == 2
    resp = {x['label']: x['count'] for x in r['responsabilidad']}
    assert resp['Asesor'] == 2


def test_coaching_by_agent_groups_correctly(app, db_session):
    _seed(db_session, [
        {'agent_name': 'AGENTE1', 'nps': 0, 'motive': 'Pin', 'resolution': 'No'},
        {'agent_name': 'AGENTE1', 'nps': 0, 'motive': 'Pin', 'resolution': 'No'},
        {'agent_name': 'AGENTE1', 'nps': 0, 'motive': 'Pin', 'resolution': 'No'},
        {'agent_name': 'AGENTE1', 'nps': 10, 'comment': 'Excelente'},
        {'agent_name': 'AGENTE2', 'nps': 10},
    ])
    from iterum.services import analytics
    agents = analytics.coaching_by_agent()
    assert len(agents) == 1  # solo agente con detractores
    a = agents[0]
    assert a['agent_name'] == 'AGENTE1'
    assert a['detractores_count'] == 3
    assert a['sin_resolver'] == 3
    assert a['promotores_count'] == 1
    assert a['urgency'] == 'urgente'  # 3+ detractores


def test_nps_target_constant():
    """El objetivo del canal viene del backend (no hardcoded en JS)."""
    from iterum.services import analytics
    assert analytics.OBJETIVO_NPS_CANAL == 77

    import os
    # Configurable via env
    os.environ['ITERUM_NPS_TARGET'] = '85'
    import importlib
    importlib.reload(analytics)
    assert analytics.OBJETIVO_NPS_CANAL == 85
    # Restaurar
    os.environ['ITERUM_NPS_TARGET'] = '77'
    importlib.reload(analytics)
    assert analytics.OBJETIVO_NPS_CANAL == 77
