"""Generacion de reporte ejecutivo: HTML + PDF nativo (WeasyPrint)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO

from flask import render_template

from models import db
from iterum.models import NPSReportSnapshot
from iterum.services import scoring


def build_report_payload(**filters) -> dict:
    """Calcula todos los KPIs necesarios para el reporte. Pura, sin side effects."""
    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'filters': {k: (v.isoformat() if hasattr(v, 'isoformat') else v)
                    for k, v in filters.items() if v is not None},
        'kpis': scoring.dashboard_kpis(**filters),
        'channels': scoring.channel_breakdown(**filters),
        'cells': scoring.cell_breakdown(**filters),
        'ranking_top': scoring.agent_ranking(limit=10, **filters),
        'timeseries': scoring.nps_timeseries(granularity='week', **filters),
    }


def render_report_html(payload: dict, *, period_label: str = '') -> str:
    """Renderiza el HTML standalone (no usa base.html, autocontenido)."""
    return render_template(
        'iterum/report_standalone.html',
        payload=payload,
        period_label=period_label,
    )


def save_snapshot(*, generated_by_id: int, period_label: str,
                  filters: dict, payload: dict, html: str) -> NPSReportSnapshot:
    snap = NPSReportSnapshot(
        generated_by_id=generated_by_id,
        period_label=period_label,
        filters_json=json.dumps(filters, ensure_ascii=False, default=str),
        payload_json=json.dumps(payload, ensure_ascii=False, default=str),
        html_blob=html,
    )
    db.session.add(snap)
    db.session.commit()
    return snap


def render_pdf(html: str) -> bytes:
    """Convierte HTML a PDF usando WeasyPrint.

    WeasyPrint requiere libpango/libcairo en el sistema (instalado en Dockerfile).
    Si la libreria no esta disponible, lanza ImportError — caller debe responder
    503 con fallback a print del navegador.
    """
    # Import lazy: si weasyprint no esta instalado, falla solo al pedir PDF
    from weasyprint import HTML  # type: ignore
    buf = BytesIO()
    HTML(string=html).write_pdf(buf)
    return buf.getvalue()
