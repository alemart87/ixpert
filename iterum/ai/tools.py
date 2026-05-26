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
from pydantic import BaseModel, Field

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
# FRAMEWORKS DE ANALISIS (devuelven markdown listo para el canvas)
# ============================================================================
@function_tool
def generate_ishikawa_estimate(
    channel: str | None = None,
    cell: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    """Genera un diagrama Ishikawa (6M) tentativo de las causas raiz del NPS bajo,
    cruzando los datos disponibles. Devuelve markdown listo para canvas con un
    flowchart mermaid + interpretacion. Las 6 categorias adaptadas a CX bancario:
    Persona (asesor), Proceso, Producto, Plataforma, Politica, Cliente.

    Es una HIPOTESIS analitica basada en patrones; el admin debe validar."""
    from collections import Counter
    f = _parse_filters(channel=channel, cell=cell,
                       from_date=from_date, to_date=to_date)
    kpis = analytics.dashboard_full(**f)
    detractors = NPSSurvey.query.filter(NPSSurvey.category == 'detractor')
    if f.get('channel'): detractors = detractors.filter(NPSSurvey.channel == f['channel'])
    if f.get('cell'): detractors = detractors.filter(NPSSurvey.cell == f['cell'])
    if f.get('from_date'): detractors = detractors.filter(NPSSurvey.response_date >= f['from_date'])
    if f.get('to_date'): detractors = detractors.filter(NPSSurvey.response_date < f['to_date'])
    rows = detractors.limit(500).all()

    # Heuristica de clasificacion por palabras en motivo/origen/comment
    classify = {'Persona': 0, 'Proceso': 0, 'Producto': 0,
                'Plataforma': 0, 'Politica': 0, 'Cliente': 0}
    examples: dict[str, list[str]] = {k: [] for k in classify}
    KEYWORDS = {
        'Persona': ['asesor', 'mal trato', 'empatia', 'capacitacion', 'comunicacion', 'atencion'],
        'Proceso': ['demora', 'tarda', 'tiempo', 'retorno', 'derivacion', 'transferir', 'sla'],
        'Producto': ['producto', 'prestamo', 'tarjeta', 'comision', 'tasa', 'limite'],
        'Plataforma': ['app', 'sistema', 'web', 'caido', 'error', 'tecnico', 'pin', 'token'],
        'Politica': ['regla', 'politica', 'restriccion', 'requisito', 'aprobacion'],
        'Cliente': ['informado', 'no entiende', 'expectativa', 'desconoc'],
    }
    for s in rows:
        haystack = ' '.join(filter(None, [
            (s.comment or '').lower(),
            (s.motive or '').lower(),
            (s.origin or '').lower(),
            (s.root_cause_type or '').lower(),
        ]))
        for cat, words in KEYWORDS.items():
            if any(w in haystack for w in words):
                classify[cat] += 1
                if s.comment and len(examples[cat]) < 3:
                    examples[cat].append(s.comment[:120])
                break
    total_clasificados = sum(classify.values()) or 1

    md = f"""# Ishikawa (6M) — Hipotesis de causa raiz NPS

**NPS actual:** {kpis.get('nps', '—')}% · **Detractores:** {kpis.get('detractores', 0)} · **Resolucion:** {kpis.get('resolucion_pct') or '—'}%

```flowchart
LR
  ROOT[NPS por debajo del objetivo 77%]
  PERS[Persona<br/>{classify['Persona']} casos] --> ROOT
  PROC[Proceso<br/>{classify['Proceso']} casos] --> ROOT
  PROD[Producto<br/>{classify['Producto']} casos] --> ROOT
  PLAT[Plataforma<br/>{classify['Plataforma']} casos] --> ROOT
  POLI[Politica<br/>{classify['Politica']} casos] --> ROOT
  CLI[Cliente<br/>{classify['Cliente']} casos] --> ROOT
  style ROOT fill:#002776,stroke:#c8a247,color:#fff,stroke-width:2px
  style PERS fill:#fef2f2,stroke:#dc2626
  style PROC fill:#fffbeb,stroke:#d97706
  style PROD fill:#f0fdf4,stroke:#16a34a
  style PLAT fill:#eff6ff,stroke:#1e40af
  style POLI fill:#fdf4ff,stroke:#a21caf
  style CLI fill:#f8fafc,stroke:#64748b
```

## Interpretacion por categoria
"""
    for cat, count in sorted(classify.items(), key=lambda x: -x[1]):
        pct = round(100 * count / total_clasificados)
        md += f"\n### {cat} ({count} casos · {pct}%)\n"
        if examples[cat]:
            for ex in examples[cat]:
                md += f"- > {ex}\n"
        else:
            md += "_Sin ejemplos clasificados._\n"
    md += """
## Lectura
La categoria con mas casos NO es necesariamente la causa raiz unica; suele ser un sintoma.
Cruza con `add_root_cause_analysis(survey_id, ...)` para profundizar en cada caso critico.
"""
    return {'markdown': md, 'classification': classify, 'total': total_clasificados}


@function_tool
def generate_pareto_motives(
    top_n: Annotated[int, 'Cantidad de items en el Pareto'] = 10,
    channel: str | None = None,
    cell: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    """Analisis de Pareto (80/20) sobre los motivos de detractores. Devuelve
    una tabla acumulada que muestra cuales pocos motivos generan la mayoria de
    los casos. Util para priorizar acciones."""
    from collections import Counter
    f = _parse_filters(channel=channel, cell=cell,
                       from_date=from_date, to_date=to_date)
    q = NPSSurvey.query.filter(NPSSurvey.category == 'detractor')
    if f.get('channel'): q = q.filter(NPSSurvey.channel == f['channel'])
    if f.get('cell'): q = q.filter(NPSSurvey.cell == f['cell'])
    if f.get('from_date'): q = q.filter(NPSSurvey.response_date >= f['from_date'])
    if f.get('to_date'): q = q.filter(NPSSurvey.response_date < f['to_date'])
    rows = q.all()

    motives = Counter(s.motive for s in rows if s.motive)
    cells = Counter(s.cell for s in rows if s.cell)
    agents = Counter(s.agent_name for s in rows if s.agent_name)

    def _pareto(counter, n):
        items = counter.most_common(n)
        total = sum(counter.values()) or 1
        out, cum = [], 0
        for label, count in items:
            pct = round(100 * count / total, 1)
            cum += pct
            out.append({'label': label, 'count': count, 'pct': pct, 'cum_pct': round(cum, 1)})
        return out, total

    pm, ptm = _pareto(motives, top_n)
    pc, ptc = _pareto(cells, top_n)
    pa, pta = _pareto(agents, top_n)

    def _table(rows, header):
        if not rows:
            return f'_{header}: sin datos_\n\n'
        s = f'### {header}\n\n| # | {header} | Casos | % | Acum % |\n|---|---|---|---|---|\n'
        for i, r in enumerate(rows, 1):
            s += f"| {i} | {r['label']} | {r['count']} | {r['pct']}% | {r['cum_pct']}% |\n"
        s += '\n'
        return s

    md = f"""# Analisis de Pareto (80/20) — Detractores

Total detractores analizados: **{len(rows)}**

{_table(pm, 'Motivo')}
{_table(pc, 'Celula')}
{_table(pa, 'Asesor')}

## Lectura
Foco los motivos cuya **Acum %** llega al ~80%. Suelen ser 2-4 items que concentran
la mayoria del problema. Ataca esos primero — mueven la aguja.
"""
    return {
        'markdown': md,
        'motives': pm, 'cells': pc, 'agents': pa,
        'totals': {'motives': ptm, 'cells': ptc, 'agents': pta},
    }


class ImpactEffortAction(BaseModel):
    action: str = Field(description='Texto descriptivo de la accion')
    impact: str = Field(description='alto | medio | bajo')
    effort: str = Field(description='alto | medio | bajo')


@function_tool
def generate_impact_effort_matrix(
    actions: Annotated[list[ImpactEffortAction], 'Lista de acciones con impact y effort'],
) -> dict:
    """Clasifica una lista de acciones en 4 cuadrantes (Impacto x Esfuerzo)
    para priorizar. Devuelve markdown con tabla por cuadrante. El modelo arma
    la lista de acciones a partir de las recomendaciones derivadas del analisis.
    Cada accion debe tener: action (texto), impact (alto/medio/bajo), effort (id)."""
    QUADRANTS = {
        'quick_wins': {'label': 'Quick Wins (alto impacto / bajo esfuerzo)', 'items': [], 'color': '#16a34a'},
        'big_bets': {'label': 'Big Bets (alto impacto / alto esfuerzo)', 'items': [], 'color': '#1e40af'},
        'fill_ins': {'label': 'Fill-Ins (bajo impacto / bajo esfuerzo)', 'items': [], 'color': '#fbbf24'},
        'time_wasters': {'label': 'Time Wasters (bajo impacto / alto esfuerzo)', 'items': [], 'color': '#dc2626'},
    }
    def _bucket(a):
        impact = (a.impact or '').lower()
        effort = (a.effort or '').lower()
        hi_imp = impact in ('alto', 'high', 'a')
        hi_eff = effort in ('alto', 'high', 'a')
        if hi_imp and not hi_eff: return 'quick_wins'
        if hi_imp and hi_eff: return 'big_bets'
        if not hi_imp and not hi_eff: return 'fill_ins'
        return 'time_wasters'

    for a in (actions or []):
        QUADRANTS[_bucket(a)]['items'].append(a.action)

    md = """# Matriz de Impacto vs Esfuerzo

Prioriza primero los **Quick Wins**. Despues los **Big Bets** con plan formal.
Evita Time Wasters salvo que sean obligatorios por compliance.

| Cuadrante | Acciones |
|-----------|----------|
"""
    for key in ('quick_wins', 'big_bets', 'fill_ins', 'time_wasters'):
        q = QUADRANTS[key]
        items = '<br/>'.join(f'• {a}' for a in q['items']) or '_(vacio)_'
        md += f"| **{q['label']}** | {items} |\n"

    md += """
## Siguiente paso recomendado
1. Empezar la semana 1 con todos los Quick Wins
2. Asignar owner+fecha a los Big Bets, dividirlos en milestones
3. Revisar matriz en 30 dias y reclasificar
"""
    return {'markdown': md, 'quadrants': {k: v['items'] for k, v in QUADRANTS.items()}}


@function_tool
def generate_executive_summary(
    period_label: Annotated[str, 'Etiqueta del periodo (ej: "Semana 21 · Mayo 2026")'],
    channel: str | None = None,
    cell: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    """Genera un resumen ejecutivo estructurado del periodo seleccionado,
    formato 1 pagina para directivos. Incluye: situacion, hallazgos, riesgos,
    acciones recomendadas y proximo punto de control. Devuelve markdown."""
    f = _parse_filters(channel=channel, cell=cell,
                       from_date=from_date, to_date=to_date)
    kpis = analytics.dashboard_full(**f)
    rc = analytics.root_cause_analytics(**f)
    top_alerts = analytics.top_alert_agents(limit=5, **f)
    keywords = analytics.keyword_patterns(**f)
    target = analytics.OBJETIVO_NPS_CANAL
    gap = (target - (kpis.get('nps') or 0)) if kpis.get('nps') is not None else None

    def _top(items, n=3):
        return [(it.get('label'), it.get('count')) for it in (items or [])[:n]]

    motivos_top = _top(rc.get('motivo', []))
    causas_top = _top(rc.get('tipo_causa', []))
    keywords_top = _top(keywords, 3)

    md = f"""# Resumen ejecutivo — {period_label}

## 1. Situacion
- **NPS:** {kpis.get('nps', '—')}% (objetivo {target}%)
- **Gap vs objetivo:** {f'-{gap:.1f} pts' if gap is not None and gap > 0 else 'al objetivo o por encima'}
- **Encuestas:** {kpis.get('total', 0)} · Promotores {kpis.get('promotores', 0)} · Detractores {kpis.get('detractores', 0)}
- **Resolucion en primer contacto:** {kpis.get('resolucion_pct') or '—'}%
- **Esfuerzo alto (muy dificil):** {kpis.get('muy_dificil', 0)} casos

## 2. Hallazgos principales
"""
    if motivos_top:
        md += "**Motivos del cliente mas recurrentes (detractores):**\n"
        for label, count in motivos_top:
            md += f"- {label}: {count} casos\n"
    if causas_top:
        md += "\n**Tipos de causa raiz identificados:**\n"
        for label, count in causas_top:
            md += f"- {label}: {count} casos\n"
    if keywords_top:
        md += "\n**Patrones detectados en comentarios libres:**\n"
        for label, count in keywords_top:
            md += f"- {label}: {count} menciones\n"

    md += "\n## 3. Asesores que demandan accion inmediata\n"
    if top_alerts:
        md += "| Asesor | Alertas |\n|---|---|\n"
        for a in top_alerts:
            md += f"| {a['agent_name']} | {a['alerts']} |\n"
    else:
        md += "_Sin alertas individuales destacadas._\n"

    md += """
## 4. Acciones recomendadas (proximos 7 dias)
1. Coaching express con los asesores listados arriba.
2. Auditar el motivo #1 del Pareto, mapear el flujo y ajustar SLA.
3. Cerrar el ciclo con los detractores no resueltos (callback).

## 5. Proximo punto de control
Revisar este mismo resumen en 7 dias. Esperable: bajar 2-3 pts el gap.
"""
    return {'markdown': md, 'kpis': kpis, 'gap': gap}


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
    # Frameworks de analisis
    generate_ishikawa_estimate,
    generate_pareto_motives,
    generate_impact_effort_matrix,
    generate_executive_summary,
    # Canvas
    canvas_write,
    canvas_append,
    canvas_read,
    # Mutaciones
    set_audit_review,
    create_coaching_session,
    add_root_cause_analysis,
]
