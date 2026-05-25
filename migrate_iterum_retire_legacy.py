"""Migration: retira el contenido legacy de Iterum del CMS.

El contenido `iterum-cx` era el HTML standalone embebido como raw_html en
/content/iterum-cx. Ahora Iterum vive en /iterum/* con backend y DB, asi que
el legacy se desactiva (is_active=False). El registro queda en DB para
trazabilidad — no se borra por si hay PageView referenciandolo.

Idempotente: si el contenido no existe o ya esta inactivo, no hace nada.
"""
from app import app
from models import db, Content


LEGACY_SLUGS = ('iterum-cx', 'iterum', '82f86905-nps-iterum')


def retire_legacy_iterum():
    with app.app_context():
        print('[MIGRATE ITERUM LEGACY] Retirando contenido legacy...', flush=True)
        retired = 0
        for slug in LEGACY_SLUGS:
            c = Content.query.filter_by(slug=slug).first()
            if c and c.is_active:
                c.is_active = False
                retired += 1
                print(f'  - Desactivado: {slug} (id={c.id})')
        if retired:
            db.session.commit()
        print(f'[MIGRATE ITERUM LEGACY] {retired} contenido(s) retirado(s).', flush=True)


if __name__ == '__main__':
    retire_legacy_iterum()
