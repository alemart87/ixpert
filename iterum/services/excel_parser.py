"""Parser de XLSX a filas normalizadas de NPS.

Tolera variaciones de columnas (banco no controla exactamente como exporta el
sistema upstream). Reusa el patron de _map_headers / _normalize_header de
admin.py para mapear flexible -> canonico.

Columnas canonicas esperadas:
- response_date  : datetime
- channel        : whatsapp | call
- cell           : string (celula operativa)
- agent_name     : string
- agent_doc      : string (documento del asesor)
- nps_score      : int 0-10
- comment        : string (opcional)
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, date
from typing import Iterable

# openpyxl es la unica dependencia nueva. read_only=True para no cargar la
# planilla entera a memoria — la procesamos en streaming.
import openpyxl  # type: ignore


# Aliases tolerantes para mapeo de columnas. Todos en lowercase sin acentos.
HEADER_ALIASES = {
    'response_date': {
        'fecha', 'fecha respuesta', 'fecha de respuesta', 'fecha encuesta',
        'date', 'timestamp', 'fecha hora', 'fecha y hora',
    },
    'channel': {
        'canal', 'channel', 'medio', 'tipo', 'tipo canal', 'canal contacto',
    },
    'cell': {
        'celula', 'célula', 'cell', 'equipo', 'grupo', 'sector', 'celula operativa',
    },
    'agent_name': {
        'asesor', 'agente', 'agent', 'nombre asesor', 'nombre agente',
        'operador', 'representante', 'ejecutivo',
    },
    'agent_doc': {
        'documento', 'doc', 'dni', 'cedula', 'cédula', 'ci', 'legajo',
        'id asesor', 'id agente',
    },
    'nps_score': {
        'nps', 'score', 'puntaje', 'nota', 'calificacion', 'calificación',
        'rating', 'puntuacion', 'puntuación',
    },
    'comment': {
        'comentario', 'comment', 'feedback', 'observacion', 'observación',
        'opinion', 'opinión', 'mensaje',
    },
}


def _normalize_header(s: str) -> str:
    """minusculas + sin acentos + colapsa espacios."""
    if s is None:
        return ''
    s = str(s).strip().lower()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r'\s+', ' ', s)
    return s


def _map_headers(headers: list[str]) -> dict[str, int]:
    """Devuelve {campo_canonico: indice_columna}."""
    mapping: dict[str, int] = {}
    for idx, raw in enumerate(headers):
        norm = _normalize_header(raw)
        for canonical, aliases in HEADER_ALIASES.items():
            if canonical in mapping:
                continue
            if norm == canonical or norm in aliases:
                mapping[canonical] = idx
                break
    return mapping


def _categorize_nps(score: int | None) -> str | None:
    """Clasifica un score NPS en promotor/pasivo/detractor."""
    if score is None:
        return None
    if score >= 9:
        return 'promotor'
    if score >= 7:
        return 'pasivo'
    if score >= 0:
        return 'detractor'
    return None


def _normalize_channel(raw) -> str | None:
    if raw is None:
        return None
    s = _normalize_header(str(raw))
    if any(k in s for k in ('whats', 'wpp', 'wsp', 'wa')):
        return 'whatsapp'
    if any(k in s for k in ('llamada', 'call', 'telef', 'phone', 'voz')):
        return 'call'
    return s[:20] or None


def _parse_date(raw):
    if raw is None or raw == '':
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, date):
        return datetime(raw.year, raw.month, raw.day)
    s = str(raw).strip()
    # Formatos comunes en bancos paraguayos
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d',
                '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M',
                '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_score(raw):
    if raw is None or raw == '':
        return None
    try:
        n = int(float(raw))
        if 0 <= n <= 10:
            return n
    except (ValueError, TypeError):
        pass
    return None


def parse_xlsx_stream(path: str) -> Iterable[dict]:
    """Generator de filas normalizadas. Lanza ValueError si el formato es invalido.

    Uso:
        for row in parse_xlsx_stream('/tmp/x.xlsx'):
            ...
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.active
        rows = ws.iter_rows(values_only=True)

        # Primera fila no vacia = headers
        headers = None
        for row in rows:
            if row and any(c is not None and str(c).strip() for c in row):
                headers = list(row)
                break
        if not headers:
            raise ValueError('La planilla esta vacia o no tiene encabezados.')

        mapping = _map_headers(headers)
        required = {'response_date', 'nps_score'}
        missing = required - set(mapping.keys())
        if missing:
            raise ValueError(
                f'Faltan columnas obligatorias: {", ".join(sorted(missing))}. '
                f'Encabezados detectados: {", ".join(str(h) for h in headers if h)}'
            )

        for row in rows:
            if not row or all(c is None or c == '' for c in row):
                continue

            def get(key):
                idx = mapping.get(key)
                if idx is None or idx >= len(row):
                    return None
                return row[idx]

            score = _parse_score(get('nps_score'))
            response_date = _parse_date(get('response_date'))
            if score is None or response_date is None:
                # Se cuenta como rows_invalid en el caller
                yield {'_invalid': True}
                continue

            yield {
                'response_date': response_date,
                'channel': _normalize_channel(get('channel')),
                'cell': (str(get('cell')).strip() if get('cell') else None),
                'agent_name': (str(get('agent_name')).strip() if get('agent_name') else None),
                'agent_doc': (str(get('agent_doc')).strip() if get('agent_doc') else None),
                'nps_score': score,
                'category': _categorize_nps(score),
                'comment': (str(get('comment')).strip() if get('comment') else None),
            }
    finally:
        wb.close()
