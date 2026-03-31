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
    max_concurrent = int(request.form.get('max_concurrent', 1) or 1)

    if role not in ('supervisor', 'asesor'):
        flash('Rol no válido.', 'error')
        return redirect(url_for('admin.user_list'))

    if not email or not name:
        flash('Usuario/email y nombre son obligatorios.', 'error')
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
        user.max_concurrent_training = max(1, min(10, max_concurrent))
        if password:
            user.set_password(password)
    else:
        if not password:
            flash('La contraseña es obligatoria para nuevos usuarios.', 'error')
            return redirect(url_for('admin.user_list'))
        if User.query.filter_by(email=email).first():
            flash('Ya existe un usuario con ese email/usuario.', 'error')
            return redirect(url_for('admin.user_list'))
        user = User(email=email, name=name, role=role, is_active_user=is_active,
                    max_concurrent_training=max(1, min(10, max_concurrent)))
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
    from datetime import timedelta
    import re

    # Date filters
    date_from = request.args.get('from', '')
    date_to = request.args.get('to', '')

    if not date_from:
        dt_from = datetime.now(timezone.utc) - timedelta(hours=24)
    else:
        dt_from = datetime.strptime(date_from, '%Y-%m-%d').replace(tzinfo=timezone.utc)

    if not date_to:
        dt_to = datetime.now(timezone.utc)
    else:
        dt_to = datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)

    # Base filtered queries
    convs_q = ChatConversation.query.filter(ChatConversation.created_at.between(dt_from, dt_to))
    conv_ids = [c.id for c in convs_q.all()]
    msgs_q = ChatMessage.query.filter(ChatMessage.conversation_id.in_(conv_ids)) if conv_ids else ChatMessage.query.filter(False)

    # Stats
    total_convs = len(conv_ids)
    total_msgs = msgs_q.filter_by(role='user').count() if conv_ids else 0
    total_tokens = db.session.query(func.coalesce(func.sum(ChatMessage.tokens_used), 0)).filter(
        ChatMessage.conversation_id.in_(conv_ids)).scalar() if conv_ids else 0
    unique_users = db.session.query(func.count(func.distinct(ChatConversation.user_id))).filter(
        ChatConversation.id.in_(conv_ids)).scalar() if conv_ids else 0

    # Conversations per day
    convs_per_day = db.session.query(
        cast(ChatConversation.created_at, Date).label('date'),
        func.count(ChatConversation.id).label('count')
    ).filter(ChatConversation.created_at.between(dt_from, dt_to)
    ).group_by('date').order_by('date').all()

    # Top users
    top_users = db.session.query(
        User.name, User.role,
        func.count(func.distinct(ChatConversation.id)).label('convs')
    ).join(ChatConversation, User.id == ChatConversation.user_id
    ).filter(ChatConversation.created_at.between(dt_from, dt_to)
    ).filter(User.role != 'superadmin'
    ).group_by(User.id, User.name, User.role
    ).order_by(func.count(func.distinct(ChatConversation.id)).desc()).limit(10).all()

    # Analyze ALL user messages in period for topics
    stop = {'hola', 'como', 'cómo', 'que', 'qué', 'para', 'por', 'con', 'una', 'uno',
            'los', 'las', 'del', 'información', 'sobre', 'quiero', 'necesito', 'saber',
            'puedo', 'hacer', 'tiene', 'tiene', 'esta', 'esto', 'esos', 'esas', 'tiene',
            'favor', 'buenas', 'buenos', 'dias', 'gracias', 'muchas', 'bien', 'muy'}

    user_messages = []
    if conv_ids:
        user_messages = ChatMessage.query.filter(
            ChatMessage.conversation_id.in_(conv_ids),
            ChatMessage.role == 'user'
        ).all()

    # Extract meaningful phrases (bigrams) from user messages
    all_text = ' '.join(m.content.lower() for m in user_messages)
    words_list = [w for w in re.findall(r'\w+', all_text) if len(w) > 2 and w not in stop]

    # Single words
    word_freq = Counter(words_list).most_common(15)

    # Bigrams (two-word phrases) — more meaningful for topics
    bigrams = Counter()
    for i in range(len(words_list) - 1):
        pair = words_list[i] + ' ' + words_list[i + 1]
        bigrams[pair] += 1
    top_bigrams = bigrams.most_common(8)

    # Combine into top topics (prefer bigrams)
    top_topics = [{'word': w, 'count': c} for w, c in top_bigrams if c > 1]
    for w, c in word_freq:
        if len(top_topics) >= 10:
            break
        if not any(w in t['word'] for t in top_topics):
            top_topics.append({'word': w, 'count': c})

    # Category coverage: analyze which categories' CONTENT is being asked about
    from models import Category, Content
    categories = Category.query.filter_by(is_active=True).all()
    cat_coverage = {}
    for cat in categories:
        # Get keywords from all contents in this category
        contents_in_cat = Content.query.filter_by(category_id=cat.id, is_active=True).all()
        cat_kw = set()
        for cont in contents_in_cat:
            for kw in (cont.keywords or '').split(','):
                kw = kw.strip().lower()
                if len(kw) > 2:
                    cat_kw.add(kw)

        # Count how many user messages mention these keywords
        mentions = 0
        for msg in user_messages:
            msg_lower = msg.content.lower()
            if any(kw in msg_lower for kw in cat_kw):
                mentions += 1
        cat_coverage[cat.name] = mentions

    # --- SMART RECOMMENDATIONS ---
    recommendations = []

    # 1. High demand topics
    if top_topics and top_topics[0]['count'] >= 2:
        t = top_topics[0]
        recommendations.append({
            'icon': '🔥',
            'title': f'Tema más consultado: "{t["word"]}"',
            'desc': f'Con {t["count"]} menciones en el período. Evaluar si el equipo necesita capacitación específica o si el contenido existente es suficiente.',
            'priority': 'alta'
        })

    # 2. Users that ask a lot (may need more training)
    for name, role, convs in top_users:
        if convs >= 3:
            recommendations.append({
                'icon': '🎓',
                'title': f'{name} ({role}) realizó {convs} consultas',
                'desc': f'Alta actividad puede indicar necesidad de capacitación personalizada. Revisar los temas de sus consultas.',
                'priority': 'media'
            })
            break  # Only top user

    # 3. Categories with low coverage vs high coverage
    if cat_coverage:
        max_cov = max(cat_coverage.values()) if cat_coverage.values() else 0
        for cat_name, mentions in cat_coverage.items():
            if mentions == 0 and total_msgs > 3:
                recommendations.append({
                    'icon': '⚠️',
                    'title': f'Sin consultas sobre "{cat_name}"',
                    'desc': f'Ninguna consulta relacionada a contenidos de "{cat_name}". El equipo podría no conocer estos recursos. Considerar difusión.',
                    'priority': 'media'
                })
            elif max_cov > 0 and mentions == max_cov:
                recommendations.append({
                    'icon': '📈',
                    'title': f'"{cat_name}" es la más consultada',
                    'desc': f'{mentions} consultas relacionadas. Verificar que el contenido esté actualizado y sea suficiente.',
                    'priority': 'alta'
                })

    # 4. Engagement metric
    if unique_users and total_convs:
        avg = total_convs / unique_users
        if avg >= 2:
            recommendations.append({
                'icon': '✅',
                'title': f'Buen nivel de uso ({avg:.1f} consultas/usuario)',
                'desc': 'El equipo está adoptando la herramienta activamente.',
                'priority': 'info'
            })
        elif total_convs > 0 and avg < 1.5:
            recommendations.append({
                'icon': '📢',
                'title': 'Bajo engagement general',
                'desc': f'Promedio de {avg:.1f} consultas/usuario. Considerar promover más el uso de iXpert AI en el equipo.',
                'priority': 'media'
            })

    # 5. Token cost
    if total_tokens > 20000:
        cost_est = total_tokens * 0.00015 / 1000  # rough gpt-4o-mini estimate
        recommendations.append({
            'icon': '💰',
            'title': f'Consumo: {total_tokens:,} tokens (~${cost_est:.2f} USD)',
            'desc': 'Monitorear el costo. El modelo gpt-4o-mini es económico pero el volumen importa.',
            'priority': 'info'
        })

    if not recommendations:
        recommendations.append({
            'icon': '📊',
            'title': 'Datos insuficientes en este período',
            'desc': 'Ampliá el rango de fechas para obtener recomendaciones más precisas.',
            'priority': 'info'
        })

    # Recent conversations
    recent_convs = convs_q.order_by(ChatConversation.updated_at.desc()).limit(30).all()

    return jsonify({
        'stats': {
            'total_conversations': total_convs,
            'total_messages': total_msgs,
            'total_tokens': total_tokens,
            'unique_users': unique_users
        },
        'convs_per_day': [{'date': str(d), 'count': c} for d, c in convs_per_day],
        'top_users': [{'name': n, 'role': r, 'convs': c} for n, r, c in top_users],
        'top_topics': top_topics,
        'frequent_questions': [{'word': w, 'count': c} for w, c in word_freq],
        'category_coverage': cat_coverage,
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
