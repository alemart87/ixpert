import os
import re
from flask import Flask, render_template, redirect, url_for, request, jsonify, flash, send_from_directory
from flask_login import LoginManager, login_required, current_user
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from models import db, User, Content, Category, PageView
from datetime import datetime, timezone

load_dotenv()

# Persistent disk path (Render) or local fallback
UPLOAD_DIR = os.environ.get('UPLOAD_DIR', os.path.join(os.path.dirname(__file__), 'static', 'imagenes'))

app = Flask(__name__, static_folder='static', template_folder='templates')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', '').replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Subimos el limite a 50MB. Los HTMLs ricos del CMS (Quill embebe imagenes como
# base64 al pegar capturas) facilmente pasan los 16MB anteriores.
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload
app.config['PREFERRED_URL_SCHEME'] = 'https'
app.config['UPLOAD_DIR'] = UPLOAD_DIR

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Debes iniciar sesión para acceder.'
login_manager.login_message_category = 'warning'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def init_superadmin():
    """Create or update superadmin from environment variables."""
    email = os.environ.get('SUPERADMIN_EMAIL')
    password = os.environ.get('SUPERADMIN_PASSWORD')
    print(f"[INIT] SUPERADMIN_EMAIL={'SET' if email else 'MISSING'}, SUPERADMIN_PASSWORD={'SET' if password else 'MISSING'}", flush=True)
    if not email or not password:
        print("[INIT] Skipping superadmin creation - missing env vars")
        return
    try:
        user = User.query.filter_by(email=email).first()
        if user:
            user.role = 'superadmin'
            user.set_password(password)
            user.name = 'Super Admin'
            user.is_active_user = True
            print(f"[INIT] Updated existing superadmin: {email}")
        else:
            user = User(
                email=email,
                name='Super Admin',
                role='superadmin',
                is_active_user=True
            )
            user.set_password(password)
            db.session.add(user)
            print(f"[INIT] Created new superadmin: {email}")
        db.session.commit()
        print("[INIT] Superadmin ready")
    except Exception as e:
        print(f"[INIT] Error creating superadmin: {e}")
        db.session.rollback()


# Register blueprints
from admin import admin_bp
from analytics import analytics_bp
from chat import chat_bp
from training import training_bp
from iterum import iterum_bp
from quizzes import quizzes_bp

app.register_blueprint(admin_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(training_bp)
app.register_blueprint(iterum_bp)
app.register_blueprint(quizzes_bp)

# Iterum: sweep de uploads colgados en 'processing' al arrancar el worker.
# Best-effort, no rompe el boot si falla.
try:
    from iterum.services.jobs import sweep_stale_processing
    sweep_stale_processing(app)
except Exception as _e:
    print(f"[INIT] Iterum sweep skipped: {_e}", flush=True)


# ===== Auth routes directly in app (no blueprint) =====
from flask_login import login_user, logout_user
import json as json_module


@app.template_filter('is_full_html_doc')
def is_full_html_doc(html):
    """True si el html_content es un documento completo (DOCTYPE/<html>/<body>).
    Estos contenidos se renderizan en iframe srcdoc para que sus estilos y
    scripts no pisen el portal."""
    if not html:
        return False
    head = html.lstrip()[:2000].lower()
    return ('<!doctype html' in head) or ('<html' in head) or ('<body' in head)


@app.template_filter('count_cases')
def count_cases_filter(text):
    """Count cases in a scenario's client_persona field."""
    try:
        data = json_module.loads(text)
        if isinstance(data, list):
            return len(data)
    except (json_module.JSONDecodeError, TypeError):
        pass
    return 1


@app.template_filter('scenario_json')
def scenario_json_filter(scenario):
    """Convert scenario to JSON for edit modal."""
    from training import parse_cases
    cases = parse_cases(scenario)
    return json_module.dumps({
        'title': scenario.title,
        'description': scenario.description or '',
        'difficulty': scenario.difficulty,
        'category': scenario.category or '',
        'scoring_mode': getattr(scenario, 'scoring_mode', None) or 'standard',
        'client_response_delay_seconds': getattr(scenario, 'client_response_delay_seconds', None) or 30,
        'cases': cases
    }, ensure_ascii=False)


@app.route('/login', methods=['GET', 'POST'])
def login():
    print(f"[AUTH] /login hit: method={request.method}", flush=True)

    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        print(f"[AUTH] POST login: email={email}", flush=True)

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password) and user.is_active_user:
                user.last_login = datetime.now(timezone.utc)
                db.session.commit()
                login_user(user, remember=True)
                print(f"[AUTH] Login SUCCESS for {email}", flush=True)
                return redirect(url_for('index'))

        flash('Usuario o contraseña incorrectos.', 'error')
        print(f"[AUTH] Login FAILED for {email}", flush=True)

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada correctamente.', 'success')
    return redirect(url_for('login'))


@app.route('/debug/check')
def debug_check():
    users = User.query.all()
    return jsonify({
        'users': [{'id': u.id, 'email': u.email, 'role': u.role, 'active': u.is_active_user} for u in users],
        'total': len(users)
    })


@app.route('/imagenes/<path:filename>')
def serve_image(filename):
    """Serve images from persistent disk or static fallback."""
    return send_from_directory(app.config['UPLOAD_DIR'], filename)


@app.errorhandler(413)
def request_entity_too_large(e):
    """Reemplaza el cartel feo de werkzeug por un flash con redirect.
    Dispara cuando el cuerpo del request supera MAX_CONTENT_LENGTH (50MB).
    El caso tipico es el editor Quill con muchas imagenes embebidas en base64.
    """
    flash('El contenido es demasiado grande (máximo 50 MB). '
          'Si pegaste imágenes en el editor, intentá usar el botón de subir '
          'imagen — así no quedan en base64 dentro del HTML.', 'error')
    # Volver al referer si viene del admin; sino al listado de contenidos.
    ref = request.referrer or url_for('admin.content_list')
    return redirect(ref), 303


@app.context_processor
def inject_nav_categories():
    """Make categories available to all templates for navigation."""
    if current_user.is_authenticated:
        cats = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
        return {'nav_categories': cats}
    return {'nav_categories': []}


@app.context_processor
def inject_mode_badge_helper():
    """Expose a helper to render scoring mode labels uniformly."""
    def mode_badge_label(mode):
        m = (mode or 'legacy').lower()
        return {
            'flexible': '🟢 Flexible',
            'standard': '🔵 Standard',
            'exigente': '🔴 Exigente',
        }.get(m, '⚪ Legacy')

    def mode_badge_class(mode):
        m = (mode or 'legacy').lower()
        if m not in ('flexible', 'standard', 'exigente'):
            return 'legacy'
        return m

    return {
        'mode_badge_label': mode_badge_label,
        'mode_badge_class': mode_badge_class,
    }


@app.route('/')
@login_required
def index():
    categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
    featured = Content.query.filter_by(is_active=True).order_by(Content.updated_at.desc()).limit(6).all()
    return render_template('index.html', categories=categories, featured=featured)


def render_trivia_html(content):
    """Renderiza el HTML completo del juego trivia con las preguntas inyectadas
    desde content.content_data (JSON). Devuelve el string que va al iframe srcdoc.
    """
    import json as _json
    try:
        data = _json.loads(content.content_data) if content.content_data else {}
    except (ValueError, TypeError):
        data = {}
    questions = data.get('questions', []) if isinstance(data, dict) else []
    return render_template(
        'games/trivia.html',
        trivia=data if isinstance(data, dict) else {},
        questions_json=_json.dumps(questions, ensure_ascii=False),
        slug=content.slug,
    )


# Pistas de que un contenido es un quiz/evaluacion y no un articulo comun.
# Solo en esos casos se activa la deteccion automatica de resultados: en un
# tutorial cualquiera, un "felicitaciones, completaste 3 de 5 pasos" podria
# confundirse con un puntaje.
_QUIZ_NAME_RE = re.compile(r'quiz|trivia|evaluaci|examen|cuestionario|\btest\b', re.I)
_QUIZ_HTML_MARKERS = (
    r'respuesta\s*correcta', r'\bcorrecta[s]?\b', r'type\s*=\s*["\']radio',
    r'\bpregunta\b', r'\bopci[oó]n(es)?\b', r'\bpuntaje\b', r'\bpuntuaci[oó]n\b',
    r'\bscore\b',
)


def _looks_like_quiz(content):
    """Heuristica para decidir si activamos la deteccion automatica."""
    if (content.content_type or 'visual') == 'trivia':
        return True
    name_hay = f"{content.slug or ''} {content.title or ''} {content.keywords or ''}"
    if _QUIZ_NAME_RE.search(name_hay):
        return True
    html = content.html_content or ''
    hits = sum(1 for pat in _QUIZ_HTML_MARKERS if re.search(pat, html, re.I))
    return hits >= 3


def inject_quiz_bridge(html, content):
    """Inyecta el bridge de registro de quiz en el HTML que va al iframe.

    El iframe usa srcdoc + sandbox allow-same-origin, asi que el script hereda
    el origen de la app y puede guardar el resultado con la sesion del usuario.
    """
    if not html:
        return html
    from markupsafe import escape as _esc

    tag = (
        '<script src="/static/js/quiz-bridge.js" data-ixpert-quiz="1"'
        f' data-content-id="{content.id}"'
        f' data-quiz-slug="{_esc(content.slug or "")}"'
        f' data-quiz-title="{_esc(content.title or "Quiz")}"'
        f' data-user-name="{_esc(getattr(current_user, "name", "") or "")}"'
        f' data-auto-detect="{"true" if _looks_like_quiz(content) else "false"}"'
        '></script>'
    )
    lowered = html.lower()
    idx = lowered.rfind('</body>')
    if idx != -1:
        return html[:idx] + tag + html[idx:]
    return html + tag


@app.route('/content/<slug>')
@login_required
def view_content(slug):
    content = Content.query.filter_by(slug=slug, is_active=True).first_or_404()
    ctype = content.content_type or 'visual'
    trivia_html = None
    iframe_html = None
    if ctype == 'trivia':
        trivia_html = inject_quiz_bridge(render_trivia_html(content), content)
    elif ctype == 'raw_html' or is_full_html_doc(content.html_content):
        # Contenido custom del CMS que se renderiza en iframe: le sumamos el
        # bridge para que, si es un quiz, el resultado quede registrado.
        iframe_html = inject_quiz_bridge(content.html_content, content)
    return render_template('viewer.html', content=content,
                           trivia_html=trivia_html, iframe_html=iframe_html)


@app.route('/category/<slug>')
@login_required
def view_category(slug):
    category = Category.query.filter_by(slug=slug, is_active=True).first_or_404()
    contents = Content.query.filter_by(category_id=category.id, is_active=True).all()
    return render_template('category.html', category=category, contents=contents)


@app.route('/api/search')
@login_required
def api_search():
    q = request.args.get('q', '').strip().lower()
    if not q:
        return jsonify([])
    contents = Content.query.filter_by(is_active=True).all()
    results = []
    for c in contents:
        keywords = (c.keywords or '').lower()
        title = c.title.lower()
        if q in keywords or q in title:
            results.append({
                'id': c.id,
                'title': c.title,
                'description': c.description or '',
                'slug': c.slug,
                'category': c.category.name if c.category else ''
            })
    return jsonify(results)


with app.app_context():
    db.create_all()
    init_superadmin()


if __name__ == '__main__':
    app.run(debug=True, port=5000)
