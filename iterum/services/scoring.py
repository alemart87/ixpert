"""Calculos de KPIs NPS, ranking de agentes y deteccion de patrones.

NPS = %promotores - %detractores. Range -100..100.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from sqlalchemy import func

from models import db
from iterum.models import NPSSurvey


def _apply_filters(query, *, channel=None, cell=None, agent_doc=None,
                   from_date=None, to_date=None):
    if channel:
        query = query.filter(NPSSurvey.channel == channel)
    if cell:
        query = query.filter(NPSSurvey.cell == cell)
    if agent_doc:
        query = query.filter(NPSSurvey.agent_doc == agent_doc)
    if from_date:
        query = query.filter(NPSSurvey.response_date >= from_date)
    if to_date:
        # inclusivo: agregamos un dia
        query = query.filter(NPSSurvey.response_date < to_date)
    return query


def dashboard_kpis(**filters) -> dict:
    """KPIs principales para la pagina Dashboard."""
    q = _apply_filters(db.session.query(NPSSurvey), **filters)

    rows = q.with_entities(
        NPSSurvey.category,
        func.count(NPSSurvey.id),
    ).group_by(NPSSurvey.category).all()

    counts = {'promotor': 0, 'pasivo': 0, 'detractor': 0}
    for cat, n in rows:
        if cat in counts:
            counts[cat] = n

    total = sum(counts.values())
    if total == 0:
        return {
            'total': 0, 'nps': None,
            'promotor_pct': 0, 'pasivo_pct': 0, 'detractor_pct': 0,
            'counts': counts,
            'avg_score': None,
        }

    promotor_pct = round(100 * counts['promotor'] / total, 1)
    pasivo_pct = round(100 * counts['pasivo'] / total, 1)
    detractor_pct = round(100 * counts['detractor'] / total, 1)
    nps = round(promotor_pct - detractor_pct, 1)

    avg_score = db.session.query(func.avg(NPSSurvey.nps_score))
    avg_score = _apply_filters(avg_score, **filters).scalar()

    return {
        'total': total,
        'nps': nps,
        'promotor_pct': promotor_pct,
        'pasivo_pct': pasivo_pct,
        'detractor_pct': detractor_pct,
        'counts': counts,
        'avg_score': round(float(avg_score), 2) if avg_score is not None else None,
    }


def nps_timeseries(granularity='day', **filters) -> list[dict]:
    """Serie temporal de NPS por dia/semana/mes.

    Buckets calculados en Python para portabilidad entre Postgres y SQLite
    (date_trunc no existe en SQLite). El volumen agregado es chico.
    """
    from datetime import date as _date, timedelta

    q = _apply_filters(
        db.session.query(NPSSurvey.response_date, NPSSurvey.category),
        **filters,
    )

    def _bucket(dt):
        if dt is None:
            return None
        d = dt.date() if hasattr(dt, 'date') else dt
        if granularity == 'month':
            return _date(d.year, d.month, 1)
        if granularity == 'week':
            # lunes de la semana
            return d - timedelta(days=d.weekday())
        return d

    buckets: dict = defaultdict(lambda: {'promotor': 0, 'pasivo': 0, 'detractor': 0})
    for dt, cat in q.all():
        b = _bucket(dt)
        if b is None or cat not in ('promotor', 'pasivo', 'detractor'):
            continue
        buckets[b][cat] += 1

    out = []
    for b in sorted(buckets.keys()):
        c = buckets[b]
        total = sum(c.values())
        nps = None
        if total > 0:
            nps = round(100 * (c['promotor'] - c['detractor']) / total, 1)
        out.append({
            'period': b.isoformat() if b else None,
            'total': total,
            'nps': nps,
            **c,
        })
    return out


def agent_ranking(limit=50, **filters) -> list[dict]:
    """Ranking de agentes por NPS. Solo agentes con >= 3 respuestas."""
    q = _apply_filters(
        db.session.query(
            NPSSurvey.agent_doc,
            NPSSurvey.agent_name,
            NPSSurvey.category,
            func.count(NPSSurvey.id),
        ),
        **filters,
    ).filter(NPSSurvey.agent_doc.isnot(None)).group_by(
        NPSSurvey.agent_doc, NPSSurvey.agent_name, NPSSurvey.category)

    by_agent: dict = defaultdict(lambda: {
        'name': '', 'promotor': 0, 'pasivo': 0, 'detractor': 0,
    })
    for doc, name, cat, n in q.all():
        by_agent[doc]['name'] = name or ''
        if cat in ('promotor', 'pasivo', 'detractor'):
            by_agent[doc][cat] = n

    rows = []
    for doc, d in by_agent.items():
        total = d['promotor'] + d['pasivo'] + d['detractor']
        if total < 3:
            continue
        nps = round(100 * (d['promotor'] - d['detractor']) / total, 1)
        rows.append({
            'agent_doc': doc,
            'agent_name': d['name'],
            'total': total,
            'nps': nps,
            'promotor': d['promotor'],
            'pasivo': d['pasivo'],
            'detractor': d['detractor'],
        })

    rows.sort(key=lambda r: (-r['nps'], -r['total']))
    return rows[:limit]


def cell_breakdown(**filters) -> list[dict]:
    """NPS por celula operativa."""
    q = _apply_filters(
        db.session.query(
            NPSSurvey.cell,
            NPSSurvey.category,
            func.count(NPSSurvey.id),
        ),
        **filters,
    ).filter(NPSSurvey.cell.isnot(None)).group_by(
        NPSSurvey.cell, NPSSurvey.category)

    by_cell: dict = defaultdict(lambda: {'promotor': 0, 'pasivo': 0, 'detractor': 0})
    for cell, cat, n in q.all():
        if cat in ('promotor', 'pasivo', 'detractor'):
            by_cell[cell][cat] = n

    rows = []
    for cell, d in by_cell.items():
        total = sum(d.values())
        nps = round(100 * (d['promotor'] - d['detractor']) / total, 1) if total else 0
        rows.append({
            'cell': cell, 'total': total, 'nps': nps, **d,
        })
    rows.sort(key=lambda r: -r['total'])
    return rows


def channel_breakdown(**filters) -> list[dict]:
    """NPS por canal (whatsapp / call)."""
    q = _apply_filters(
        db.session.query(
            NPSSurvey.channel,
            NPSSurvey.category,
            func.count(NPSSurvey.id),
        ),
        **filters,
    ).group_by(NPSSurvey.channel, NPSSurvey.category)

    by_ch: dict = defaultdict(lambda: {'promotor': 0, 'pasivo': 0, 'detractor': 0})
    for ch, cat, n in q.all():
        if cat in ('promotor', 'pasivo', 'detractor'):
            by_ch[ch or 'desconocido'][cat] = n

    rows = []
    for ch, d in by_ch.items():
        total = sum(d.values())
        nps = round(100 * (d['promotor'] - d['detractor']) / total, 1) if total else 0
        rows.append({'channel': ch, 'total': total, 'nps': nps, **d})
    rows.sort(key=lambda r: -r['total'])
    return rows


def coaching_urgency(agent_doc: str, **filters) -> str:
    """Urgencia de coaching basada en proporcion de detractores recientes."""
    q = _apply_filters(
        db.session.query(NPSSurvey.category, func.count(NPSSurvey.id)),
        agent_doc=agent_doc, **filters,
    ).group_by(NPSSurvey.category)
    counts = {'promotor': 0, 'pasivo': 0, 'detractor': 0}
    for cat, n in q.all():
        if cat in counts:
            counts[cat] = n
    total = sum(counts.values())
    if total == 0:
        return 'low'
    detractor_pct = 100 * counts['detractor'] / total
    if detractor_pct >= 40:
        return 'high'
    if detractor_pct >= 20:
        return 'med'
    return 'low'
