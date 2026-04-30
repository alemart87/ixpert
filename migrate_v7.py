"""
Migration v7: Per-scenario client response delay.

Agrega:
- training_scenarios.client_response_delay_seconds  (INT, default 30)
- training_batches.client_response_delay_seconds    (INT, default 30, snapshot)

El delay simula el tiempo real que un cliente tarda en leer y empezar a
responder. Cada escenario lo configura entre 10 y 60 segundos. El batch
toma snapshot al iniciar para que cambios futuros del escenario no
afecten entrenamientos en curso.

Idempotente: usa IF NOT EXISTS.
"""
from app import app
from models import db


def migrate_v7():
    with app.app_context():
        print("[MIGRATE V7] Adding client_response_delay_seconds columns...")

        db.session.execute(db.text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'training_scenarios'
                      AND column_name = 'client_response_delay_seconds'
                ) THEN
                    ALTER TABLE training_scenarios
                        ADD COLUMN client_response_delay_seconds INTEGER DEFAULT 30;
                    RAISE NOTICE 'Added client_response_delay_seconds to training_scenarios';
                END IF;
            END $$;
        """))

        db.session.execute(db.text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'training_batches'
                      AND column_name = 'client_response_delay_seconds'
                ) THEN
                    ALTER TABLE training_batches
                        ADD COLUMN client_response_delay_seconds INTEGER DEFAULT 30;
                    RAISE NOTICE 'Added client_response_delay_seconds to training_batches';
                END IF;
            END $$;
        """))

        db.session.commit()
        print("[MIGRATE V7] Done.")


if __name__ == '__main__':
    migrate_v7()
