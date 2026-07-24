"""Registro de resultados de Quiz.

Los quiz de iXpert son contenidos del CMS renderizados dentro de un iframe
(`srcdoc` + sandbox `allow-same-origin`), por lo que el JS del quiz corre en el
MISMO origen que la app y puede llamar a esta API con la cookie de sesion. Eso
permite registrar quien rindio cada quiz sin pedirle nada al usuario.

Hay tres caminos de captura, de mas a menos exacto:
  1. 'trivia' — la plantilla stock llama a la API con el puntaje real.
  2. 'api'    — el HTML del quiz llama a window.iXpertQuiz.save({...}).
  3. 'auto'   — el bridge detecta la pantalla de resultados y parsea el puntaje.
"""
import json
import csv
import io
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, Response
from flask_login import login_required, current_user

from models import db, User, Content, QuizResult

quizzes_bp = Blueprint('quizzes', __name__)

# Umbral de aprobacion por defecto (%). Un quiz puede mandar el suyo propio.
DEFAULT_PASS_THRESHOLD = 70

# Ventana anti-duplicados: el detector automatico puede disparar dos veces
# (ej: la pantalla de resultados se re-renderiza). Si llega un resultado
# identico del mismo usuario y quiz dentro de esta ventana, no se duplica.
DEDUPE_WINDOW_SECONDS = 90


def can_view_quizzes(f):
    """SuperAdmin, Analista y Supervisor pueden ver los resultados del equipo.

    Es el pedido explicito del negocio: el supervisor necesita ver como le fue
    a cada persona en la capacitacion. El asesor solo ve lo suyo.
    """
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.role in ('superadmin', 'analista', 'supervisor'):
            return f(*args, **kwargs)
        flash('No tienes permisos para ver los resultados de quiz.', 'error')
        return redirect(url_for('index'))
    return decorated


def _num(value, default=None):
    """Convierte a float tolerando strings con coma decimal y basura."""
    if value is None or value == '':
        return default
    try:
        if isinstance(value, str):
            value = value.strip().replace(',', '.')
        n = float(value)
    except (TypeError, ValueError):
        return default
    if n != n or n in (float('inf'), float('-inf')):  # NaN / inf
        return default
    return n


def _int(value, default=None):
    n = _num(value)
    return int(n) if n is not None else default


def _naive(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


@quizzes_bp.route('/api/quiz/result', methods=['POST'])
@login_required
def save_quiz_result():
    """Guarda el resultado de un quiz para el usuario logueado.

    El porcentaje se RECALCULA en el servidor a partir de los crudos siempre
    que se pueda: el payload viene de HTML del CMS y no queremos que un quiz
    mal escrito ensucie los rankings con porcentajes arbitrarios.
    """
    data = request.get_json(silent=True) or {}

    score = _num(data.get('score'))
    max_score = _num(data.get('max_score') or data.get('total'))
    correct = _int(data.get('correct_answers') or data.get('correct'))
    total_q = _int(data.get('total_questions') or data.get('questions'))

    # Porcentaje: preferimos derivarlo de los datos crudos, y entre esos
    # priorizamos correctas/preguntas sobre puntos. Los puntos pueden incluir
    # bonus (rachas, tiempo) y superar el maximo teorico, lo que distorsiona
    # la comparacion entre personas; "8 de 10 correctas" no tiene ese problema.
    percentage = None
    if correct is not None and total_q:
        percentage = correct / total_q * 100
    elif score is not None and max_score:
        percentage = score / max_score * 100
    else:
        percentage = _num(data.get('percentage'))

    if percentage is None:
        return jsonify({'error': 'Resultado sin puntaje interpretable'}), 400
    percentage = max(0.0, min(100.0, percentage))

    content_id = _int(data.get('content_id'))
    content = Content.query.get(content_id) if content_id else None
    quiz_slug = (data.get('quiz_slug') or (content.slug if content else '') or '')[:500]
    quiz_title = (data.get('quiz_title') or (content.title if content else '') or 'Quiz')[:500]

    if not quiz_slug and not content:
        return jsonify({'error': 'Quiz no identificado'}), 400

    threshold = _num(data.get('pass_threshold'), DEFAULT_PASS_THRESHOLD)

    # Anti-duplicados: mismo usuario, mismo quiz, mismo porcentaje, hace poco.
    cutoff = datetime.utcnow() - timedelta(seconds=DEDUPE_WINDOW_SECONDS)
    recent = QuizResult.query.filter(
        QuizResult.user_id == current_user.id,
        QuizResult.quiz_slug == quiz_slug
    ).order_by(QuizResult.created_at.desc()).first()
    if recent and _naive(recent.created_at) and _naive(recent.created_at) >= cutoff:
        if recent.percentage is not None and abs(recent.percentage - percentage) < 0.01:
            return jsonify({
                'ok': True, 'duplicate': True, 'result_id': recent.id,
                'attempt_number': recent.attempt_number,
                'percentage': round(recent.percentage, 1)
            })

    attempt = QuizResult.query.filter_by(
        user_id=current_user.id, quiz_slug=quiz_slug
    ).count() + 1

    detail = data.get('detail')
    detail_json = None
    if detail is not None:
        try:
            detail_json = json.dumps(detail, ensure_ascii=False)[:20000]
        except (TypeError, ValueError):
            detail_json = None

    source = data.get('source', 'api')
    if source not in ('api', 'trivia', 'auto'):
        source = 'api'

    result = QuizResult(
        user_id=current_user.id,
        content_id=content.id if content else None,
        quiz_slug=quiz_slug,
        quiz_title=quiz_title,
        score=score,
        max_score=max_score,
        correct_answers=correct,
        total_questions=total_q,
        percentage=round(percentage, 2),
        passed=percentage >= threshold,
        duration_seconds=max(0, _int(data.get('duration_seconds'), 0) or 0),
        attempt_number=attempt,
        source=source,
        detail=detail_json,
    )
    db.session.add(result)
    db.session.commit()

    return jsonify({
        'ok': True,
        'result_id': result.id,
        'attempt_number': attempt,
        'percentage': round(percentage, 1),
        'passed': result.passed,
        'user': current_user.name,
    })


@quizzes_bp.route('/api/quiz/my-results')
@login_required
def my_quiz_results():
    """Historial propio del usuario (para mostrarlo dentro del quiz)."""
    results = QuizResult.query.filter_by(user_id=current_user.id).order_by(
        QuizResult.created_at.desc()).limit(50).all()
    return jsonify([{
        'quiz': r.quiz_title,
        'slug': r.quiz_slug,
        'percentage': round(r.percentage, 1) if r.percentage is not None else None,
        'passed': r.passed,
        'attempt': r.attempt_number,
        'date': _naive(r.created_at).strftime('%d/%m/%Y %H:%M') if r.created_at else ''
    } for r in results])


# ===== Panel de resultados (SuperAdmin / Analista / Supervisor) =====

@quizzes_bp.route('/admin/quizzes')
@can_view_quizzes
def admin_quiz_results():
    return render_template('admin/quiz_results.html')


def _filtered_results():
    """Aplica los filtros de la query string y devuelve (results, meta)."""
    date_from = request.args.get('from', '')
    date_to = request.args.get('to', '')
    quiz_slug = request.args.get('quiz', '')

    q = QuizResult.query
    if date_from:
        dt_from = datetime.strptime(date_from, '%Y-%m-%d')
        q = q.filter(QuizResult.created_at >= dt_from)
    if date_to:
        dt_to = datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        q = q.filter(QuizResult.created_at <= dt_to)
    if quiz_slug:
        q = q.filter(QuizResult.quiz_slug == quiz_slug)

    return q.order_by(QuizResult.created_at.desc()).all()


@quizzes_bp.route('/admin/api/quizzes/results')
@can_view_quizzes
def api_quiz_results():
    results = _filtered_results()

    # Lista de quizzes disponibles para el selector (siempre completa, sin que
    # el filtro activo la recorte: si no, al elegir un quiz desaparecen los otros).
    all_quizzes = db.session.query(
        QuizResult.quiz_slug, QuizResult.quiz_title,
        db.func.count(QuizResult.id)
    ).group_by(QuizResult.quiz_slug, QuizResult.quiz_title).all()

    total = len(results)
    participants = len({r.user_id for r in results})
    avg_pct = sum(r.percentage or 0 for r in results) / total if total else 0
    passed = sum(1 for r in results if r.passed)
    pass_rate = passed / total * 100 if total else 0

    # Resumen por usuario: mejor intento, ultimo intento y cantidad de intentos.
    by_user = {}
    for r in sorted(results, key=lambda x: _naive(x.created_at) or datetime.min):
        u = by_user.setdefault(r.user_id, {
            'name': r.user.name if r.user else 'Desconocido',
            'email': r.user.email if r.user else '',
            'role': r.user.role if r.user else '',
            'attempts': 0, 'best': 0, 'last': 0, 'last_date': '',
            'passed': False, 'quizzes': set(),
        })
        u['attempts'] += 1
        pct = r.percentage or 0
        u['best'] = max(u['best'], pct)
        u['last'] = pct
        u['last_date'] = _naive(r.created_at).strftime('%d/%m/%Y %H:%M') if r.created_at else ''
        u['passed'] = u['passed'] or bool(r.passed)
        u['quizzes'].add(r.quiz_title)

    users_summary = sorted([{
        'name': u['name'], 'email': u['email'], 'role': u['role'],
        'attempts': u['attempts'],
        'best': round(u['best'], 1), 'last': round(u['last'], 1),
        'last_date': u['last_date'], 'passed': u['passed'],
        'quizzes': sorted(u['quizzes']),
    } for u in by_user.values()], key=lambda x: x['best'], reverse=True)

    # Resumen por quiz
    by_quiz = {}
    for r in results:
        qz = by_quiz.setdefault(r.quiz_slug, {
            'title': r.quiz_title, 'slug': r.quiz_slug,
            'attempts': 0, 'users': set(), 'total_pct': 0, 'passed': 0,
        })
        qz['attempts'] += 1
        qz['users'].add(r.user_id)
        qz['total_pct'] += (r.percentage or 0)
        if r.passed:
            qz['passed'] += 1

    quizzes_summary = sorted([{
        'title': q['title'], 'slug': q['slug'],
        'attempts': q['attempts'], 'participants': len(q['users']),
        'avg': round(q['total_pct'] / q['attempts'], 1) if q['attempts'] else 0,
        'pass_rate': round(q['passed'] / q['attempts'] * 100) if q['attempts'] else 0,
    } for q in by_quiz.values()], key=lambda x: x['attempts'], reverse=True)

    return jsonify({
        'stats': {
            'total_attempts': total,
            'participants': participants,
            'avg_percentage': round(avg_pct, 1),
            'pass_rate': round(pass_rate, 1),
        },
        'available_quizzes': [
            {'slug': s, 'title': t, 'attempts': c} for s, t, c in all_quizzes
        ],
        'users': users_summary,
        'quizzes': quizzes_summary,
        'attempts': [{
            'id': r.id,
            'user': r.user.name if r.user else 'Desconocido',
            'email': r.user.email if r.user else '',
            'role': r.user.role if r.user else '',
            'quiz': r.quiz_title,
            'slug': r.quiz_slug,
            'percentage': round(r.percentage, 1) if r.percentage is not None else None,
            'score': r.score, 'max_score': r.max_score,
            'correct': r.correct_answers, 'total_questions': r.total_questions,
            'passed': r.passed,
            'attempt_number': r.attempt_number,
            'duration': r.duration_seconds or 0,
            'source': r.source,
            'date': _naive(r.created_at).strftime('%d/%m/%Y %H:%M') if r.created_at else '',
        } for r in results[:500]],
    })


@quizzes_bp.route('/admin/quizzes/export.csv')
@can_view_quizzes
def export_quiz_results():
    """Descarga de todos los resultados filtrados en CSV (para Excel)."""
    results = _filtered_results()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')  # ; para que Excel-ES separe columnas
    writer.writerow([
        'Usuario', 'Email', 'Rol', 'Quiz', 'Intento', 'Porcentaje',
        'Puntaje', 'Puntaje maximo', 'Correctas', 'Preguntas',
        'Aprobado', 'Duracion (seg)', 'Origen', 'Fecha'
    ])
    for r in results:
        writer.writerow([
            r.user.name if r.user else '',
            r.user.email if r.user else '',
            r.user.role if r.user else '',
            r.quiz_title or '',
            r.attempt_number or 1,
            f'{r.percentage:.1f}'.replace('.', ',') if r.percentage is not None else '',
            r.score if r.score is not None else '',
            r.max_score if r.max_score is not None else '',
            r.correct_answers if r.correct_answers is not None else '',
            r.total_questions if r.total_questions is not None else '',
            'SI' if r.passed else 'NO',
            r.duration_seconds or 0,
            r.source or '',
            _naive(r.created_at).strftime('%d/%m/%Y %H:%M') if r.created_at else '',
        ])

    stamp = datetime.utcnow().strftime('%Y%m%d_%H%M')
    # BOM para que Excel detecte UTF-8 y no rompa las tildes
    payload = '﻿' + output.getvalue()
    return Response(
        payload,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename=resultados_quiz_{stamp}.csv'}
    )
