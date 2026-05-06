"""
Migration v8: Backfill de contenidos que son documentos HTML completos.

La migracion inicial recortaba a <body> y se perdian los <style>/<script>
del <head>. Resultado: juegos y calculadoras se renderizaban sin estilo,
con conflictos contra el layout del portal.

Ahora migrate.py preserva los documentos completos, y el viewer los
renderiza en iframe sandbox (filtro is_full_html_doc en app.py).
Esta migracion v8 recorre los archivos HTML originales y, para cada slug
existente cuya version en BD esta "incompleta" (no incluye <style> o <script>
del head pero el archivo en disco SI), reemplaza el html_content con la
version completa del archivo.

Idempotente: solo actualiza si detecta que el archivo en disco es full doc
y la version en BD lo perdio.
"""
import os
import re
from app import app
from models import db, Content
from migrate import slug_from_filename, is_full_document, extract_body


def migrate_v8():
    base_dir = os.path.join(os.path.dirname(__file__), 'iXpert')
    if not os.path.exists(base_dir):
        print('[MIGRATE V8] iXpert/ no existe, nada que hacer.')
        return

    with app.app_context():
        updated = 0
        scanned = 0

        # Recorrer raiz + subdirs (mismo orden que migrate.py)
        targets = [(base_dir, 'root')]
        for sub in ['saccom', 'sihb', 'Nucleo', 'varios']:
            sub_path = os.path.join(base_dir, sub)
            if os.path.isdir(sub_path):
                targets.append((sub_path, sub))

        for dir_path, _label in targets:
            for filename in os.listdir(dir_path):
                if not filename.endswith('.html'):
                    continue
                if filename == 'iXpert.html':
                    continue
                filepath = os.path.join(dir_path, filename)
                if not os.path.isfile(filepath):
                    continue

                slug = slug_from_filename(filename)
                content = Content.query.filter_by(slug=slug).first()
                if not content:
                    continue
                scanned += 1

                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        disk_html = f.read()
                except Exception as e:
                    print(f'  [SKIP] error leyendo {filepath}: {e}')
                    continue

                # Solo nos interesa si el archivo en disco es un documento
                # completo Y la version en BD lo perdio (le falta el <head>).
                if not is_full_document(disk_html):
                    continue

                db_html = content.html_content or ''
                # Heuristica simple: si la version en BD no contiene <html o
                # <head, le faltan las partes top-level del documento.
                lower_db = db_html.lower()
                if '<html' in lower_db and '<head' in lower_db:
                    # Ya esta completa, no tocar.
                    continue

                # Reemplazar con la version full doc (preservando reescritura
                # de rutas /imagenes/).
                new_html = extract_body(disk_html)
                if new_html == db_html:
                    continue

                content.html_content = new_html
                updated += 1
                print(f'  [FIX] {slug}  ({len(db_html)}B → {len(new_html)}B)')

        db.session.commit()
        print(f'[MIGRATE V8] Escaneados: {scanned}. Actualizados: {updated}.')


if __name__ == '__main__':
    migrate_v8()
