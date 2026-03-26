import os
from flask import Flask, render_template, redirect, url_for, request, jsonify, flash
from flask_login import LoginManager, login_required, current_user
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from models import db, User, Content, Category, PageView
from datetime import datetime, timezone

load_dotenv()

app = Flask(__name__, static_folder='static', template_folder='templates')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', '').replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['PREFERRED_URL_SCHEME'] = 'https'

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
    print(f"[INIT] Password length={len(password) if password else 0}, first3={password[:3] if password else 'N/A'}, last3={password[-3:] if password else 'N/A'}", flush=True)
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

app.register_blueprint(admin_bp)
app.register_blueprint(analytics_bp)


# ===== Auth routes directly in app (no blueprint) =====
from flask_login import login_user, logout_user


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
        print(f"[AUTH] User found: {user is not None}", flush=True)
        if user:
            pw_ok = user.check_password(password)
            print(f"[AUTH] Password len={len(password)}, check={pw_ok}, active={user.is_active_user}", flush=True)
            # Debug: re-verify with env password
            env_pw = os.environ.get('SUPERADMIN_PASSWORD', '')
            print(f"[AUTH] Env password len={len(env_pw)}, match_input={password == env_pw}", flush=True)
            if pw_ok and user.is_active_user:
                user.last_login = datetime.now(timezone.utc)
                db.session.commit()
                login_user(user, remember=True)
                print(f"[AUTH] Login SUCCESS for {email}", flush=True)
                return redirect(url_for('index'))

        flash('Email o contraseña incorrectos.', 'error')
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


@app.context_processor
def inject_nav_categories():
    """Make categories available to all templates for navigation."""
    if current_user.is_authenticated:
        cats = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
        return {'nav_categories': cats}
    return {'nav_categories': []}


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
