"""Analytics enriquecidos: KPIs del banco, distribuciones, patrones.

Replica la logica del Iterum legacy con queries SQLAlchemy en Postgres/SQLite.
"""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from sqlalchemy import func, or_

from models import db
from iterum.models import NPSSurvey


# Objetivo NPS del canal. Configurable via env, default 77 (banco PY).
OBJETIVO_NPS_CANAL = int(os.environ.get('ITERUM_NPS_TARGET', '77'))


# ============================================================================
# Filtros
# ============================================================================
def _apply_filters(query, *, channel=None, cell=None, agent_doc=None,
                   from_date=None, to_date=None, category=None, week=None):
    if channel: query = query.filter(NPSSurvey.channel == channel)
    if cell: query = query.filter(NPSSurvey.cell == cell)
    if agent_doc:
        query = query.filter(or_(NPSSurvey.agent_doc == agent_doc,
                                 NPSSurvey.agent_name == agent_doc))
    if from_date: query = query.filter(NPSSurvey.response_date >= from_date)
    if to_date: query = query.filter(NPSSurvey.response_date < to_date)
    if category: query = query.filter(NPSSurvey.category == category)
    if week:  # ISO week number como int
        query = query.filter(func.extract('week', NPSSurvey.response_date) == int(week))
    return query


# ============================================================================
# Dashboard KPIs enriquecidos
# ============================================================================
def dashboard_full(**filters) -> dict:
    """Todo el bloque de KPIs del dashboard original en una llamada."""
    base = _apply_filters(db.session.query(NPSSurvey), **filters)
    total = base.count()
    if total == 0:
        return _empty_dashboard()

    # Counts por categoria
    counts = {'promotor': 0, 'pasivo': 0, 'detractor': 0}
    for cat, n in _apply_filters(
        db.session.query(NPSSurvey.category, func.count(NPSSurvey.id)),
        **filters,
    ).group_by(NPSSurvey.category).all():
        if cat in counts:
            counts[cat] = n

    promotor_pct = round(100 * counts['promotor'] / total, 1)
    pasivo_pct = round(100 * counts['pasivo'] / total, 1)
    detractor_pct = round(100 * counts['detractor'] / total, 1)
    nps = round(promotor_pct - detractor_pct, 1)

    avg_score = _apply_filters(
        db.session.query(func.avg(NPSSurvey.nps_score)), **filters,
    ).scalar()
    avg_score = round(float(avg_score), 2) if avg_score is not None else None

    # Resolución
    resol_yes = _apply_filters(base, **{}).filter(NPSSurvey.resolution == 'Si').count()
    resol_total_with = _apply_filters(base, **{}).filter(NPSSurvey.resolution.isnot(None)).count()
    resol_pct = round(100 * resol_yes / resol_total_with, 0) if resol_total_with else None

    # Esfuerzo muy dificil
    muy_dificil = _apply_filters(base, **{}).filter(NPSSurvey.effort == 'Muy dificil').count()

    # Con comentario
    con_comentario = _apply_filters(
        db.session.query(NPSSurvey),
        **filters,
    ).filter(NPSSurvey.comment.isnot(None)).filter(NPSSurvey.comment != '').count()
    con_comentario_pct = round(100 * con_comentario / total, 0) if total else 0

    # Top motivo detractor
    top_motivo = None; top_motivo_count = 0
    motivo_rows = _apply_filters(
        db.session.query(NPSSurvey.motive, func.count(NPSSurvey.id)),
        **filters,
    ).filter(NPSSurvey.category == 'detractor').filter(
        NPSSurvey.motive.isnot(None)
    ).group_by(NPSSurvey.motive).order_by(func.count(NPSSurvey.id).desc()).limit(1).all()
    if motivo_rows:
        top_motivo, top_motivo_count = motivo_rows[0]

    # Principal responsable (Asesor/Externo/Proceso)
    top_resp = None; top_resp_count = 0
    resp_rows = _apply_filters(
        db.session.query(NPSSurvey.responsibility, func.count(NPSSurvey.id)),
        **filters,
    ).filter(NPSSurvey.category == 'detractor').filter(
        NPSSurvey.responsibility.isnot(None)
    ).group_by(NPSSurvey.responsibility).order_by(func.count(NPSSurvey.id).desc()).limit(1).all()
    if resp_rows:
        top_resp, top_resp_count = resp_rows[0]

    # Con causa raiz (porque_1 not null)
    con_causa_raiz = _apply_filters(
        db.session.query(NPSSurvey), **filters,
    ).filter(NPSSurvey.category == 'detractor').filter(
        NPSSurvey.why_1.isnot(None)
    ).count()

    return {
        'total': total,
        'promotores': counts['promotor'],
        'pasivos': counts['pasivo'],
        'detractores': counts['detractor'],
        'promotor_pct': promotor_pct,
        'pasivo_pct': pasivo_pct,
        'detractor_pct': detractor_pct,
        'nps': nps,
        'avg_score': avg_score,
        'resolucion_pct': resol_pct,
        'resolucion_count': resol_yes,
        'resolucion_total': resol_total_with,
        'muy_dificil': muy_dificil,
        'con_comentario': con_comentario,
        'con_comentario_pct': con_comentario_pct,
        'top_motivo': top_motivo,
        'top_motivo_count': top_motivo_count,
        'top_responsable': top_resp,
        'top_responsable_count': top_resp_count,
        'con_causa_raiz': con_causa_raiz,
    }


def _empty_dashboard():
    return {k: 0 for k in [
        'total', 'promotores', 'pasivos', 'detractores',
        'promotor_pct', 'pasivo_pct', 'detractor_pct',
        'muy_dificil', 'con_comentario', 'con_comentario_pct',
        'top_motivo_count', 'top_responsable_count', 'con_causa_raiz',
    ]} | {
        'nps': None, 'avg_score': None,
        'resolucion_pct': None, 'resolucion_count': 0, 'resolucion_total': 0,
        'top_motivo': None, 'top_responsable': None,
    }


# ============================================================================
# Distribuciones
# ============================================================================
def gender_breakdown(**filters) -> list[dict]:
    """Participacion + comportamiento NPS por genero."""
    rows = _apply_filters(
        db.session.query(NPSSurvey.gender, NPSSurvey.category, func.count(NPSSurvey.id)),
        **filters,
    ).group_by(NPSSurvey.gender, NPSSurvey.category).all()

    by_g: dict = defaultdict(lambda: {'promotor': 0, 'pasivo': 0, 'detractor': 0})
    for g, cat, n in rows:
        key = g or 'No Detectado'
        if cat in ('promotor', 'pasivo', 'detractor'):
            by_g[key][cat] = n

    total_all = sum(sum(v.values()) for v in by_g.values()) or 1
    out = []
    for g, d in by_g.items():
        tot = d['promotor'] + d['pasivo'] + d['detractor']
        if tot == 0: continue
        out.append({
            'gender': g,
            'total': tot,
            'participation_pct': round(100 * tot / total_all, 1),
            'promotor': d['promotor'],
            'pasivo': d['pasivo'],
            'detractor': d['detractor'],
            'promotor_pct': round(100 * d['promotor'] / tot, 0),
            'pasivo_pct': round(100 * d['pasivo'] / tot, 0),
            'detractor_pct': round(100 * d['detractor'] / tot, 0),
            'nps': round(100 * (d['promotor'] - d['detractor']) / tot, 1),
        })
    out.sort(key=lambda r: -r['total'])
    return out


def unknown_gender_names(**filters) -> list[str]:
    """Primeros nombres no clasificados para que el supervisor los etiquete."""
    from iterum.services.gender import predict_gender
    rows = _apply_filters(
        db.session.query(NPSSurvey.client_name), **filters,
    ).filter(
        NPSSurvey.gender == 'No Detectado'
    ).distinct().limit(200).all()
    seen = set()
    for (name,) in rows:
        if not name: continue
        _, hint = predict_gender(name)
        if hint and hint not in seen:
            seen.add(hint)
    return sorted(seen)


def effort_distribution(**filters) -> list[dict]:
    """5 buckets de esfuerzo."""
    rows = _apply_filters(
        db.session.query(NPSSurvey.effort, func.count(NPSSurvey.id)),
        **filters,
    ).filter(NPSSurvey.effort.isnot(None)).group_by(NPSSurvey.effort).all()
    counts = {'Muy facil': 0, 'Facil': 0, 'Neutro': 0, 'Dificil': 0, 'Muy dificil': 0}
    for e, n in rows:
        if e in counts:
            counts[e] = n
    return [{'effort': k, 'count': v} for k, v in counts.items()]


def resolution_stats(**filters) -> dict:
    q = _apply_filters(
        db.session.query(NPSSurvey.resolution, func.count(NPSSurvey.id)), **filters,
    ).group_by(NPSSurvey.resolution).all()
    counts = {'Si': 0, 'No': 0, 'Parcial': 0, None: 0}
    for r, n in q:
        counts[r] = n
    total_known = counts['Si'] + counts['No'] + counts['Parcial']
    return {
        'resueltos': counts['Si'],
        'sin_resolver': counts['No'],
        'parcial': counts['Parcial'],
        'total': total_known,
        'resueltos_pct': round(100 * counts['Si'] / total_known, 1) if total_known else 0,
    }


# ============================================================================
# Causa Raiz: 4 chart panels
# ============================================================================
def root_cause_analytics(**filters) -> dict:
    """4 distribuciones (tipo, responsabilidad, motivo, origen) + lista encadenada."""
    # Filtrar solo detractores
    filters_det = {**filters, 'category': 'detractor'}

    def _bar(field):
        rows = _apply_filters(
            db.session.query(field, func.count(NPSSurvey.id)),
            **filters_det,
        ).filter(field.isnot(None)).group_by(field).order_by(
            func.count(NPSSurvey.id).desc()
        ).all()
        total = sum(n for _, n in rows) or 1
        return [{
            'label': v,
            'count': n,
            'pct': round(100 * n / total, 0),
        } for v, n in rows]

    return {
        'tipo_causa': _bar(NPSSurvey.root_cause_type),
        'responsabilidad': _bar(NPSSurvey.responsibility),
        'motivo': _bar(NPSSurvey.motive),
        'origen': _bar(NPSSurvey.origin),
    }


def root_cause_chain(**filters) -> list[dict]:
    """Top detractores con porques encadenados (porque_1 != null)."""
    filters_det = {**filters, 'category': 'detractor'}
    rows = _apply_filters(
        db.session.query(NPSSurvey), **filters_det,
    ).filter(NPSSurvey.why_1.isnot(None)).order_by(
        NPSSurvey.response_date.desc()
    ).limit(20).all()
    return [{
        'id': r.id,
        'agent_name': r.agent_name,
        'cell': r.cell,
        'root_cause_type': r.root_cause_type,
        'responsibility': r.responsibility,
        'problem_description': r.problem_description,
        'why_1': r.why_1, 'why_2': r.why_2, 'why_3': r.why_3,
    } for r in rows]


# ============================================================================
# Patrones: keyword detection + structured origen
# ============================================================================
KEYWORDS = {
    'Tiempo de respuesta / demora': ['tarda', 'demora', 'lento', 'esperar', 'minutos', 'horas', 'dias', 'días', 'retorno', 'tarde', 'rapid', 'rápid'],
    'No resolución del problema': ['no resuelv', 'no solucion', 'sin solución', 'no dan', 'no puede', 'pendiente', 'esperando', 'no me dan'],
    'Cierre de chat / desconexión': ['cierran', 'cerraron', 'desconect', 'cortan', 'chat cerrado'],
    'Transferencias sin contexto': ['derivan', 'transferen', 'otro equipo', 'sin contacto', 'no dan contacto'],
    'Información incorrecta': ['mala información', 'información incorrecta', 'mal asesorado', 'información equivocada'],
    'Falta de asesor humano': ['máquina', 'maquina', 'bot', 'automático', 'automatico', 'quiero hablar', 'persona humana', 'humano'],
    'Problemas de producto/proceso': ['préstamo', 'prestamo', 'intereses', 'reembolso', 'tarjeta', 'pin', 'token', 'débito', 'debito', 'bloqueo'],
    'Atención muy tardía (días)': ['días', 'dias', 'semanas', 'hace días', 'hace dias', 'hace tiempo', 'mucho tiempo'],
}


def keyword_patterns(**filters) -> list[dict]:
    """Detecta categorias de problemas en los comentarios."""
    filters_det = {**filters, 'category': 'detractor'}
    rows = _apply_filters(
        db.session.query(NPSSurvey.comment), **filters_det,
    ).filter(NPSSurvey.comment.isnot(None)).filter(NPSSurvey.comment != '').all()
    total = len(rows)
    if total == 0:
        return []
    comments_lower = [(c or '').lower() for (c,) in rows]
    out = []
    for label, words in KEYWORDS.items():
        matches = sum(1 for c in comments_lower if any(w in c for w in words))
        if matches > 0:
            out.append({
                'label': label, 'count': matches, 'total': total,
                'pct': round(100 * matches / total, 0),
            })
    out.sort(key=lambda r: -r['count'])
    return out


def origin_breakdown(**filters) -> list[dict]:
    """Origen Principal (campo estructurado) — distribucion sobre detractores."""
    filters_det = {**filters, 'category': 'detractor'}
    rows = _apply_filters(
        db.session.query(NPSSurvey.origin, func.count(NPSSurvey.id)),
        **filters_det,
    ).filter(NPSSurvey.origin.isnot(None)).group_by(NPSSurvey.origin).order_by(
        func.count(NPSSurvey.id).desc()
    ).all()
    total = sum(n for _, n in rows) or 1
    return [{'label': k, 'count': n, 'pct': round(100 * n / total, 0)} for k, n in rows]


def top_alert_agents(limit=5, **filters) -> list[dict]:
    """Asesores con mas detractores en el periodo."""
    filters_det = {**filters, 'category': 'detractor'}
    rows = _apply_filters(
        db.session.query(NPSSurvey.agent_name, func.count(NPSSurvey.id)),
        **filters_det,
    ).filter(NPSSurvey.agent_name.isnot(None)).group_by(NPSSurvey.agent_name).order_by(
        func.count(NPSSurvey.id).desc()
    ).limit(limit).all()
    return [{'agent_name': a, 'alerts': n} for a, n in rows]


# ============================================================================
# Auditoria de etiquetado
# ============================================================================
def audit_review_stats(**filters) -> dict:
    """Conteos por review_status."""
    rows = _apply_filters(
        db.session.query(NPSSurvey.review_status, func.count(NPSSurvey.id)), **filters,
    ).filter(NPSSurvey.category == 'detractor').group_by(NPSSurvey.review_status).all()
    counts = {'sin_revisar': 0, 'correcto': 0, 'dudoso': 0, 'incorrecto': 0}
    for s, n in rows:
        if s in counts: counts[s] = n
    total = sum(counts.values())
    revisado = total - counts['sin_revisar']
    return {
        'total': total,
        'sin_revisar': counts['sin_revisar'],
        'correctos': counts['correcto'],
        'dudosos': counts['dudoso'],
        'incorrectos': counts['incorrecto'],
        'progreso_pct': round(100 * revisado / total, 0) if total else 0,
    }


# ============================================================================
# Coaching: agrupacion por asesor
# ============================================================================
def coaching_by_agent(**filters) -> list[dict]:
    """Por cada asesor con detractores: detalle de casos + promotores fortalezas."""
    base = _apply_filters(db.session.query(NPSSurvey), **filters)
    surveys = base.filter(NPSSurvey.agent_name.isnot(None)).all()

    by_agent: dict = defaultdict(lambda: {'detr': [], 'prom': []})
    for s in surveys:
        key = s.agent_name
        if s.category == 'detractor':
            by_agent[key]['detr'].append(s)
        elif s.category == 'promotor':
            by_agent[key]['prom'].append(s)

    out = []
    for agent, data in by_agent.items():
        if not data['detr']:
            continue  # solo agentes con al menos 1 detractor
        n_detr = len(data['detr'])
        n_sin_resolver = sum(1 for s in data['detr'] if s.resolution != 'Si')
        n_sin_cr = sum(1 for s in data['detr'] if not s.why_1)

        # Motivo dominante
        motives = Counter(s.motive for s in data['detr'] if s.motive)
        top_motive = motives.most_common(1)[0] if motives else (None, 0)

        # Urgencia: >= 3 detractores o > 50% sin resolver
        if n_detr >= 3 or (n_detr and n_sin_resolver / n_detr > 0.5):
            urgency = 'urgente'
        elif n_detr >= 2:
            urgency = 'riesgo'
        else:
            urgency = 'normal'

        # Promotores con voz del cliente
        promoter_comments = [s.comment for s in data['prom'] if s.comment][:5]
        avg_prom_score = (sum(s.nps_score for s in data['prom']) / len(data['prom'])) if data['prom'] else None

        out.append({
            'agent_name': agent,
            'urgency': urgency,
            'detractores_count': n_detr,
            'sin_resolver': n_sin_resolver,
            'sin_causa_raiz': n_sin_cr,
            'promotores_count': len(data['prom']),
            'top_motive': top_motive[0],
            'top_motive_count': top_motive[1],
            'detractor_cases': [{
                'id': s.id,
                'response_date': s.response_date.isoformat() if s.response_date else None,
                'motive': s.motive,
                'origin': s.origin,
                'responsibility': s.responsibility,
                'resolution': s.resolution,
                'nps_score': s.nps_score,
                'comment': s.comment,
                'why_1': s.why_1, 'why_2': s.why_2, 'why_3': s.why_3,
                'root_cause_type': s.root_cause_type,
            } for s in data['detr']],
            'avg_promoter_score': round(avg_prom_score, 1) if avg_prom_score is not None else None,
            'promoter_voices': promoter_comments,
        })

    # Orden: urgentes primero, luego por cantidad de detractores
    urgency_order = {'urgente': 0, 'riesgo': 1, 'normal': 2}
    out.sort(key=lambda r: (urgency_order[r['urgency']], -r['detractores_count']))
    return out


def coaching_stats(**filters) -> dict:
    agents = coaching_by_agent(**filters)
    urgentes = sum(1 for a in agents if a['urgency'] == 'urgente')
    en_riesgo = sum(1 for a in agents if a['urgency'] == 'riesgo')
    sin_cr = sum(1 for a in agents if a['sin_causa_raiz'] > 0)

    # Asesores solo con promotores (sin detractores en el periodo)
    all_agents = set()
    for ag, in _apply_filters(
        db.session.query(NPSSurvey.agent_name), **filters,
    ).filter(NPSSurvey.agent_name.isnot(None)).distinct().all():
        all_agents.add(ag)
    agents_with_detr = {a['agent_name'] for a in agents}
    solo_promotores = len(all_agents - agents_with_detr)

    return {
        'asesores_con_detractores': len(agents),
        'urgentes': urgentes,
        'en_riesgo': en_riesgo,
        'sin_causa_raiz': sin_cr,
        'solo_promotores': solo_promotores,
    }
