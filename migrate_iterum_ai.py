"""Migration: tablas del AI Analyst.

Crea iterum_ai_chat, iterum_ai_message, iterum_ai_canvas. Idempotente.
"""
from app import app
from models import db
import iterum.ai.models  # noqa: F401


def migrate_ai():
    with app.app_context():
        print('[MIGRATE ITERUM AI] Creando tablas del AI Analyst...', flush=True)
        db.create_all()
        print('[MIGRATE ITERUM AI] Done.', flush=True)


if __name__ == '__main__':
    migrate_ai()
