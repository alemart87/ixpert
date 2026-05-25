"""Endpoints JSON de Iterum.

Cada endpoint:
1. Valida permisos via decorator
2. Parsea payload via schemas.py
3. Delega a un service
4. Loggea acceso en NPSAccessLog (para auditoria legal)
5. Devuelve JSON serializado
"""
import json
import os
import tempfile
from datetime import datetime, timezone

from flask import jsonify, request, send_file, abort, make_response
from flask_login import login_required, current_user

from models import db, User
from .routes import iterum_bp
from .permissions import (
    iterum_required, iterum_editor_required, iterum_admin_required, log_access,
)
from .models import (
    NPSUpload, NPSSurvey, NPSAudit, NPSRootCause, NPSCoaching, NPSReportSnapshot,
    NPSAccessLog,
)
from .schemas import (
    parse_filters, parse_audit_payload, parse_root_cause_payload,
    parse_coaching_payload, ValidationError,
)
from .services import scoring, audit as audit_svc, root_cause as rc_svc, coaching as coach_svc
from .services import reports as report_svc
from .services import analytics
from .services.dedup import file_hash
from .services.jobs import submit_upload_processing


# ============================================================================
# UPLOAD: recibe XLSX, encola procesamiento en background
# ============================================================================
@iterum_bp.route('/api/upload', methods=['POST'])
@login_required
@iterum_editor_required
def api_upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No se envio archivo'}), 400
    f = request.files['file']
    if not f.filename or not f.filename.lower().endswith(('.xlsx', '.xls')):
        return jsonify({'error': 'Formato invalido. Solo XLSX/XLS.'}), 400

    # Guardar a /tmp y calcular hash. El job borra el archivo despues.
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.xlsx', prefix='iterum_')
    os.close(tmp_fd)
    f.save(tmp_path)

    try:
        fhash = file_hash(tmp_path)
    except Exception as e:
        os.remove(tmp_path)
        return jsonify({'error': f'No se pudo leer el archivo: {e}'}), 400

    # Dedupe por file_hash. Si el upload previo del mismo archivo TERMINO BIEN
    # (done) o esta en curso (pending/processing), devolvemos el existente.
    # Si fallo, lo eliminamos para permitir reintentar (caso tipico: el parser
    # mejoro y ahora si puede procesar el archivo que antes fallaba).
    existing = NPSUpload.query.filter_by(file_hash=fhash).first()
    if existing:
        if existing.status == 'failed':
            db.session.delete(existing)
            db.session.commit()
            log_access('delete', 'upload', existing.id,
                       {'reason': 'retry_after_failure', 'file_hash': fhash})
        else:
            os.remove(tmp_path)
            return jsonify({
                'upload_id': existing.id,
                'status': existing.status,
                'duplicate_file': True,
                'message': 'Este archivo ya fue procesado anteriormente.',
            }), 200

    size = os.path.getsize(tmp_path)
    upload = NPSUpload(
        uploaded_by_id=current_user.id,
        filename=f.filename,
        file_hash=fhash,
        file_size_bytes=size,
        status='pending',
    )
    db.session.add(upload)
    db.session.commit()

    log_access('upload', 'upload', upload.id,
               {'filename': f.filename, 'size': size})

    from flask import current_app
    submit_upload_processing(current_app._get_current_object(), upload.id, tmp_path)

    return jsonify({
        'upload_id': upload.id,
        'status': 'pending',
        'message': 'Archivo en cola, procesando...',
    }), 202


@iterum_bp.route('/api/upload/<int:upload_id>/status')
@login_required
@iterum_required
def api_upload_status(upload_id):
    u = db.session.get(NPSUpload, upload_id)
    if not u:
        return jsonify({'error': 'No encontrado'}), 404
    return jsonify({
        'id': u.id,
        'status': u.status,
        'filename': u.filename,
        'rows_total': u.rows_total,
        'rows_new': u.rows_new,
        'rows_duplicate': u.rows_duplicate,
        'rows_invalid': u.rows_invalid,
        'period_start': u.period_start.isoformat() if u.period_start else None,
        'period_end': u.period_end.isoformat() if u.period_end else None,
        'error': u.error_message,
        'created_at': u.created_at.isoformat() if u.created_at else None,
        'processed_at': u.processed_at.isoformat() if u.processed_at else None,
    })


@iterum_bp.route('/api/upload/<int:upload_id>', methods=['DELETE'])
@login_required
@iterum_editor_required
def api_upload_delete(upload_id):
    """Elimina un upload Y todas las encuestas que trajo (cascada).
    Las nps_audit, nps_root_cause y nps_access_log relacionadas tambien
    se borran por cascade='all, delete-orphan' definido en los modelos.
    """
    u = db.session.get(NPSUpload, upload_id)
    if not u:
        return jsonify({'error': 'No encontrado'}), 404

    # Contar surveys antes de borrar (para el log de auditoria)
    n_surveys = NPSSurvey.query.filter_by(upload_id=upload_id).count()

    # Borrar surveys en bulk (cascade borra audit/root_cause asociados via ORM)
    surveys = NPSSurvey.query.filter_by(upload_id=upload_id).all()
    for s in surveys:
        db.session.delete(s)
    db.session.delete(u)
    db.session.commit()

    log_access('delete', 'upload', upload_id,
               {'filename': u.filename, 'surveys_deleted': n_surveys})
    return jsonify({'deleted': True, 'surveys_deleted': n_surveys})


@iterum_bp.route('/api/uploads')
@login_required
@iterum_required
def api_upload_list():
    rows = NPSUpload.query.order_by(NPSUpload.created_at.desc()).limit(50).all()
    out = []
    for u in rows:
        out.append({
            'id': u.id, 'filename': u.filename, 'status': u.status,
            'rows_new': u.rows_new, 'rows_duplicate': u.rows_duplicate,
            'rows_invalid': u.rows_invalid,
            'rows_total': u.rows_total,
            'uploaded_by': u.uploader.name if u.uploader else '',
            'created_at': u.created_at.isoformat() if u.created_at else None,
            'error_message': u.error_message,
        })
    return jsonify({'uploads': out})


# ============================================================================
# SURVEYS: listar (paginado, filtros)
# ============================================================================
@iterum_bp.route('/api/surveys')
@login_required
@iterum_required
def api_surveys():
    try:
        filters = parse_filters(request.args)
    except ValidationError as e:
        return jsonify({'error': str(e)}), 400

    page = max(1, int(request.args.get('page', 1)))
    per_page = min(100, max(10, int(request.args.get('per_page', 50))))

    q = NPSSurvey.query
    if filters.get('channel'):
        q = q.filter(NPSSurvey.channel == filters['channel'])
    if filters.get('cell'):
        q = q.filter(NPSSurvey.cell == filters['cell'])
    if filters.get('agent_doc'):
        q = q.filter(NPSSurvey.agent_doc == filters['agent_doc'])
    if filters.get('from_date'):
        q = q.filter(NPSSurvey.response_date >= filters['from_date'])
    if filters.get('to_date'):
        q = q.filter(NPSSurvey.response_date < filters['to_date'])

    category = request.args.get('category')
    if category in ('promotor', 'pasivo', 'detractor'):
        q = q.filter(NPSSurvey.category == category)

    search = (request.args.get('q') or '').strip()
    if search:
        q = q.filter(NPSSurvey.comment.ilike(f'%{search}%'))

    total = q.count()
    rows = q.order_by(NPSSurvey.response_date.desc()).offset((page - 1) * per_page).limit(per_page).all()

    log_access('view', 'survey', None,
               {'filters': {k: str(v) for k, v in filters.items()},
                'page': page, 'total': total})

    return jsonify({
        'page': page, 'per_page': per_page, 'total': total,
        'surveys': [{
            'id': s.id,
            'response_date': s.response_date.isoformat() if s.response_date else None,
            'channel': s.channel,
            'cell': s.cell,
            'agent_name': s.agent_name,
            'agent_doc': s.agent_doc,
            'nps_score': s.nps_score,
            'category': s.category,
            'comment': s.comment,
            'client_name': s.client_name,
            'gender': s.gender,
            'effort': s.effort,
            'resolution': s.resolution,
            'motive': s.motive,
            'gestion_type': s.gestion_type,
            'origin': s.origin,
            'problem_description': s.problem_description,
            'why_1': s.why_1, 'why_2': s.why_2, 'why_3': s.why_3,
            'root_cause_type': s.root_cause_type,
            'responsibility': s.responsibility,
            'audit': {
                'verdict': s.audit.verdict if s.audit else None,
                'classification': s.audit.classification if s.audit else None,
            } if s.audit else None,
        } for s in rows]
    })


@iterum_bp.route('/api/surveys/<int:survey_id>')
@login_required
@iterum_required
def api_survey_detail(survey_id):
    s = db.session.get(NPSSurvey, survey_id)
    if not s:
        return jsonify({'error': 'No encontrada'}), 404
    log_access('view', 'survey', s.id)
    return jsonify({
        'id': s.id,
        'response_date': s.response_date.isoformat() if s.response_date else None,
        'channel': s.channel, 'cell': s.cell,
        'agent_name': s.agent_name, 'agent_doc': s.agent_doc,
        'nps_score': s.nps_score, 'category': s.category,
        'comment': s.comment,
        'audit': _audit_to_dict(s.audit),
        'root_cause': _root_cause_to_dict(s.root_cause),
    })


# ============================================================================
# KPIs: dashboard, ranking, breakdown
# ============================================================================
@iterum_bp.route('/api/kpi/dashboard')
@login_required
@iterum_required
def api_kpi_dashboard():
    try:
        filters = parse_filters(request.args)
    except ValidationError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({
        'kpis': scoring.dashboard_kpis(**filters),
        'channels': scoring.channel_breakdown(**filters),
        'cells': scoring.cell_breakdown(**filters),
        'timeseries': scoring.nps_timeseries(
            granularity=request.args.get('granularity', 'day'), **filters),
    })


@iterum_bp.route('/api/analytics/dashboard')
@login_required
@iterum_required
def api_analytics_dashboard():
    """Dashboard enriquecido completo: KPIs + género + esfuerzo + resolución."""
    try:
        filters = parse_filters(request.args)
    except ValidationError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({
        'kpis': analytics.dashboard_full(**filters),
        'gender': analytics.gender_breakdown(**filters),
        'unknown_names': analytics.unknown_gender_names(**filters),
        'effort': analytics.effort_distribution(**filters),
        'resolution': analytics.resolution_stats(**filters),
        'composition': scoring.dashboard_kpis(**filters),
        'nps_target': analytics.OBJETIVO_NPS_CANAL,
    })


@iterum_bp.route('/api/analytics/patterns')
@login_required
@iterum_required
def api_analytics_patterns():
    try:
        filters = parse_filters(request.args)
    except ValidationError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({
        'keywords': analytics.keyword_patterns(**filters),
        'origin': analytics.origin_breakdown(**filters),
        'top_alerts': analytics.top_alert_agents(**filters),
        'critical_cases': [{
            'id': r['id'], 'agent_name': r['agent_name'],
            'problem_description': r['problem_description'],
            'comment_snippet': (r['problem_description'] or '')[:200],
        } for r in analytics.root_cause_chain(**filters)[:5]],
    })


@iterum_bp.route('/api/analytics/root-cause')
@login_required
@iterum_required
def api_analytics_root_cause():
    try:
        filters = parse_filters(request.args)
    except ValidationError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({
        'charts': analytics.root_cause_analytics(**filters),
        'chain': analytics.root_cause_chain(**filters),
    })


@iterum_bp.route('/api/analytics/audit-review')
@login_required
@iterum_required
def api_analytics_audit_review():
    """Stats + lista de detractores para revisar etiquetado."""
    try:
        filters = parse_filters(request.args)
    except ValidationError as e:
        return jsonify({'error': str(e)}), 400
    stats = analytics.audit_review_stats(**filters)
    review_filter = request.args.get('review_status')
    q = NPSSurvey.query.filter(NPSSurvey.category == 'detractor')
    if filters.get('cell'): q = q.filter(NPSSurvey.cell == filters['cell'])
    if filters.get('channel'): q = q.filter(NPSSurvey.channel == filters['channel'])
    if filters.get('from_date'): q = q.filter(NPSSurvey.response_date >= filters['from_date'])
    if filters.get('to_date'): q = q.filter(NPSSurvey.response_date < filters['to_date'])
    if review_filter:
        q = q.filter(NPSSurvey.review_status == review_filter)
    rows = q.order_by(NPSSurvey.response_date.desc()).limit(100).all()
    return jsonify({
        'stats': stats,
        'cases': [_survey_review_dict(s) for s in rows],
    })


@iterum_bp.route('/api/analytics/audit-review/<int:survey_id>', methods=['POST'])
@login_required
@iterum_editor_required
def api_audit_review_set(survey_id):
    """Marca un survey como correcto/dudoso/incorrecto."""
    from datetime import datetime, timezone
    data = request.get_json(silent=True) or {}
    status = (data.get('status') or '').strip().lower()
    if status not in ('sin_revisar', 'correcto', 'dudoso', 'incorrecto'):
        return jsonify({'error': 'status invalido'}), 400
    s = db.session.get(NPSSurvey, survey_id)
    if not s: return jsonify({'error': 'No encontrado'}), 404
    s.review_status = status
    s.review_note = data.get('note') or None
    s.reviewed_by_id = current_user.id
    s.reviewed_at = datetime.now(timezone.utc)
    db.session.commit()
    log_access('update', 'survey_review', s.id, {'status': status})
    return jsonify({'status': status})


@iterum_bp.route('/api/analytics/coaching')
@login_required
@iterum_required
def api_analytics_coaching():
    try:
        filters = parse_filters(request.args)
    except ValidationError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({
        'stats': analytics.coaching_stats(**filters),
        'agents': analytics.coaching_by_agent(**filters),
    })


@iterum_bp.route('/api/kpi/ranking')
@login_required
@iterum_required
def api_kpi_ranking():
    try:
        filters = parse_filters(request.args)
    except ValidationError as e:
        return jsonify({'error': str(e)}), 400
    sort = request.args.get('sort', 'nps')
    min_resp = max(1, int(request.args.get('min_responses', 1)))
    limit_arg = request.args.get('limit')
    limit = int(limit_arg) if limit_arg else None
    return jsonify({
        'ranking': scoring.agent_ranking(
            limit=limit, min_responses=min_resp, sort=sort, **filters),
    })


# ============================================================================
# AUDIT
# ============================================================================
@iterum_bp.route('/api/audit/<int:survey_id>', methods=['POST', 'PUT'])
@login_required
@iterum_editor_required
def api_audit_upsert(survey_id):
    try:
        data = parse_audit_payload(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({'error': str(e)}), 400

    try:
        a = audit_svc.upsert_audit(
            survey_id=survey_id, reviewer_id=current_user.id, **data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    log_access('update', 'audit', a.id, {'survey_id': survey_id, **data})
    return jsonify(_audit_to_dict(a))


@iterum_bp.route('/api/audit')
@login_required
@iterum_required
def api_audit_list():
    reviewer_id = request.args.get('reviewer_id', type=int)
    verdict = request.args.get('verdict')
    rows = audit_svc.list_audits(reviewer_id=reviewer_id, verdict=verdict)
    return jsonify({'audits': [_audit_to_dict(a) for a in rows]})


# ============================================================================
# ROOT CAUSE (5 Whys)
# ============================================================================
@iterum_bp.route('/api/root-cause/<int:survey_id>', methods=['POST', 'PUT'])
@login_required
@iterum_editor_required
def api_root_cause_upsert(survey_id):
    try:
        data = parse_root_cause_payload(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({'error': str(e)}), 400

    try:
        rc = rc_svc.upsert_root_cause(
            survey_id=survey_id, created_by_id=current_user.id, **data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    log_access('update', 'root_cause', rc.id, {'survey_id': survey_id})
    return jsonify(_root_cause_to_dict(rc))


@iterum_bp.route('/api/root-cause/<int:survey_id>')
@login_required
@iterum_required
def api_root_cause_get(survey_id):
    rc = NPSRootCause.query.filter_by(survey_id=survey_id).first()
    return jsonify(_root_cause_to_dict(rc))


@iterum_bp.route('/api/root-causes')
@login_required
@iterum_required
def api_root_cause_list():
    rows = rc_svc.list_open_root_causes()
    return jsonify({'root_causes': [_root_cause_to_dict(rc) for rc in rows]})


# ============================================================================
# COACHING
# ============================================================================
@iterum_bp.route('/api/coaching', methods=['POST'])
@login_required
@iterum_editor_required
def api_coaching_create():
    try:
        data = parse_coaching_payload(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({'error': str(e)}), 400

    try:
        c = coach_svc.create_coaching(coach_id=current_user.id, **data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    log_access('create', 'coaching', c.id, {'agent_doc': data['agent_doc']})
    return jsonify(_coaching_to_dict(c)), 201


@iterum_bp.route('/api/coaching/<int:coaching_id>', methods=['PATCH'])
@login_required
@iterum_editor_required
def api_coaching_update(coaching_id):
    data = request.get_json(silent=True) or {}
    try:
        c = coach_svc.update_coaching(coaching_id, **data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    log_access('update', 'coaching', c.id, data)
    return jsonify(_coaching_to_dict(c))


@iterum_bp.route('/api/coaching')
@login_required
@iterum_required
def api_coaching_list():
    coach_id = request.args.get('coach_id', type=int)
    status = request.args.get('status')
    agent_doc = request.args.get('agent_doc')
    rows = coach_svc.list_coaching(coach_id=coach_id, status=status, agent_doc=agent_doc)
    return jsonify({'coaching': [_coaching_to_dict(c) for c in rows]})


# ============================================================================
# REPORT (snapshot + PDF nativo)
# ============================================================================
@iterum_bp.route('/api/report/preview')
@login_required
@iterum_required
def api_report_preview():
    """Devuelve payload del reporte sin persistir."""
    try:
        filters = parse_filters(request.args)
    except ValidationError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify(report_svc.build_report_payload(**filters))


@iterum_bp.route('/api/report/snapshot', methods=['POST'])
@login_required
@iterum_admin_required
def api_report_snapshot():
    """Persiste un reporte ejecutivo."""
    data = request.get_json(silent=True) or {}
    try:
        filters = parse_filters(data)
    except ValidationError as e:
        return jsonify({'error': str(e)}), 400

    period_label = (data.get('period_label') or '').strip() or 'Sin etiqueta'
    payload = report_svc.build_report_payload(**filters)
    html = report_svc.render_report_html(payload, period_label=period_label)
    snap = report_svc.save_snapshot(
        generated_by_id=current_user.id,
        period_label=period_label,
        filters={k: (v.isoformat() if hasattr(v, 'isoformat') else v)
                 for k, v in filters.items()},
        payload=payload,
        html=html,
    )
    log_access('create', 'report', snap.id, {'period': period_label})
    return jsonify({'id': snap.id, 'period_label': snap.period_label}), 201


@iterum_bp.route('/api/report/<int:snap_id>.html')
@login_required
@iterum_required
def api_report_html(snap_id):
    snap = db.session.get(NPSReportSnapshot, snap_id)
    if not snap:
        abort(404)
    log_access('view', 'report', snap.id)
    resp = make_response(snap.html_blob or '')
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    return resp


@iterum_bp.route('/api/report/<int:snap_id>.pdf')
@login_required
@iterum_required
def api_report_pdf(snap_id):
    snap = db.session.get(NPSReportSnapshot, snap_id)
    if not snap:
        abort(404)
    try:
        pdf_bytes = report_svc.render_pdf(snap.html_blob or '')
    except ImportError:
        return jsonify({
            'error': 'PDF nativo no disponible (WeasyPrint no instalado). '
                     'Usa la opcion imprimir del navegador.'
        }), 503
    except Exception as e:
        return jsonify({'error': f'No se pudo generar PDF: {e}'}), 500

    log_access('export', 'report', snap.id, {'format': 'pdf'})
    from io import BytesIO
    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'iterum-report-{snap.id}.pdf',
    )


@iterum_bp.route('/api/reports')
@login_required
@iterum_required
def api_reports_list():
    rows = NPSReportSnapshot.query.order_by(NPSReportSnapshot.created_at.desc()).limit(50).all()
    return jsonify({
        'reports': [{
            'id': r.id,
            'period_label': r.period_label,
            'generated_by': r.generated_by.name if r.generated_by else '',
            'created_at': r.created_at.isoformat() if r.created_at else None,
        } for r in rows]
    })


# ============================================================================
# ACCESS LOG (auditoria legal — solo superadmin)
# ============================================================================
@iterum_bp.route('/api/access-log')
@login_required
@iterum_admin_required
def api_access_log():
    limit = min(500, max(10, int(request.args.get('limit', 100))))
    action = request.args.get('action')
    entity_type = request.args.get('entity_type')
    user_id = request.args.get('user_id', type=int)

    q = NPSAccessLog.query
    if action:
        q = q.filter(NPSAccessLog.action == action)
    if entity_type:
        q = q.filter(NPSAccessLog.entity_type == entity_type)
    if user_id:
        q = q.filter(NPSAccessLog.user_id == user_id)
    rows = q.order_by(NPSAccessLog.created_at.desc()).limit(limit).all()

    return jsonify({
        'entries': [{
            'id': r.id,
            'user': r.user.name if r.user else '',
            'user_email': r.user.email if r.user else '',
            'action': r.action,
            'entity_type': r.entity_type,
            'entity_id': r.entity_id,
            'ip_address': r.ip_address,
            'created_at': r.created_at.isoformat() if r.created_at else None,
            'payload': r.payload_json,
        } for r in rows]
    })


# ============================================================================
# META: filtros disponibles (celulas, canales, etc.)
# ============================================================================
@iterum_bp.route('/api/meta/filters')
@login_required
@iterum_required
def api_meta_filters():
    """Listas de valores unicos para poblar dropdowns de filtros."""
    cells = [c[0] for c in db.session.query(NPSSurvey.cell).distinct().all() if c[0]]
    channels = [c[0] for c in db.session.query(NPSSurvey.channel).distinct().all() if c[0]]
    return jsonify({
        'cells': sorted(cells),
        'channels': sorted(channels),
    })


# ============================================================================
# Serializadores helpers
# ============================================================================
def _survey_review_dict(s):
    return {
        'id': s.id,
        'agent_name': s.agent_name,
        'client_name': s.client_name,
        'cell': s.cell,
        'channel': s.channel,
        'response_date': s.response_date.isoformat() if s.response_date else None,
        'nps_score': s.nps_score,
        'motive': s.motive,
        'origin': s.origin,
        'responsibility': s.responsibility,
        'root_cause_type': s.root_cause_type,
        'why_1': s.why_1, 'why_2': s.why_2, 'why_3': s.why_3,
        'review_status': s.review_status or 'sin_revisar',
        'review_note': s.review_note,
    }


def _audit_to_dict(a):
    if not a:
        return None
    return {
        'id': a.id,
        'survey_id': a.survey_id,
        'reviewer_id': a.reviewer_id,
        'reviewer_name': a.reviewer.name if a.reviewer else '',
        'verdict': a.verdict,
        'classification': a.classification,
        'notes': a.notes,
        'reviewed_at': a.reviewed_at.isoformat() if a.reviewed_at else None,
        'updated_at': a.updated_at.isoformat() if a.updated_at else None,
    }


def _root_cause_to_dict(rc):
    if not rc:
        return None
    return {
        'id': rc.id,
        'survey_id': rc.survey_id,
        'why_1': rc.why_1, 'why_2': rc.why_2, 'why_3': rc.why_3,
        'why_4': rc.why_4, 'why_5': rc.why_5,
        'root_cause': rc.root_cause,
        'action_owner_id': rc.action_owner_id,
        'action_owner_name': rc.action_owner.name if rc.action_owner else '',
        'due_date': rc.due_date.isoformat() if rc.due_date else None,
        'status': rc.status,
        'created_at': rc.created_at.isoformat() if rc.created_at else None,
    }


def _coaching_to_dict(c):
    if not c:
        return None
    return {
        'id': c.id,
        'agent_doc': c.agent_doc,
        'agent_name': c.agent_name,
        'coach_id': c.coach_id,
        'coach_name': c.coach.name if c.coach else '',
        'urgency': c.urgency,
        'status': c.status,
        'topic': c.topic,
        'notes': c.notes,
        'related_survey_ids': c.related_survey_ids,
        'scheduled_at': c.scheduled_at.isoformat() if c.scheduled_at else None,
        'completed_at': c.completed_at.isoformat() if c.completed_at else None,
        'created_at': c.created_at.isoformat() if c.created_at else None,
    }
