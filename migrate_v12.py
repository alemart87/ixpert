"""
Migration v12: Auto-cierre de sesiones de entrenamiento abandonadas.

Agrega:
- training_sessions.last_activity_at (TIMESTAMP, nullable) — timestamp
  del ultimo mensaje del asesor o del cliente simulado. Se usa para
  detectar sesiones inactivas y cerrarlas automaticamente despues de
  TRAINING_AUTO_CLOSE_MINUTES (30 min) en training.py.

Backfill: para sesiones existentes, last_activity_at queda en NULL.
La logica de auto-cierre usa coalesce(last_activity_at, started_at)
asi que sigue funcionando para sesiones legacy.

Idempotente.
"""
from app import app
from models import db
from sqlalchemy import inspect


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


def migrate_v12():
    with app.app_context():
        print('[MIGRATE V12] Auto-cierre por inactividad...')
        if _ensure_column('training_sessions', 'last_activity_at', 'TIMESTAMP'):
            print('  + training_sessions.last_activity_at')
        print('[MIGRATE V12] Done.')


if __name__ == '__main__':
    migrate_v12()
