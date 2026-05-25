"""
Migration: normaliza nombres de celulas en nps_survey.

Aplica el mismo mapeo que iterum/services/excel_parser._normalize_cell para que
los datos historicos queden consistentes con las cargas nuevas.

Ej: 'PB' -> 'PERSONAL BANK'

Idempotente: re-ejecutar no cambia datos ya normalizados.
"""
from app import app
from models import db
import iterum.models  # noqa: F401
from iterum.models import NPSSurvey
from iterum.services.excel_parser import _normalize_cell


def normalize_cells():
    with app.app_context():
        print('[MIGRATE ITERUM CELLS] Normalizando nombres de celulas...', flush=True)
        rows = NPSSurvey.query.filter(NPSSurvey.cell.isnot(None)).all()
        changed = 0
        for r in rows:
            new = _normalize_cell(r.cell)
            if new != r.cell:
                r.cell = new
                changed += 1
        if changed:
            db.session.commit()
        print(f'[MIGRATE ITERUM CELLS] {changed} filas normalizadas.', flush=True)


if __name__ == '__main__':
    normalize_cells()
