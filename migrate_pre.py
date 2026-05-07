"""
Migration PRE: aplicar TODOS los ALTER TABLE para columnas nuevas ANTES
de cualquier consulta del ORM.

Necesario porque migrate.py (importacion inicial) usa el ORM y este
genera SQL con TODAS las columnas del modelo. Si la BD viene de una
version previa y le faltan columnas, las queries fallan con
'UndefinedColumn' antes de que las migraciones v5-v10 corran.

Este script corre PRIMERO en el Dockerfile y se asegura que el schema
sea compatible con el ORM actual. Es idempotente: cada ALTER TABLE
verifica primero si la columna existe.

Tambien crea tablas que el ORM espera y que no se crean por
db.create_all (porque ya existen sin las columnas o tienen
dependencias).
"""
from app import app
from models import db
from sqlalchemy import inspect


def _ensure_column(table, column, ddl_type):
    """Agrega la columna si no existe. Portable a SQLite y PostgreSQL."""
    insp = inspect(db.engine)
    try:
        cols = {c['name'] for c in insp.get_columns(table)}
    except Exception:
        # La tabla no existe aun; db.create_all la creara con el modelo actual.
        return False
    if column in cols:
        return False
    db.session.execute(db.text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl_type}'))
    db.session.commit()
    print(f'  + {table}.{column}')
    return True


def _table_exists(name):
    insp = inspect(db.engine)
    return name in insp.get_table_names()


def migrate_pre():
    with app.app_context():
        print('[MIGRATE PRE] Asegurando schema compatible con el ORM...')

        # contents — campos agregados en v9 y v10
        _ensure_column('contents', 'content_type', "VARCHAR(20) DEFAULT 'visual'")
        _ensure_column('contents', 'content_data', 'TEXT')
        _ensure_column('contents', 'source_hash', 'VARCHAR(64)')

        # training_sessions — campo agregado en v5
        if _table_exists('training_sessions'):
            _ensure_column('training_sessions', 'avg_response_time', 'DOUBLE PRECISION DEFAULT 0')

        # training_scenarios — campos agregados en v6 y v7
        if _table_exists('training_scenarios'):
            _ensure_column('training_scenarios', 'scoring_mode', 'VARCHAR(20)')
            _ensure_column('training_scenarios', 'client_response_delay_seconds', 'INTEGER DEFAULT 30')

        # training_batches — campos agregados en v6 y v7
        if _table_exists('training_batches'):
            _ensure_column('training_batches', 'scoring_mode', 'VARCHAR(20)')
            _ensure_column('training_batches', 'client_response_delay_seconds', 'INTEGER DEFAULT 30')

        print('[MIGRATE PRE] Schema OK.')


if __name__ == '__main__':
    migrate_pre()
