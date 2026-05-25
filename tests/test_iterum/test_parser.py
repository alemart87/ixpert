"""Tests del parser de XLSX y dedupe."""
from iterum.services.excel_parser import parse_xlsx_stream, _map_headers, _categorize_nps
from iterum.services.dedup import survey_hash, file_hash


def test_parse_basic(sample_xlsx):
    rows = [r for r in parse_xlsx_stream(sample_xlsx) if not r.get('_invalid')]
    assert len(rows) == 5
    assert rows[0]['nps_score'] == 10
    assert rows[0]['category'] == 'promotor'
    assert rows[0]['channel'] == 'whatsapp'


def test_categorize():
    assert _categorize_nps(10) == 'promotor'
    assert _categorize_nps(9) == 'promotor'
    assert _categorize_nps(8) == 'pasivo'
    assert _categorize_nps(7) == 'pasivo'
    assert _categorize_nps(6) == 'detractor'
    assert _categorize_nps(0) == 'detractor'
    assert _categorize_nps(None) is None


def test_map_headers_flexible():
    m = _map_headers(['Fecha', 'Canal', 'NPS', 'Comentario'])
    assert 'response_date' in m
    assert 'channel' in m
    assert 'nps_score' in m
    assert 'comment' in m


def test_survey_hash_stable():
    from datetime import datetime
    d = datetime(2026, 5, 1, 10, 0)
    h1 = survey_hash(d, '111', 10, 'Hola', 'whatsapp')
    h2 = survey_hash(d, '111', 10, 'Hola', 'whatsapp')
    assert h1 == h2


def test_survey_hash_distinct():
    from datetime import datetime
    d = datetime(2026, 5, 1, 10, 0)
    h1 = survey_hash(d, '111', 10, 'a', 'whatsapp')
    h2 = survey_hash(d, '111', 9, 'a', 'whatsapp')
    assert h1 != h2


def test_map_headers_bank_real_format():
    """Cobertura del formato real del XLSX exportado por el sistema upstream
    del banco. Headers con sufijos de timezone, _ATENCION, etc."""
    headers = [
        'FECHA_REGISTRADA (-04:00 GMT)', 'NOTA', 'TIPO_RESPUESTA', 'NRO_CLIENTE',
        'NOMBRE', 'COMENTARIO_COMPLETO', 'SEGMENTO', 'PROVEEDOR_ATENCION',
        'AGENTE_ATENCION', 'SUCURSAL_ATENCION', 'ESFUERZO', 'RESOLUCION',
        'ENCUESTA', 'YY', 'MM', 'DD', 'SEM', 'Celula',
    ]
    m = _map_headers(headers)
    assert m['response_date'] == 0  # FECHA_REGISTRADA
    assert m['nps_score'] == 1      # NOTA
    assert m['comment'] == 5        # COMENTARIO_COMPLETO
    assert m['agent_name'] == 8     # AGENTE_ATENCION
    assert m['channel'] == 9        # SUCURSAL_ATENCION (en esta data trae WHATSAPP)
    assert m['cell'] == 17          # Celula


def test_no_false_positives_on_misc_columns():
    """Columnas genericas no deben capturar un campo canonico."""
    headers = ['Tipo_Gestion', 'Motivo_Cliente', 'Origen_Principal',
               'Problema_Descrito', 'Historial del chat']
    m = _map_headers(headers)
    assert m == {}


def test_file_hash(sample_xlsx):
    h1 = file_hash(sample_xlsx)
    h2 = file_hash(sample_xlsx)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_normalize_cell_pb_to_personal_bank():
    """PB es alias de PERSONAL BANK (data del banco trae ambas formas)."""
    from iterum.services.excel_parser import _normalize_cell
    assert _normalize_cell('PB') == 'PERSONAL BANK'
    assert _normalize_cell('pb') == 'PERSONAL BANK'
    assert _normalize_cell(' PB ') == 'PERSONAL BANK'
    assert _normalize_cell('PERSONAL BANK') == 'PERSONAL BANK'
    assert _normalize_cell('Personal Bank') == 'PERSONAL BANK'
    assert _normalize_cell('personalbank') == 'PERSONAL BANK'
    # Otras celulas: solo strip + colapsa espacios
    assert _normalize_cell('Célula 0917') == 'Célula 0917'
    assert _normalize_cell('  Célula   1422  ') == 'Célula 1422'
    assert _normalize_cell(None) is None
    assert _normalize_cell('') is None
