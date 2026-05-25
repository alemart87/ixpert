"""
Migration: tablas de Iterum (NPS Management Platform).

Crea idempotentemente:
- nps_upload
- nps_survey
- nps_audit
- nps_root_cause
- nps_coaching
- nps_report_snapshot
- nps_access_log

Estrategia: importar los modelos hace que db.metadata los conozca, luego
db.create_all() crea solo las tablas que NO existen. Indices y constraints
quedan definidos en los modelos. Safe to run multiple times.
"""
from app import app
from models import db
import iterum.models  # noqa: F401  (registra los modelos en db.metadata)


def migrate_iterum():
    with app.app_context():
        print('[MIGRATE ITERUM] Creando tablas Iterum si no existen...', flush=True)
        db.create_all()
        print('[MIGRATE ITERUM] Done.', flush=True)


if __name__ == '__main__':
    migrate_iterum()
