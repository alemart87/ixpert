"""
Migration: agrega campos enriquecidos a nps_survey (capturados del XLSX del banco).

Campos nuevos:
- client_name, client_doc
- gender (predicho del nombre)
- effort, resolution, resolved
- motive, gestion_type, origin
- problem_description
- why_1, why_2, why_3, root_cause_type, responsibility
- review_status, review_note, reviewed_by_id, reviewed_at

Idempotente: chequea cada columna antes de crearla.
"""
from app import app
from models import db
from sqlalchemy import inspect
import iterum.models  # noqa: F401


COLUMNS = [
    ('client_name', 'VARCHAR(200)'),
    ('client_doc', 'VARCHAR(50)'),
    ('gender', 'VARCHAR(20)'),
    ('effort', 'VARCHAR(30)'),
    ('resolution', 'VARCHAR(20)'),
    ('resolved', 'VARCHAR(20)'),
    ('motive', 'VARCHAR(200)'),
    ('gestion_type', 'VARCHAR(100)'),
    ('origin', 'VARCHAR(150)'),
    ('problem_description', 'TEXT'),
    ('why_1', 'TEXT'),
    ('why_2', 'TEXT'),
    ('why_3', 'TEXT'),
    ('root_cause_type', 'VARCHAR(100)'),
    ('responsibility', 'VARCHAR(50)'),
    ("review_status", "VARCHAR(20) DEFAULT 'sin_revisar'"),
    ('review_note', 'TEXT'),
    ('reviewed_by_id', 'INTEGER'),
    ('reviewed_at', 'TIMESTAMP'),
]


def _ensure_column(table, column, ddl_type):
    insp = inspect(db.engine)
    try:
        cols = {c['name'] for c in insp.get_columns(table)}
    except Exception:
        return False
    if column in cols:
        return False
    db.session.execute(db.text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl_type}'))
    db.session.commit()
    return True


def migrate_extended_fields():
    with app.app_context():
        print('[MIGRATE ITERUM EXTENDED] Agregando campos enriquecidos a nps_survey...', flush=True)
        added = 0
        for col, ddl in COLUMNS:
            if _ensure_column('nps_survey', col, ddl):
                print(f'  + {col}')
                added += 1
        print(f'[MIGRATE ITERUM EXTENDED] {added} columna(s) agregada(s).', flush=True)


if __name__ == '__main__':
    migrate_extended_fields()
