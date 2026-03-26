import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, User, Content, Category
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import datetime, timezone

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def superadmin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_superadmin:
            flash('No tienes permisos para acceder a esta sección.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


# --- Dashboard ---
@admin_bp.route('/dashboard')
@superadmin_required
def dashboard():
    return render_template('admin/dashboard.html')


# --- Content Management ---
@admin_bp.route('/contents')
@superadmin_required
def content_list():
    contents = Content.query.order_by(Content.updated_at.desc()).all()
    categories = Category.query.order_by(Category.sort_order).all()
    return render_template('admin/content_list.html', contents=contents, categories=categories)


@admin_bp.route('/contents/new', methods=['GET', 'POST'])
@superadmin_required
def content_new():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        slug = request.form.get('slug', '').strip()
        category_id = request.form.get('category_id')
        html_content = request.form.get('html_content', '')
        keywords = request.form.get('keywords', '')
        description = request.form.get('description', '')

        if not title or not slug:
            flash('Título y slug son obligatorios.', 'error')
        elif Content.query.filter_by(slug=slug).first():
            flash('Ya existe un contenido con ese slug.', 'error')
        else:
            content = Content(
                title=title,
                slug=slug,
                category_id=int(category_id) if category_id else None,
                html_content=html_content,
                keywords=keywords,
                description=description,
                created_by=current_user.id,
                updated_by=current_user.id
            )
            db.session.add(content)
            db.session.commit()
            flash('Contenido creado correctamente.', 'success')
            return redirect(url_for('admin.content_list'))

    categories = Category.query.order_by(Category.sort_order).all()
    return render_template('admin/content_edit.html', content=None, categories=categories)


@admin_bp.route('/contents/<int:content_id>/edit', methods=['GET', 'POST'])
@superadmin_required
def content_edit(content_id):
    content = Content.query.get_or_404(content_id)

    if request.method == 'POST':
        content.title = request.form.get('title', '').strip()
        content.slug = request.form.get('slug', '').strip()
        content.category_id = int(request.form.get('category_id')) if request.form.get('category_id') else None
        content.html_content = request.form.get('html_content', '')
        content.keywords = request.form.get('keywords', '')
        content.description = request.form.get('description', '')
        content.updated_by = current_user.id
        content.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        flash('Contenido actualizado correctamente.', 'success')
        return redirect(url_for('admin.content_list'))

    categories = Category.query.order_by(Category.sort_order).all()
    return render_template('admin/content_edit.html', content=content, categories=categories)


@admin_bp.route('/contents/<int:content_id>/delete', methods=['POST'])
@superadmin_required
def content_delete(content_id):
    content = Content.query.get_or_404(content_id)
    db.session.delete(content)
    db.session.commit()
    flash('Contenido eliminado.', 'success')
    return redirect(url_for('admin.content_list'))


# --- Categories ---
@admin_bp.route('/categories')
@superadmin_required
def category_list():
    categories = Category.query.order_by(Category.sort_order).all()
    return render_template('admin/categories.html', categories=categories)


@admin_bp.route('/categories/save', methods=['POST'])
@superadmin_required
def category_save():
    cat_id = request.form.get('id')
    name = request.form.get('name', '').strip()
    slug = request.form.get('slug', '').strip()
    description = request.form.get('description', '')
    sort_order = int(request.form.get('sort_order', 0))

    if not name or not slug:
        flash('Nombre y slug son obligatorios.', 'error')
        return redirect(url_for('admin.category_list'))

    if cat_id:
        cat = Category.query.get_or_404(int(cat_id))
        cat.name = name
        cat.slug = slug
        cat.description = description
        cat.sort_order = sort_order
    else:
        cat = Category(name=name, slug=slug, description=description, sort_order=sort_order)
        db.session.add(cat)

    db.session.commit()
    flash('Categoría guardada.', 'success')
    return redirect(url_for('admin.category_list'))


@admin_bp.route('/categories/<int:cat_id>/delete', methods=['POST'])
@superadmin_required
def category_delete(cat_id):
    cat = Category.query.get_or_404(cat_id)
    Content.query.filter_by(category_id=cat.id).update({'category_id': None})
    db.session.delete(cat)
    db.session.commit()
    flash('Categoría eliminada.', 'success')
    return redirect(url_for('admin.category_list'))


# --- User Management ---
@admin_bp.route('/users')
@superadmin_required
def user_list():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)


@admin_bp.route('/users/save', methods=['POST'])
@superadmin_required
def user_save():
    user_id = request.form.get('id')
    email = request.form.get('email', '').strip()
    name = request.form.get('name', '').strip()
    role = request.form.get('role', 'asesor')
    password = request.form.get('password', '')
    is_active = request.form.get('is_active') == 'on'

    if role not in ('supervisor', 'asesor'):
        flash('Rol no válido.', 'error')
        return redirect(url_for('admin.user_list'))

    if not email or not name:
        flash('Email y nombre son obligatorios.', 'error')
        return redirect(url_for('admin.user_list'))

    if user_id:
        user = User.query.get_or_404(int(user_id))
        if user.is_superadmin:
            flash('No puedes editar al SuperAdmin desde aquí.', 'error')
            return redirect(url_for('admin.user_list'))
        user.email = email
        user.name = name
        user.role = role
        user.is_active_user = is_active
        if password:
            user.set_password(password)
    else:
        if not password:
            flash('La contraseña es obligatoria para nuevos usuarios.', 'error')
            return redirect(url_for('admin.user_list'))
        if User.query.filter_by(email=email).first():
            flash('Ya existe un usuario con ese email.', 'error')
            return redirect(url_for('admin.user_list'))
        user = User(email=email, name=name, role=role, is_active_user=is_active)
        user.set_password(password)
        db.session.add(user)

    db.session.commit()
    flash('Usuario guardado correctamente.', 'success')
    return redirect(url_for('admin.user_list'))


# --- Image Upload ---
@admin_bp.route('/upload-image', methods=['POST'])
@superadmin_required
def upload_image():
    if 'image' not in request.files:
        return jsonify({'error': 'No se envió archivo'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'Archivo sin nombre'}), 400

    allowed = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed:
        return jsonify({'error': 'Tipo de archivo no permitido'}), 400

    filename = secure_filename(file.filename)
    upload_dir = os.path.join('static', 'imagenes')
    os.makedirs(upload_dir, exist_ok=True)
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)

    return jsonify({'url': '/' + filepath.replace('\\', '/')})
