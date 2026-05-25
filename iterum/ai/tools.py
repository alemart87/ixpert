"""Tools que el agente puede invocar.

Cada tool envuelve un servicio de iterum/services/* y devuelve dict/list
serializable. El SDK auto-genera el JSON Schema a partir de los type hints.

Hay 3 grupos:
- Lectura: consultan la DB, no mutan
- Canvas: actualizan el workspace compartido (admin lo ve en vivo)
- Gestion (mutaciones): cambian datos de produccion (auditoria/coaching/causa raiz)
"""
from __future__ import annotations

import json
from datetime import datetime, date
from typing import Annotated

from agents import function_tool

from models import db
from iterum.models import NPSSurvey
from iterum.services import analytics, scoring, audit as audit_svc, root_cause as rc_svc, coaching as coach_svc
from iterum.ai.models import IterumAICanvas


# ============================================================================
# Helpers
# ============================================================================
def _parse_filters(channel=None, cell=None, agent_doc=None,
                   from_date=None, to_date=None) -> dict:
    f = {}
    if channel: f['channel'] = channel
    if cell: f['cell'] = cell
    if agent_doc: f['agent_doc'] = agent_doc
    if from_date:
        try: f['from_date'] = datetime.fromisoformat(from_date).date()
        except Exception: pass
    if to_date:
        try: f['to_date'] = datetime.fromisoformat(to_date).date()
        except Exception: pass
    return f


# Context: chat_id (lo seteamos antes de cada run para que las tools del canvas
# sepan en que workspace escribir). Thread-local seria ideal pero por ahora
# usamos un dict simple por request.
_ctx: dict = {'chat_id': None}


def set_ctx(chat_id: int):
    _ctx['chat_id'] = chat_id


# ============================================================================
# LECTURA
# ============================================================================
@function_tool
def get_dashboard_kpis(
    channel: Annotated[str | None, 'Filtro canal: whatsapp | call'] = None,
    cell: Annotated[str | None, 'Filtro celula operativa'] = None,
    from_date: Annotated[str | None, 'Fecha desde YYYY-MM-DD'] = None,
    to_date: Annotated[str | None, 'Fecha hasta YYYY-MM-DD'] = None,
) -> dict:
    """KPIs principales: NPS, promotores/detractores, resolucion %, esfuerzo,
    top motivo detractor, principal responsable, con causa raiz. Filtrable
    por canal, celula y rango de fechas. Devuelve nps_target=77 para comparar."""
    f = _parse_filters(channel=channel, cell=cell, from_date=from_date, to_date=to_date)
    kpis = analytics.dashboard_full(**f)
    return {**kpis, 'nps_target': analytics.OBJETIVO_NPS_CANAL}


@function_tool
def get_ranking(
    sort: Annotated[str, 'Ordenar por: nps|promotores|detractores|resolucion|esfuerzo|total'] = 'nps',
    channel: str | None = None,
    cell: str | None = None,
    limit: Annotated[int, 'Maximo de asesores a devolver'] = 30,
) -> list[dict]:
    """Ranking de asesores ordenable. Devuelve nombre, celula dominante,
    NPS, P/D, resolucion% y esfuerzo% por asesor."""
    f = _parse_filters(channel=channel, cell=cell)
    return scoring.agent_ranking(limit=limit, sort=sort, **f)


@function_tool
def get_agent_detail(
    agent_name: Annotated[str, 'Username del asesor (ej GERARDOB)'],
) -> dict:
    """Detalle completo de un asesor: KPIs propios + ultimos 5 detractores
    con causa raiz, ultimos 5 promotores. Util para coaching."""
    # KPIs filtrando por agente
    base_filters = {'agent_doc': agent_name}
    kpis = analytics.dashboard_full(**base_filters)

    surveys = NPSSurvey.query.filter(
        (NPSSurvey.agent_name == agent_name) | (NPSSurvey.agent_doc == agent_name)
    ).order_by(NPSSurvey.response_date.desc()).all()

    detractors = [s for s in surveys if s.category == 'detractor'][:5]
    promoters = [s for s in surveys if s.category == 'promotor'][:5]

    def _ser(s):
        return {
            'id': s.id,
            'date': s.response_date.isoformat() if s.response_date else None,
            'cell': s.cell, 'channel': s.channel,
            'nps_score': s.nps_score,
            'comment': s.comment,
            'motive': s.motive, 'origin': s.origin,
            'responsibility': s.responsibility,
            'root_cause_type': s.root_cause_type,
            'why_1': s.why_1, 'why_2': s.why_2, 'why_3': s.why_3,
            'resolution': s.resolution, 'effort': s.effort,
        }
    return {
        'agent_name': agent_name,
        'kpis': kpis,
        'recent_detractors': [_ser(s) for s in detractors],
        'recent_promoters': [_ser(s) for s in promoters],
        'total_surveys': len(surveys),
    }


@function_tool
def get_top_detractors(
    limit: Annotated[int, 'Cuantos casos devolver'] = 10,
    channel: str | None = None,
    cell: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    """Los peores detractores recientes con comentario completo, motivo,
    causa raiz y porques. Util para entender que esta pasando."""
    f = _parse_filters(channel=channel, cell=cell, from_date=from_date, to_date=to_date)
    f['category'] = 'detractor'
    chain = analytics.root_cause_chain(**f)
    return chain[:limit]


@function_tool
def get_keyword_patterns(
    channel: str | None = None,
    cell: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    """Patrones detectados: 8 categorias de problemas (demora, no resuelv, cierre
    chat, etc) + distribucion de Origen Principal estructurado + top alertas."""
    f = _parse_filters(channel=channel, cell=cell, from_date=from_date, to_date=to_date)
    return {
        'keywords': analytics.keyword_patterns(**f),
        'origin': analytics.origin_breakdown(**f),
        'top_alerts': analytics.top_alert_agents(**f),
    }


@function_tool
def get_root_cause_breakdown(
    channel: str | None = None,
    cell: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    """4 distribuciones sobre detractores: tipo de causa raiz, responsabilidad
    (asesor/proceso/externo/servicio), motivo del cliente, origen principal."""
    f = _parse_filters(channel=channel, cell=cell, from_date=from_date, to_date=to_date)
    return analytics.root_cause_analytics(**f)


@function_tool
def get_coaching_panel(
    channel: str | None = None,
    cell: str | None = None,
) -> dict:
    """Panel de coaching: stats + lista de asesores con detractores agrupados
    por urgencia (urgente/riesgo/normal). Cada uno trae casos + fortalezas."""
    f = _parse_filters(channel=channel, cell=cell)
    return {
        'stats': analytics.coaching_stats(**f),
        'agents': analytics.coaching_by_agent(**f),
    }


@function_tool
def search_comments(
    query: Annotated[str, 'Texto a buscar en los comentarios'],
    category: Annotated[str | None, 'Filtrar por: promotor|pasivo|detractor'] = None,
    limit: int = 20,
) -> list[dict]:
    """Busqueda textual en los comentarios libres de los clientes."""
    q = NPSSurvey.query.filter(NPSSurvey.comment.ilike(f'%{query}%'))
    if category in ('promotor', 'pasivo', 'detractor'):
        q = q.filter(NPSSurvey.category == category)
    rows = q.order_by(NPSSurvey.response_date.desc()).limit(limit).all()
    return [{
        'id': r.id, 'date': r.response_date.isoformat() if r.response_date else None,
        'agent_name': r.agent_name, 'cell': r.cell, 'channel': r.channel,
        'category': r.category, 'nps_score': r.nps_score, 'comment': r.comment,
    } for r in rows]


@function_tool
def compare_periods(
    period_a_from: Annotated[str, 'Inicio periodo A (YYYY-MM-DD)'],
    period_a_to: Annotated[str, 'Fin periodo A (YYYY-MM-DD)'],
    period_b_from: Annotated[str, 'Inicio periodo B (YYYY-MM-DD)'],
    period_b_to: Annotated[str, 'Fin periodo B (YYYY-MM-DD)'],
    channel: str | None = None,
    cell: str | None = None,
) -> dict:
    """Compara dos ventanas temporales. Devuelve KPIs de A, KPIs de B y deltas
    en cada metrica (NPS, resolucion, motivos, etc.)."""
    fa = _parse_filters(channel=channel, cell=cell,
                        from_date=period_a_from, to_date=period_a_to)
    fb = _parse_filters(channel=channel, cell=cell,
                        from_date=period_b_from, to_date=period_b_to)
    a = analytics.dashboard_full(**fa)
    b = analytics.dashboard_full(**fb)

    def _delta(k):
        va, vb = a.get(k), b.get(k)
        if va is None or vb is None: return None
        try: return round(vb - va, 1)
        except Exception: return None

    return {
        'period_a': {'from': period_a_from, 'to': period_a_to, 'kpis': a},
        'period_b': {'from': period_b_from, 'to': period_b_to, 'kpis': b},
        'delta': {k: _delta(k) for k in
                  ['nps', 'avg_score', 'resolucion_pct', 'detractor_pct',
                   'promotor_pct', 'total']},
    }


# ============================================================================
# CANVAS — workspace compartido con el admin
# ============================================================================
def _get_or_create_canvas(chat_id: int) -> IterumAICanvas:
    c = IterumAICanvas.query.filter_by(chat_id=chat_id).first()
    if not c:
        c = IterumAICanvas(chat_id=chat_id, content_md='', version=1)
        db.session.add(c)
        db.session.commit()
    return c


@function_tool
def canvas_write(
    content_md: Annotated[str, 'Contenido en Markdown a escribir en el canvas (reemplaza todo)'],
    title: Annotated[str | None, 'Titulo opcional del workspace'] = None,
) -> dict:
    """Sobrescribe el workspace del admin con contenido markdown. Usar para
    presentar planes de accion estructurados, listados de asesores priorizados,
    drafts de comunicaciones, tablas, etc. El admin lo ve en vivo y puede editarlo."""
    chat_id = _ctx.get('chat_id')
    if not chat_id:
        return {'error': 'no chat_id en contexto'}
    c = _get_or_create_canvas(chat_id)
    c.content_md = content_md
    if title:
        c.title = title[:200]
    c.version = (c.version or 0) + 1
    db.session.commit()
    return {'ok': True, 'version': c.version, 'chars': len(content_md)}


@function_tool
def canvas_append(
    content_md: Annotated[str, 'Markdown a agregar al final del canvas'],
) -> dict:
    """Agrega contenido al final del workspace sin borrar lo que ya esta."""
    chat_id = _ctx.get('chat_id')
    if not chat_id:
        return {'error': 'no chat_id en contexto'}
    c = _get_or_create_canvas(chat_id)
    sep = '\n\n' if c.content_md else ''
    c.content_md = (c.content_md or '') + sep + content_md
    c.version = (c.version or 0) + 1
    db.session.commit()
    return {'ok': True, 'version': c.version, 'chars': len(c.content_md)}


@function_tool
def canvas_read() -> dict:
    """Lee el contenido actual del workspace (incluyendo ediciones manuales del admin)."""
    chat_id = _ctx.get('chat_id')
    if not chat_id:
        return {'error': 'no chat_id en contexto'}
    c = IterumAICanvas.query.filter_by(chat_id=chat_id).first()
    if not c:
        return {'content_md': '', 'version': 0, 'title': 'Workspace'}
    return {'content_md': c.content_md or '', 'version': c.version, 'title': c.title}


# ============================================================================
# GESTION (mutaciones)
# ============================================================================
@function_tool
def set_audit_review(
    survey_id: Annotated[int, 'ID de la encuesta a marcar'],
    status: Annotated[str, 'correcto | dudoso | incorrecto'],
    note: Annotated[str | None, 'Nota opcional explicando el veredicto'] = None,
) -> dict:
    """Marca el etiquetado de una encuesta como correcto/dudoso/incorrecto en
    la auditoria de causa raiz. Solo usar cuando el admin lo pide explicitamente
    o cuando hay evidencia clara de error en el tagging."""
    if status not in ('correcto', 'dudoso', 'incorrecto', 'sin_revisar'):
        return {'error': f'status invalido: {status}'}
    from datetime import datetime, timezone
    s = db.session.get(NPSSurvey, survey_id)
    if not s: return {'error': f'survey {survey_id} no existe'}
    s.review_status = status
    s.review_note = note
    s.reviewed_at = datetime.now(timezone.utc)
    db.session.commit()
    return {'ok': True, 'survey_id': survey_id, 'status': status}


@function_tool
def create_coaching_session(
    agent_name: Annotated[str, 'Username del asesor'],
    topic: Annotated[str, 'Tema de la sesion (ej: empatia, manejo de quejas)'],
    urgency: Annotated[str, 'urgente | riesgo | normal'] = 'normal',
    notes: str | None = None,
) -> dict:
    """Crea una ficha de coaching para un asesor. La urgencia debe estar
    justificada con datos (ej: 3+ detractores en la semana, repetir motivo)."""
    if urgency not in ('urgente', 'riesgo', 'normal'):
        urgency = 'normal'
    # Mapeo a la convencion de NPSCoaching (low/med/high)
    urg_map = {'urgente': 'high', 'riesgo': 'med', 'normal': 'low'}
    user_id = _ctx.get('user_id')
    if not user_id:
        return {'error': 'no user_id en contexto'}
    c = coach_svc.create_coaching(
        agent_doc=agent_name, coach_id=user_id,
        agent_name=agent_name, topic=topic,
        urgency=urg_map[urgency], notes=notes,
    )
    return {'ok': True, 'coaching_id': c.id, 'agent_name': agent_name, 'urgency': urgency}


@function_tool
def add_root_cause_analysis(
    survey_id: Annotated[int, 'ID de la encuesta detractora'],
    why_1: Annotated[str, 'Primer porque'],
    why_2: Annotated[str | None, 'Segundo porque (opcional)'] = None,
    why_3: Annotated[str | None, 'Tercer porque (causa raiz)'] = None,
    root_cause_text: Annotated[str | None, 'Resumen de la causa raiz en una oracion'] = None,
    status: Annotated[str, 'open | in_progress | done'] = 'open',
) -> dict:
    """Registra un analisis de 5 porques para un caso detractor que no lo tenia."""
    user_id = _ctx.get('user_id')
    if not user_id:
        return {'error': 'no user_id en contexto'}
    whys = [w for w in [why_1, why_2, why_3] if w]
    try:
        rc = rc_svc.upsert_root_cause(
            survey_id=survey_id, created_by_id=user_id,
            whys=whys, root_cause=root_cause_text, status=status,
        )
        return {'ok': True, 'root_cause_id': rc.id, 'survey_id': survey_id}
    except ValueError as e:
        return {'error': str(e)}


# ============================================================================
# Lista de todas las tools para registrar en el Agent
# ============================================================================
ALL_TOOLS = [
    # Lectura
    get_dashboard_kpis,
    get_ranking,
    get_agent_detail,
    get_top_detractors,
    get_keyword_patterns,
    get_root_cause_breakdown,
    get_coaching_panel,
    search_comments,
    compare_periods,
    # Canvas
    canvas_write,
    canvas_append,
    canvas_read,
    # Mutaciones
    set_audit_review,
    create_coaching_session,
    add_root_cause_analysis,
]
