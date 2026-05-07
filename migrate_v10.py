"""
Migration v10: Editor estructurado de Trivia.

Agrega:
- contents.content_data (TEXT, nullable) — JSON con datos estructurados
  segun content_type. Para 'trivia' es {"questions": [...]}.

Setea como 'trivia' al game1 existente y popula content_data con las 43
preguntas extraidas del JS del archivo iXpert/varios/game1.html.

Idempotente.
"""
import os
import re
import json
import hashlib
from app import app
from models import db


def _ensure_column(table, column, ddl_type):
    from sqlalchemy import inspect
    insp = inspect(db.engine)
    if column in {c['name'] for c in insp.get_columns(table)}:
        return False
    db.session.execute(db.text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl_type}'))
    db.session.commit()
    return True


def _extract_trivia_questions_from_html(html):
    """Extrae cada pregunta individualmente del JS del trivia HTML.

    En lugar de evaluar el array como JSON (fragil con caracteres de control,
    apostrofes y comentarios), buscamos cada bloque
        { pregunta: "...", correcta: "...", opciones: ["...", "...", ...] }
    y parseamos cada campo por separado.
    """
    # Quitar comentarios //... y /* ... */ que pueden romper la parte que sigue
    src = re.sub(r'/\*.*?\*/', '', html, flags=re.DOTALL)
    src = re.sub(r'(?m)//[^\n]*', '', src)

    # Patron: capta el bloque entero de un objeto pregunta. Usa re.DOTALL
    # para tolerar saltos de linea entre los campos.
    pattern = re.compile(
        r'\{\s*'
        r'pregunta\s*:\s*"((?:[^"\\]|\\.)*?)"\s*,\s*'
        r'correcta\s*:\s*"((?:[^"\\]|\\.)*?)"\s*,\s*'
        r'opciones\s*:\s*\[\s*(.*?)\s*\]\s*'
        r'\}',
        re.DOTALL
    )
    opt_pattern = re.compile(r'"((?:[^"\\]|\\.)*?)"', re.DOTALL)

    questions = []
    for m in pattern.finditer(src):
        pregunta = m.group(1)
        correcta = m.group(2)
        opts_block = m.group(3)
        opciones = opt_pattern.findall(opts_block)
        if pregunta and correcta and len(opciones) >= 2:
            questions.append({
                'pregunta': pregunta,
                'correcta': correcta,
                'opciones': opciones,
            })
    return questions


def migrate_v10():
    with app.app_context():
        print("[MIGRATE V10] Adding contents.content_data...")
        if _ensure_column('contents', 'content_data', 'TEXT'):
            print('  Added contents.content_data')

        # Cargar game1 desde disco y extraer preguntas
        from models import Content
        game1_path = os.path.join(os.path.dirname(__file__),
                                  'iXpert', 'varios', 'game1.html')
        if not os.path.isfile(game1_path):
            print('  [SKIP] iXpert/varios/game1.html no existe')
            return

        with open(game1_path, 'r', encoding='utf-8') as f:
            disk_html = f.read()

        questions = _extract_trivia_questions_from_html(disk_html)
        if not questions:
            print('  [SKIP] no se pudieron extraer preguntas del game1')
            return
        print(f'  Extraidas {len(questions)} preguntas del game1')

        # Migrar el contenido game1 si existe en BD: convertirlo a trivia
        # estructurada (preserva HTML como fallback).
        c = Content.query.filter_by(slug='game1').first()
        if not c:
            print('  [SKIP] game1 no existe en BD, no hay nada que convertir')
            return

        # Solo convertir si todavia es raw_html (no fue tocado a otro tipo)
        if (c.content_type or 'visual') in ('raw_html', 'visual'):
            payload = json.dumps({
                'title': 'iXpert Trivia',
                'welcome_title': '🎉 Bienvenido a la Trivia de iXpert 🎉',
                'welcome_subtitle': 'Responde correctamente y suma puntos.',
                'questions_per_round': 10,
                'time_per_question': 30,
                'questions': questions,
            }, ensure_ascii=False)
            c.content_type = 'trivia'
            c.content_data = payload
            # No tocamos source_hash para que migrate_v9 sepa que es derivado
            # de la version del repo. Pero el html_content se mantiene como
            # backup por si alguien quiere volver a 'raw_html'.
            db.session.commit()
            print(f'  game1 convertido a content_type=trivia ({len(questions)} preguntas)')
        else:
            print(f'  game1 ya tiene content_type={c.content_type}, no se toca')


if __name__ == '__main__':
    migrate_v10()
