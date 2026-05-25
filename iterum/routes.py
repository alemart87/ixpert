"""Vistas HTML de Iterum (renderizan templates Jinja).

Las llamadas que devuelven JSON viven en iterum/api.py.
"""
from flask import Blueprint, render_template, request
from flask_login import login_required

from .permissions import iterum_required, iterum_editor_required, log_access

iterum_bp = Blueprint('iterum', __name__, url_prefix='/iterum')


@iterum_bp.route('/')
@login_required
@iterum_required
def index():
    """Landing: redirige a dashboard o muestra upload segun haya datos."""
    log_access('view', 'iterum', None, {'page': 'index'})
    return render_template('iterum/dashboard.html')


@iterum_bp.route('/upload')
@login_required
@iterum_editor_required
def upload_page():
    log_access('view', 'iterum', None, {'page': 'upload'})
    return render_template('iterum/upload.html')


@iterum_bp.route('/dashboard')
@login_required
@iterum_required
def dashboard():
    log_access('view', 'iterum', None, {'page': 'dashboard'})
    return render_template('iterum/dashboard.html')


@iterum_bp.route('/ranking')
@login_required
@iterum_required
def ranking():
    log_access('view', 'iterum', None, {'page': 'ranking'})
    return render_template('iterum/ranking.html')


@iterum_bp.route('/comments')
@login_required
@iterum_required
def comments():
    log_access('view', 'iterum', None, {'page': 'comments'})
    return render_template('iterum/comments.html')


@iterum_bp.route('/patterns')
@login_required
@iterum_required
def patterns():
    log_access('view', 'iterum', None, {'page': 'patterns'})
    return render_template('iterum/patterns.html')


@iterum_bp.route('/root-cause')
@login_required
@iterum_required
def root_cause():
    log_access('view', 'iterum', None, {'page': 'root_cause'})
    return render_template('iterum/root_cause.html')


@iterum_bp.route('/audit')
@login_required
@iterum_required
def audit():
    log_access('view', 'iterum', None, {'page': 'audit'})
    return render_template('iterum/audit.html')


@iterum_bp.route('/coaching')
@login_required
@iterum_required
def coaching():
    log_access('view', 'iterum', None, {'page': 'coaching'})
    return render_template('iterum/coaching.html')


@iterum_bp.route('/report')
@login_required
@iterum_required
def report():
    log_access('view', 'iterum', None, {'page': 'report'})
    return render_template('iterum/report.html')


# ===== Importar API endpoints (registran rutas en el mismo blueprint) =====
from . import api  # noqa: E402,F401
