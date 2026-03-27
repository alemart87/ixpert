"""
Migration script: imports existing HTML content into PostgreSQL.
Reads HTML files from the iXpert/ directory and creates categories + content records.
Safe to run multiple times - skips existing slugs.
"""
import os
import re
import sys
from app import app, db
from models import Category, Content

# Map directories to categories
CATEGORY_MAP = {
    'root': {'name': 'General', 'slug': 'general', 'description': 'Contenido general y tutoriales', 'sort_order': 0},
    'saccom': {'name': 'SAC.COM', 'slug': 'saccom', 'description': 'Plataforma SAC.COM', 'sort_order': 1},
    'sihb': {'name': 'SIHB', 'slug': 'sihb', 'description': 'Servicios SIHB', 'sort_order': 2},
    'Nucleo': {'name': 'Núcleo', 'slug': 'nucleo', 'description': 'Sistema Núcleo bancario', 'sort_order': 3},
    'varios': {'name': 'Varios', 'slug': 'varios', 'description': 'Herramientas y utilidades', 'sort_order': 4},
}

# Keywords mapping from busqueda.js (simplified)
KEYWORDS_MAP = {
    'tuto4': 'pin, activar pin, token, itoken',
    'pinactivate': 'pin, activar pin, tx, token, itoken',
    'bpm_excepcion': 'excepcion, excepcional, itoken',
    'tuto5': 'devolucion, devolver',
    'tuto6': 'duplicado, doble, pago duplicado',
    'tuto7': 'delivery, tracking, currier, envios',
    'tuto8': 'contracargo',
    'tuto9': 'cuenta, salario, ahorro, prestamo, mantenimiento',
    'intervale': 'intervale, cuentas',
    'tarifario': 'tarifario, cuentas',
    'saccom': 'sac.com, saccom, sac',
    'bancard': 'bancard',
    'alias': 'alias',
    'resumentc': 'resumen, tc',
    'tipificaciones': 'tipificacion, registro, registros, tipificaciones, tipificar',
    'Matriz_Soporte': 'matriz, gestionessihb',
    'Matriz_CIB': 'matriz, gestionescib',
    'cancelartransferencia': 'programada, transferencia, cancelar',
    'qrpix': 'pix, qr',
    'Calculadora_NPS': 'nps, calculadora',
    'extractoxmail': 'extracto, resumen, mail',
    'anulacionesyconfirmaciones': 'anulaciones, confirmaciones',
    'retencionyreubicacion': 'retencion, reubicacion, reubicar',
    'cnb': 'cnb, agencias',
    'game1': 'game, trivia',
    'aumentolineatc': 'aumento, aumentar, linea tc',
    'extractotc': 'extracto, descargar, tc',
    'phishing': 'phishing, seguridad',
    'herramientas': 'herramientas, plataformas',
    'depositarcheque': 'depositar, cheque, app',
    'SIHB': 'sihb',
    'Nucleo': 'nucleo',
    'BPM': 'bpm',
    'prestamo': 'prestamo',
    'ahorroprogramado': 'ahorro programado',
    'snpi': 'snpi',
    'ptelectronica': 'pt electronica',
    'extranet': 'extranet',
    'admin24hs': 'admin 24hs',
    'tuto10': 'tutorial',
}

# Files to skip (main page, not content)
SKIP_FILES = {'iXpert.html'}


def extract_title(html):
    """Extract title from HTML."""
    # Try <title> tag
    m = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
    if m:
        title = m.group(1).strip()
        # Remove common suffixes
        for suffix in [' - Itaú Xpert', ' | Itaú Xpert', ' - iXpert']:
            title = title.replace(suffix, '')
        if title:
            return title

    # Try first <h1>
    m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.IGNORECASE | re.DOTALL)
    if m:
        return re.sub(r'<[^>]+>', '', m.group(1)).strip()

    return 'Sin título'


def extract_body(html):
    """Extract body content from HTML, preserving internal structure."""
    # Try to get content between body tags
    m = re.search(r'<body[^>]*>(.*)</body>', html, re.IGNORECASE | re.DOTALL)
    if m:
        body = m.group(1)
    else:
        body = html

    # Fix image paths to use static folder
    body = re.sub(r'src=["\'](?:\.\.\/)*imagenes/', 'src="/imagenes/', body)
    body = re.sub(r'src=["\']imagenes/', 'src="/imagenes/', body)

    return body


def slug_from_filename(filename):
    """Create a slug from filename."""
    name = os.path.splitext(filename)[0]
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', name).strip('-').lower()
    return slug


def migrate():
    base_dir = os.path.join(os.path.dirname(__file__), 'iXpert')

    if not os.path.exists(base_dir):
        print("iXpert/ directory not found, skipping migration.")
        return

    with app.app_context():
        # Create categories
        for key, cat_data in CATEGORY_MAP.items():
            existing = Category.query.filter_by(slug=cat_data['slug']).first()
            if not existing:
                cat = Category(**cat_data)
                db.session.add(cat)
                print(f"  Created category: {cat_data['name']}")
        db.session.commit()

        # Process HTML files
        count = 0

        # Root level files
        for filename in os.listdir(base_dir):
            if not filename.endswith('.html') or filename in SKIP_FILES:
                continue
            filepath = os.path.join(base_dir, filename)
            if os.path.isfile(filepath):
                count += process_file(filepath, filename, 'root')

        # Subdirectory files
        for subdir in ['saccom', 'sihb', 'Nucleo', 'varios']:
            subdir_path = os.path.join(base_dir, subdir)
            if not os.path.isdir(subdir_path):
                continue
            for filename in os.listdir(subdir_path):
                if not filename.endswith('.html'):
                    continue
                filepath = os.path.join(subdir_path, filename)
                count += process_file(filepath, filename, subdir)

        db.session.commit()
        print(f"Migration complete: {count} content items processed.")


def process_file(filepath, filename, category_key):
    """Process a single HTML file and insert into DB."""
    slug = slug_from_filename(filename)

    # Check if already exists
    if Content.query.filter_by(slug=slug).first():
        return 0

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            html = f.read()
    except Exception as e:
        print(f"  Error reading {filepath}: {e}")
        return 0

    title = extract_title(html)
    body = extract_body(html)
    name_no_ext = os.path.splitext(filename)[0]
    keywords = KEYWORDS_MAP.get(name_no_ext, '')

    cat_slug = CATEGORY_MAP[category_key]['slug']
    category = Category.query.filter_by(slug=cat_slug).first()

    content = Content(
        title=title,
        slug=slug,
        html_content=body,
        keywords=keywords,
        description=title,
        category_id=category.id if category else None,
        is_active=True
    )
    db.session.add(content)
    print(f"  Migrated: {filename} -> {slug} ({title})")
    return 1


if __name__ == '__main__':
    print("Starting migration...")
    migrate()
    print("Ensuring superadmin exists...")
    from app import init_superadmin
    with app.app_context():
        init_superadmin()
