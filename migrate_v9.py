"""
Migration v9: Tipo de contenido editable (Visual / HTML personalizado).

Agrega:
- contents.content_type  (string, default 'visual')
   - 'visual'    → editor Quill, render inline (caso CMS tipico)
   - 'raw_html'  → HTML/JS personalizado, render en iframe sandbox
- contents.source_hash   (string, nullable, sha256 del archivo de origen)
   Permite a futuras migraciones detectar si el contenido fue modificado
   por el admin y evitar pisarlo. Si el hash en BD coincide con el del
   archivo en disco, sabemos que sigue siendo "fuente original" y se puede
   sincronizar.

Tambien:
- Setea content_type = 'raw_html' para todas las entradas que actualmente
  son documentos HTML completos (detectadas por <html>+<head>+<style>).
- Re-importa desde disco los slugs cuyo source_hash es NULL o coincide
  con el hash anterior — i.e. el admin no los toco. Esto fuerza el
  refresh de game1 con la nueva version.

Idempotente.
"""
import os
import re
import hashlib
from app import app
from models import db


def _file_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def _is_full_doc(html):
    if not html:
        return False
    head = html.lstrip()[:2000].lower()
    return ('<!doctype html' in head) or ('<html' in head)


def _ensure_column(table, column, ddl_type):
    """Agrega la columna si no existe. Portable a SQLite y PostgreSQL."""
    from sqlalchemy import inspect
    insp = inspect(db.engine)
    cols = {c['name'] for c in insp.get_columns(table)}
    if column in cols:
        return False
    db.session.execute(db.text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl_type}'))
    db.session.commit()
    return True


def migrate_v9():
    with app.app_context():
        print("[MIGRATE V9] Adding content_type + source_hash columns...")

        if _ensure_column('contents', 'content_type', "VARCHAR(20) DEFAULT 'visual'"):
            print('  Added contents.content_type')
        if _ensure_column('contents', 'source_hash', 'VARCHAR(64)'):
            print('  Added contents.source_hash')

        # Backfill: marcar como 'raw_html' las entradas que ya son docs completos
        from models import Content
        promoted = 0
        for c in Content.query.all():
            if (c.content_type or 'visual') != 'visual':
                continue
            if _is_full_doc(c.html_content or ''):
                c.content_type = 'raw_html'
                promoted += 1
        db.session.commit()
        print(f'[MIGRATE V9] Promoted to raw_html: {promoted}')

        # Re-sync desde disco para los que no tienen source_hash o coinciden con
        # el hash actual del archivo (no fueron modificados por el admin).
        from migrate import slug_from_filename
        base = os.path.join(os.path.dirname(__file__), 'iXpert')
        if not os.path.isdir(base):
            print('[MIGRATE V9] iXpert/ no existe, fin.')
            return

        targets = [(base, 'root')]
        for sub in ['saccom', 'sihb', 'Nucleo', 'varios']:
            sp = os.path.join(base, sub)
            if os.path.isdir(sp):
                targets.append((sp, sub))

        synced = 0
        for dir_path, _ in targets:
            for fname in os.listdir(dir_path):
                if not fname.endswith('.html') or fname == 'iXpert.html':
                    continue
                fpath = os.path.join(dir_path, fname)
                if not os.path.isfile(fpath):
                    continue
                slug = slug_from_filename(fname)
                c = Content.query.filter_by(slug=slug).first()
                if not c:
                    continue

                disk_hash = _file_sha256(fpath)
                # Si el hash coincide, ya esta sincronizado.
                if c.source_hash and c.source_hash == disk_hash:
                    continue

                with open(fpath, 'r', encoding='utf-8') as f:
                    disk_html = f.read()

                if _is_full_doc(disk_html):
                    # Reglas de sincronizacion:
                    # 1) source_hash != NULL y != disk_hash → el archivo en disco
                    #    cambio (release nueva), sincronizamos.
                    # 2) source_hash == NULL y BD esta "rota" (no es full doc) →
                    #    primera sincronizacion, levantar el contenido.
                    # 3) source_hash == NULL y BD ya es full doc → admin edito
                    #    despues de v8/migrate inicial; NO pisar, solo registrar
                    #    el hash actual para evitar volver a sincronizar.
                    db_is_full = _is_full_doc(c.html_content or '')
                    is_admin_edited = (c.source_hash is None) and db_is_full

                    if is_admin_edited:
                        # Marcar el hash sin tocar el contenido (preservar edicion)
                        c.source_hash = disk_hash
                        continue

                    # Aplicar la misma normalizacion de paths de imagen que migrate.py
                    new_html = re.sub(r'src=["\'](?:\.\.\/)*imagenes/', 'src="/imagenes/', disk_html)
                    new_html = re.sub(r'src=["\']imagenes/', 'src="/imagenes/', new_html)
                    if c.html_content != new_html:
                        c.html_content = new_html
                        c.content_type = 'raw_html'
                        synced += 1
                        print(f'  [SYNC] {slug}  ({len(c.html_content) if c.html_content else 0}B)')
                    c.source_hash = disk_hash
                else:
                    if c.source_hash != disk_hash:
                        c.source_hash = disk_hash

        db.session.commit()
        print(f'[MIGRATE V9] Synced from disk: {synced}.')


if __name__ == '__main__':
    migrate_v9()
