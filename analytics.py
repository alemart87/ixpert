from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models import db, PageView, ClickEvent, SearchLog, Content
from datetime import datetime, timezone

analytics_bp = Blueprint('analytics', __name__)


@analytics_bp.route('/api/track/pageview', methods=['POST'])
@login_required
def track_pageview():
    data = request.get_json(silent=True) or {}
    page_path = data.get('page_path', '')
    referrer = data.get('referrer', '')
    session_id = data.get('session_id', '')
    content_id = data.get('content_id')

    pv = PageView(
        user_id=current_user.id,
        content_id=content_id,
        page_path=page_path,
        referrer=referrer,
        session_id=session_id
    )
    db.session.add(pv)
    db.session.commit()
    return jsonify({'ok': True})


@analytics_bp.route('/api/track/click', methods=['POST'])
@login_required
def track_click():
    data = request.get_json(silent=True) or {}
    ce = ClickEvent(
        user_id=current_user.id,
        content_id=data.get('content_id'),
        element_type=data.get('element_type', ''),
        element_text=data.get('element_text', '')[:500] if data.get('element_text') else '',
        page_path=data.get('page_path', '')
    )
    db.session.add(ce)
    db.session.commit()
    return jsonify({'ok': True})


@analytics_bp.route('/api/track/search', methods=['POST'])
@login_required
def track_search():
    data = request.get_json(silent=True) or {}
    sl = SearchLog(
        user_id=current_user.id,
        query=data.get('query', '')[:500],
        results_count=data.get('results_count', 0)
    )
    db.session.add(sl)
    db.session.commit()
    return jsonify({'ok': True})


@analytics_bp.route('/api/analytics/overview')
@login_required
def analytics_overview():
    if not current_user.is_superadmin:
        return jsonify({'error': 'No autorizado'}), 403

    from sqlalchemy import func, cast, Date

    date_from = request.args.get('from', '')
    date_to = request.args.get('to', '')

    dt_from = datetime.strptime(date_from, '%Y-%m-%d').replace(tzinfo=timezone.utc) if date_from else None
    dt_to = datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59, tzinfo=timezone.utc) if date_to else None

    def in_range(q, col):
        if dt_from is not None:
            q = q.filter(col >= dt_from)
        if dt_to is not None:
            q = q.filter(col <= dt_to)
        return q

    total_views = in_range(db.session.query(PageView), PageView.created_at).count()
    total_clicks = in_range(db.session.query(ClickEvent), ClickEvent.created_at).count()
    total_searches = in_range(db.session.query(SearchLog), SearchLog.created_at).count()

    # Todas las paginas visitadas (respetando el filtro de fechas, que antes
    # solo aplicaba a los totales). Con visitas, usuarios distintos y ultima
    # visita por ruta. El top-8 del grafico se recorta en el frontend.
    all_pages = in_range(db.session.query(
        PageView.page_path,
        func.count(PageView.id).label('views'),
        func.count(func.distinct(PageView.user_id)).label('unique_users'),
        func.max(PageView.created_at).label('last_visit')
    ), PageView.created_at).group_by(PageView.page_path
    ).order_by(db.text('views DESC')).limit(500).all()

    # Top searches (tambien respeta el filtro de fechas)
    top_searches = in_range(db.session.query(
        SearchLog.query,
        func.count(SearchLog.id).label('count')
    ), SearchLog.created_at).group_by(SearchLog.query
    ).order_by(db.text('count DESC')).limit(10).all()

    # Views per day
    views_per_day = in_range(db.session.query(
        cast(PageView.created_at, Date).label('date'),
        func.count(PageView.id).label('views')
    ), PageView.created_at).group_by('date').order_by('date').all()

    return jsonify({
        'total_views': total_views,
        'total_clicks': total_clicks,
        'total_searches': total_searches,
        'top_pages': [{'path': p, 'views': v} for p, v, _, _ in all_pages[:10]],
        'all_pages': [{
            'path': p, 'views': v, 'unique_users': u,
            'last_visit': lv.strftime('%d/%m/%Y %H:%M') if lv else ''
        } for p, v, u, lv in all_pages],
        'top_searches': [{'query': q, 'count': c} for q, c in top_searches],
        'views_per_day': [{'date': str(d), 'views': v} for d, v in views_per_day]
    })


@analytics_bp.route('/api/analytics/users')
@login_required
def analytics_users():
    if not current_user.is_superadmin:
        return jsonify({'error': 'No autorizado'}), 403

    from models import User
    from sqlalchemy import func

    user_stats = db.session.query(
        User.id, User.name, User.email, User.role,
        func.count(PageView.id).label('views')
    ).outerjoin(PageView, User.id == PageView.user_id
    ).filter(User.role != 'superadmin'
    ).group_by(User.id, User.name, User.email, User.role
    ).order_by(db.text('views DESC')).all()

    return jsonify([{
        'id': u_id, 'name': name, 'email': email, 'role': role, 'views': views
    } for u_id, name, email, role, views in user_stats])
