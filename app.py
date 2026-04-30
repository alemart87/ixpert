import os
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
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
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

app.register_blueprint(admin_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(training_bp)


# ===== Auth routes directly in app (no blueprint) =====
from flask_login import login_user, logout_user
import json as json_module


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


@app.route('/content/<slug>')
@login_required
def view_content(slug):
    content = Content.query.filter_by(slug=slug, is_active=True).first_or_404()
    return render_template('viewer.html', content=content)


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
