import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from models import db, User, Content, Category, ChatConversation, ChatMessage
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
    upload_dir = current_app.config['UPLOAD_DIR']
    os.makedirs(upload_dir, exist_ok=True)
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)

    return jsonify({'url': '/imagenes/' + filename})


# --- Insights AI de Mejora ---
@admin_bp.route('/chat')
@superadmin_required
def chat_analytics():
    return render_template('admin/chat_analytics.html')


@admin_bp.route('/chat/<int:conv_id>/detail')
@superadmin_required
def admin_chat_detail(conv_id):
    conv = ChatConversation.query.get_or_404(conv_id)
    return jsonify({
        'title': conv.title,
        'user': conv.user.name if conv.user else 'Desconocido',
        'messages': [{
            'role': m.role,
            'content': m.content,
            'created_at': m.created_at.strftime('%d/%m/%Y %H:%M') if m.created_at else ''
        } for m in conv.messages]
    })


@admin_bp.route('/api/insights')
@superadmin_required
def api_insights():
    from sqlalchemy import func, cast, Date
    from collections import Counter
    import re

    # Basic stats
    total_convs = ChatConversation.query.count()
    total_msgs = ChatMessage.query.filter_by(role='user').count()
    total_tokens = db.session.query(func.coalesce(func.sum(ChatMessage.tokens_used), 0)).scalar()
    unique_users = db.session.query(func.count(func.distinct(ChatConversation.user_id))).scalar()

    # Conversations per day (last 30 days)
    convs_per_day = db.session.query(
        cast(ChatConversation.created_at, Date).label('date'),
        func.count(ChatConversation.id).label('count')
    ).group_by('date').order_by('date').all()

    # Top users by conversations
    top_users = db.session.query(
        User.name, User.role,
        func.count(ChatConversation.id).label('convs'),
        func.count(ChatMessage.id).label('msgs')
    ).join(ChatConversation, User.id == ChatConversation.user_id
    ).outerjoin(ChatMessage, ChatConversation.id == ChatMessage.conversation_id
    ).filter(User.role != 'superadmin'
    ).group_by(User.id, User.name, User.role
    ).order_by(func.count(ChatConversation.id).desc()).limit(10).all()

    # Topic analysis from conversation titles
    all_titles = [c.title.lower() for c in ChatConversation.query.all() if c.title]
    topic_words = Counter()
    stop = {'hola', 'como', 'que', 'para', 'por', 'con', 'una', 'los', 'las', 'del', 'qué', 'cómo', 'información', 'sobre'}
    for title in all_titles:
        words = re.findall(r'\w+', title)
        for w in words:
            if len(w) > 3 and w not in stop:
                topic_words[w] += 1
    top_topics = topic_words.most_common(10)

    # User messages for gap analysis (what users ask about most)
    user_msgs = ChatMessage.query.filter_by(role='user').all()
    question_words = Counter()
    for msg in user_msgs:
        words = re.findall(r'\w+', msg.content.lower())
        for w in words:
            if len(w) > 3 and w not in stop:
                question_words[w] += 1
    frequent_questions = question_words.most_common(15)

    # Content gap: categories with few/no questions
    from models import Category, Content
    categories = Category.query.filter_by(is_active=True).all()
    cat_mentions = {}
    for cat in categories:
        cat_name_lower = cat.name.lower()
        mentions = sum(1 for t in all_titles if cat_name_lower in t)
        cat_mentions[cat.name] = mentions

    # Training recommendations
    recommendations = []
    if top_topics:
        top_topic_name = top_topics[0][0]
        recommendations.append({
            'type': 'high_demand',
            'icon': '🔥',
            'title': f'Alta demanda: "{top_topic_name}"',
            'desc': f'El tema "{top_topic_name}" concentra {top_topics[0][1]} consultas. Considerar capacitación grupal o material adicional.'
        })

    # Find underexplored categories
    for cat_name, mentions in cat_mentions.items():
        if mentions == 0:
            recommendations.append({
                'type': 'gap',
                'icon': '📊',
                'title': f'Brecha: "{cat_name}" sin consultas',
                'desc': f'La categoría "{cat_name}" no tiene consultas. Puede indicar desconocimiento o falta de necesidad. Verificar con el equipo.'
            })

    if unique_users and total_convs:
        avg = total_convs / unique_users
        if avg > 5:
            recommendations.append({
                'type': 'engagement',
                'icon': '👥',
                'title': 'Alto engagement del equipo',
                'desc': f'Promedio de {avg:.1f} consultas por usuario. El equipo está usando activamente la herramienta.'
            })

    if total_tokens > 50000:
        recommendations.append({
            'type': 'cost',
            'icon': '💰',
            'title': 'Monitorear consumo de tokens',
            'desc': f'{total_tokens:,} tokens consumidos. Considerar optimizar respuestas o establecer límites.'
        })

    # Recent conversations for table
    recent_convs = ChatConversation.query.order_by(
        ChatConversation.updated_at.desc()
    ).limit(20).all()

    return jsonify({
        'stats': {
            'total_conversations': total_convs,
            'total_messages': total_msgs,
            'total_tokens': total_tokens,
            'unique_users': unique_users
        },
        'convs_per_day': [{'date': str(d), 'count': c} for d, c in convs_per_day],
        'top_users': [{'name': n, 'role': r, 'convs': c, 'msgs': m} for n, r, c, m in top_users],
        'top_topics': [{'word': w, 'count': c} for w, c in top_topics],
        'frequent_questions': [{'word': w, 'count': c} for w, c in frequent_questions],
        'category_coverage': cat_mentions,
        'recommendations': recommendations,
        'recent_conversations': [{
            'id': c.id,
            'user': c.user.name if c.user else '-',
            'role': c.user.role if c.user else '-',
            'title': c.title,
            'messages': len(c.messages),
            'tokens': sum(m.tokens_used or 0 for m in c.messages),
            'date': c.created_at.strftime('%d/%m/%Y %H:%M') if c.created_at else ''
        } for c in recent_convs]
    })
