"""Deduplicacion de respuestas NPS.

Hash determinista por respuesta = sha256 de campos clave normalizados. Si una
misma respuesta aparece en multiples XLSX (carga historica + incremental), el
constraint UNIQUE en nps_survey.unique_hash garantiza idempotencia.
"""
import hashlib


def survey_hash(response_date, agent_doc, nps_score, comment, channel) -> str:
    """Hash estable para detectar duplicados entre cargas.

    Usa fecha (con minuto), documento del asesor, score, primeros 200 chars
    del comentario y canal. Estable ante normalizacion de comentarios.
    """
    parts = [
        response_date.strftime('%Y-%m-%d %H:%M') if response_date else '',
        (agent_doc or '').strip().lower(),
        str(nps_score if nps_score is not None else ''),
        (comment or '').strip().lower()[:200],
        (channel or '').strip().lower(),
    ]
    joined = '|'.join(parts)
    return hashlib.sha256(joined.encode('utf-8')).hexdigest()


def file_hash(path: str) -> str:
    """Hash sha256 del archivo entero. Permite detectar reuploads del mismo XLSX."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()
