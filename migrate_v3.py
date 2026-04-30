"""
Migration v3: Add avg_response_time (ART) column to training_sessions.
Idempotent — safe to run multiple times.
"""
from app import app, db
from sqlalchemy import text

MIGRATIONS = [
    "ALTER TABLE training_sessions ADD COLUMN IF NOT EXISTS avg_response_time DOUBLE PRECISION DEFAULT 0",
]


def run():
    with app.app_context():
        for sql in MIGRATIONS:
            try:
                db.session.execute(text(sql))
                db.session.commit()
                print(f"  OK: {sql[:80]}...")
            except Exception as e:
                db.session.rollback()
                print(f"  SKIP: {str(e)[:80]}")


if __name__ == '__main__':
    print("Running v3 migrations (avg_response_time / ART)...")
    run()
    print("Done.")
