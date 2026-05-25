"""Parser de XLSX a filas normalizadas de NPS.

Tolera variaciones de columnas (banco no controla exactamente como exporta el
sistema upstream). Matching token-based: se busca cualquier token disparador
en los tokens del header (separados por espacios/underscores/parentesis), asi
"FECHA_REGISTRADA (-04:00 GMT)" matchea por 'fecha'.

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


# Tokens disparadores por campo canonico. Cualquier match en los tokens del
# header alcanza para mapear la columna. Order = prioridad si un header
# matchea multiples campos (mas especifico primero).
TRIGGER_TOKENS: dict[str, set[str]] = {
    # agent_doc primero: si una columna dice "DOC_ASESOR", queremos doc no name
    'agent_doc': {'documento', 'dni', 'cedula', 'legajo'},
    'response_date': {'fecha', 'date', 'timestamp'},
    'nps_score': {'nps', 'nota', 'puntaje', 'calificacion', 'rating',
                  'puntuacion', 'score'},
    'comment': {'comentario', 'comment', 'feedback', 'observacion',
                'opinion', 'mensaje'},
    'cell': {'celula', 'equipo', 'sector'},
    # 'sucursal' incluido porque algunos bancos usan esa columna para guardar
    # el canal (WHATSAPP, LLAMADA) en vez de la sucursal fisica.
    'channel': {'canal', 'channel', 'medio', 'sucursal'},
    'agent_name': {'asesor', 'agente', 'agent', 'operador', 'representante',
                   'ejecutivo'},
}

FIELD_PRIORITY = list(TRIGGER_TOKENS.keys())


def _normalize_header(s: str) -> str:
    """minusculas + sin acentos + colapsa espacios."""
    if s is None:
        return ''
    s = str(s).strip().lower()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r'\s+', ' ', s)
    return s


def _tokens(header: str) -> set[str]:
    """Devuelve el set de tokens (palabras alfanumericas) del header normalizado.

    Ej: "FECHA_REGISTRADA (-04:00 GMT)" -> {'fecha','registrada','04','00','gmt'}
    """
    norm = _normalize_header(header)
    # Split en cualquier separador no alfanumerico
    return {t for t in re.split(r'[^a-z0-9]+', norm) if t}


def _map_headers(headers: list[str]) -> dict[str, int]:
    """Devuelve {campo_canonico: indice_columna}.

    Estrategia: para cada campo canonico (en orden de prioridad), buscar el
    primer header NO usado que contenga alguno de sus tokens disparadores.
    Asi evitamos que un header se asigne a multiples campos.
    """
    mapping: dict[str, int] = {}
    used_indices: set[int] = set()

    # Pre-tokenizar cada header una sola vez
    header_tokens = [(idx, _tokens(h)) for idx, h in enumerate(headers)]

    for canonical in FIELD_PRIORITY:
        triggers = TRIGGER_TOKENS[canonical]
        for idx, toks in header_tokens:
            if idx in used_indices:
                continue
            if toks & triggers:  # interseccion no vacia
                mapping[canonical] = idx
                used_indices.add(idx)
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
