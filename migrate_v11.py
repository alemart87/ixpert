"""
Migration v11: Reset de metricas con snapshot.

Agrega:
- vex_profiles.reset_at (TIMESTAMP, nullable) — fecha del ultimo reinicio
  de metricas. Si esta seteado, calculate_vex_profile filtra sesiones
  donde created_at > reset_at (las anteriores quedan en el historial pero
  no cuentan para el nuevo periodo).
- Tabla vex_profile_snapshots — log auditable de cada reinicio con el
  estado completo del perfil al momento del reset + quien lo hizo +
  motivo opcional.

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


def migrate_v11():
    with app.app_context():
        print('[MIGRATE V11] Reset de metricas con snapshot...')

        if _ensure_column('vex_profiles', 'reset_at', 'TIMESTAMP'):
            print('  + vex_profiles.reset_at')

        # Crear tabla vex_profile_snapshots si no existe
        # (db.create_all en app.py ya la habria creado en first deploy, pero
        # en upgrade desde version vieja la tabla no existe).
        db.session.execute(db.text("""
            CREATE TABLE IF NOT EXISTS vex_profile_snapshots (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                taken_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                taken_by INTEGER REFERENCES users(id),
                reason TEXT,
                communication_score FLOAT,
                empathy_score FLOAT,
                resolution_score FLOAT,
                speed_score FLOAT,
                adaptability_score FLOAT,
                compliance_score FLOAT,
                overall_score FLOAT,
                predictive_index FLOAT,
                profile_category VARCHAR(30),
                recommendation VARCHAR(30),
                sessions_analyzed INTEGER
            )
        """))
        db.session.commit()
        print('[MIGRATE V11] Done.')


if __name__ == '__main__':
    migrate_v11()
