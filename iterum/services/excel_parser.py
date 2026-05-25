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


# Campos enriquecidos del XLSX del banco: matching por nombre exacto del header
# (despues de normalizar a snake_case lower). Si la columna no esta, queda None.
# Estos NO compiten con los principales — se mapean en paralelo.
EXTENDED_FIELD_MAP: dict[str, list[str]] = {
    # canonical -> lista de nombres alternativos posibles
    'client_name': ['nombre', 'cliente', 'nombre_cliente'],
    'client_doc': ['nro_cliente', 'documento_cliente', 'doc_cliente', 'cliente_doc'],
    'effort': ['esfuerzo', 'effort'],
    'resolution': ['resolucion', 'resolution'],
    'resolved': ['se_resolvio', 'resuelto'],
    'motive': ['motivo_cliente', 'motivo'],
    'gestion_type': ['tipo_gestion', 'gestion'],
    'origin': ['origen_principal', 'origen'],
    'problem_description': ['problema_descrito', 'problema', 'descripcion'],
    'why_1': ['porque_1', 'porque1', 'why_1'],
    'why_2': ['porque_2', 'porque2', 'why_2'],
    'why_3': ['porque_3_raiz', 'porque_3', 'porque3', 'why_3'],
    'root_cause_type': ['tipo_causa_raiz', 'tipo_causa', 'causa_raiz'],
    'responsibility': ['depende_de', 'depende', 'responsabilidad'],
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


def _tokens(header: str) -> set[str]:
    """Devuelve el set de tokens (palabras alfanumericas) del header normalizado.

    Ej: "FECHA_REGISTRADA (-04:00 GMT)" -> {'fecha','registrada','04','00','gmt'}
    """
    norm = _normalize_header(header)
    # Split en cualquier separador no alfanumerico
    return {t for t in re.split(r'[^a-z0-9]+', norm) if t}


def _snake_normalize(s: str) -> str:
    """'  Tipo_Gestion ' -> 'tipo_gestion'."""
    s = _normalize_header(s)
    # reemplaza no-alfanumericos por _
    s = re.sub(r'[^a-z0-9]+', '_', s)
    return s.strip('_')


def _map_headers(headers: list[str]) -> dict[str, int]:
    """Devuelve {campo_canonico: indice_columna} incluyendo campos enriquecidos.

    Orden de matching:
    1. Campos extendidos (matching de nombre exacto en snake_case): mas
       especificos. Asi 'Depende_de (Asesor/...)' va a responsibility, no
       a agent_name por la palabra 'asesor' que aparece en el sufijo.
    2. Campos principales (token-based con prioridad).
    """
    mapping: dict[str, int] = {}
    used_indices: set[int] = set()

    # 1) Extendidos: match si snake_header == alias o startswith alias + '_'
    snake_headers = [(idx, _snake_normalize(h)) for idx, h in enumerate(headers)]
    for canonical, aliases in EXTENDED_FIELD_MAP.items():
        for idx, snake in snake_headers:
            if idx in used_indices:
                continue
            matched = False
            for alias in aliases:
                if snake == alias or snake.startswith(alias + '_'):
                    matched = True
                    break
            if matched:
                mapping[canonical] = idx
                used_indices.add(idx)
                break

    # 2) Principales (token-based)
    header_tokens = [(idx, _tokens(h)) for idx, h in enumerate(headers)]
    for canonical in FIELD_PRIORITY:
        if canonical in mapping:
            continue
        triggers = TRIGGER_TOKENS[canonical]
        for idx, toks in header_tokens:
            if idx in used_indices:
                continue
            if toks & triggers:
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


def _normalize_cell(raw) -> str | None:
    """Normaliza el nombre de la celula. Aplica mapeo de aliases conocidos
    y limpia espacios. Mantener este map sincronizado con
    iterum/migrations/normalize_cells.py para datos historicos.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Colapsar espacios multiples
    s = re.sub(r'\s+', ' ', s)
    # Mapeo de aliases (clave: forma normalizada upper sin espacios, valor: forma canonica)
    upper_compact = re.sub(r'\s+', '', s.upper())
    aliases = {
        'PB': 'PERSONAL BANK',
        'PERSONALBANK': 'PERSONAL BANK',
    }
    if upper_compact in aliases:
        return aliases[upper_compact]
    return s


def _normalize_effort(raw) -> str | None:
    """Normaliza ESFUERZO a 5 buckets canonicos."""
    if raw is None: return None
    s = _normalize_header(str(raw))
    if 'muy' in s and ('facil' in s or 'fácil' in s): return 'Muy facil'
    if 'muy' in s and ('dificil' in s or 'difícil' in s): return 'Muy dificil'
    if 'facil' in s or 'fácil' in s: return 'Facil'
    if 'dificil' in s or 'difícil' in s: return 'Dificil'
    if 'neutro' in s or 'normal' in s: return 'Neutro'
    return str(raw).strip()[:30] or None


def _normalize_yes_no(raw) -> str | None:
    """Normaliza Si/No/Parcial."""
    if raw is None: return None
    s = _normalize_header(str(raw))
    if not s: return None
    if s in ('si', 'sí', 's', 'yes', 'y', 'true', '1'): return 'Si'
    if s in ('no', 'n', 'false', '0'): return 'No'
    if 'parcial' in s: return 'Parcial'
    return str(raw).strip()[:20] or None


def _normalize_responsibility(raw) -> str | None:
    """Asesor / Proceso / Externo / Servicio."""
    if raw is None: return None
    s = _normalize_header(str(raw))
    if 'asesor' in s: return 'Asesor'
    if 'proceso' in s: return 'Proceso'
    if 'externo' in s: return 'Externo'
    if 'servicio' in s: return 'Servicio'
    return str(raw).strip()[:50] or None


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

            from iterum.services.gender import predict_gender

            def _s(key, max_len=None):
                v = get(key)
                if v is None or v == '': return None
                s = str(v).strip()
                if not s or s == '-': return None
                return s[:max_len] if max_len else s

            client_name = _s('client_name', 200)
            gender, _hint = predict_gender(client_name) if client_name else ('No Detectado', None)

            yield {
                'response_date': response_date,
                'channel': _normalize_channel(get('channel')),
                'cell': _normalize_cell(get('cell')),
                'agent_name': _s('agent_name', 150),
                'agent_doc': _s('agent_doc', 50),
                'nps_score': score,
                'category': _categorize_nps(score),
                'comment': _s('comment'),
                # Enriquecidos
                'client_name': client_name,
                'client_doc': _s('client_doc', 50),
                'gender': gender,
                'effort': _normalize_effort(get('effort')),
                'resolution': _normalize_yes_no(get('resolution')),
                'resolved': _normalize_yes_no(get('resolved')),
                'motive': _s('motive', 200),
                'gestion_type': _s('gestion_type', 100),
                'origin': _s('origin', 150),
                'problem_description': _s('problem_description'),
                'why_1': _s('why_1'),
                'why_2': _s('why_2'),
                'why_3': _s('why_3'),
                'root_cause_type': _s('root_cause_type', 100),
                'responsibility': _normalize_responsibility(get('responsibility')),
            }
    finally:
        wb.close()
