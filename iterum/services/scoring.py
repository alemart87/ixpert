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


def agent_ranking(limit=None, min_responses=1, sort='nps', **filters) -> list[dict]:
    """Ranking de agentes por NPS.

    - Identifica al agente por (agent_doc, agent_name); usa name si no hay doc.
    - Por defecto incluye todos los agentes con al menos 1 respuesta
      (replicando el comportamiento del Iterum original).
    - Calcula resolution_pct y effort_pct (% Muy facil + Facil) por agente.
    - Devuelve celula y canal dominante por agente (mode).
    - Ordenable por: nps | promotores | detractores | resolucion | esfuerzo.
    """
    base = _apply_filters(db.session.query(NPSSurvey), **filters)
    surveys = base.filter(
        (NPSSurvey.agent_doc.isnot(None)) | (NPSSurvey.agent_name.isnot(None))
    ).all()

    by_agent: dict = defaultdict(lambda: {
        'name': '', 'doc': '', 'promotor': 0, 'pasivo': 0, 'detractor': 0,
        'resolved': 0, 'easy': 0,
        'cells': defaultdict(int), 'channels': defaultdict(int),
    })
    for s in surveys:
        key = s.agent_doc if s.agent_doc else (s.agent_name or '')
        if not key:
            continue
        a = by_agent[key]
        a['doc'] = s.agent_doc or ''
        a['name'] = s.agent_name or ''
        if s.category in ('promotor', 'pasivo', 'detractor'):
            a[s.category] += 1
        if s.resolution == 'Si':
            a['resolved'] += 1
        if s.effort in ('Muy facil', 'Facil'):
            a['easy'] += 1
        if s.cell:
            a['cells'][s.cell] += 1
        if s.channel:
            a['channels'][s.channel] += 1

    rows = []
    for key, d in by_agent.items():
        total = d['promotor'] + d['pasivo'] + d['detractor']
        if total < min_responses:
            continue
        nps = round(100 * (d['promotor'] - d['detractor']) / total, 1)
        # Celula y canal dominante (modo)
        top_cell = max(d['cells'].items(), key=lambda x: x[1])[0] if d['cells'] else None
        top_channel = max(d['channels'].items(), key=lambda x: x[1])[0] if d['channels'] else None
        rows.append({
            'agent_doc': d['doc'],
            'agent_name': d['name'],
            'cell': top_cell,
            'channel': top_channel,
            'total': total,
            'nps': nps,
            'promotor': d['promotor'],
            'pasivo': d['pasivo'],
            'detractor': d['detractor'],
            'resolution_pct': round(100 * d['resolved'] / total, 0),
            'effort_easy_pct': round(100 * d['easy'] / total, 0),
        })

    # Ordenable
    if sort == 'promotores':
        rows.sort(key=lambda r: -r['promotor'])
    elif sort == 'detractores':
        rows.sort(key=lambda r: -r['detractor'])
    elif sort == 'resolucion':
        rows.sort(key=lambda r: -r['resolution_pct'])
    elif sort == 'esfuerzo':
        rows.sort(key=lambda r: -r['effort_easy_pct'])
    elif sort == 'total':
        rows.sort(key=lambda r: -r['total'])
    else:  # nps
        rows.sort(key=lambda r: (-r['nps'], -r['total']))

    if limit:
        rows = rows[:limit]
    return rows


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
    """Urgencia de coaching basada en proporcion de detractores recientes.

    `agent_doc` puede ser el documento real o el username/nombre del agente
    (data del banco usa username en AGENTE_ATENCION).
    """
    from sqlalchemy import or_
    q = _apply_filters(
        db.session.query(NPSSurvey.category, func.count(NPSSurvey.id)),
        **filters,
    ).filter(
        or_(NPSSurvey.agent_doc == agent_doc, NPSSurvey.agent_name == agent_doc)
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
