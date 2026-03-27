import os
import re
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import (db, User, TrainingScenario, TrainingSession, TrainingMessage,
                    TrainingViewPermission, VexProfile)
from datetime import datetime, timezone
from functools import wraps


def utcnow():
    return datetime.utcnow()


def safe_elapsed(start_dt):
    """Calculate elapsed seconds handling naive/aware datetime mix."""
    now = datetime.utcnow()
    if start_dt and start_dt.tzinfo:
        start_dt = start_dt.replace(tzinfo=None)
    return (now - start_dt).total_seconds() if start_dt else 0
from chat import call_openai

training_bp = Blueprint('training', __name__)


def superadmin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_superadmin:
            flash('No tienes permisos.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


def can_view_training(f):
    """SuperAdmin or supervisor with permission."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if current_user.is_superadmin:
            return f(*args, **kwargs)
        perm = TrainingViewPermission.query.filter_by(supervisor_id=current_user.id).first()
        if perm:
            return f(*args, **kwargs)
        flash('No tienes permisos para ver resultados de entrenamiento.', 'error')
        return redirect(url_for('index'))
    return decorated


# ===== User Routes =====

@training_bp.route('/training')
@login_required
def index():
    scenarios = TrainingScenario.query.filter_by(is_active=True).all()
    my_sessions = TrainingSession.query.filter_by(
        user_id=current_user.id
    ).order_by(TrainingSession.created_at.desc()).limit(10).all()
    active_session = TrainingSession.query.filter_by(
        user_id=current_user.id, status='active'
    ).first()
    return render_template('training/index.html',
                           scenarios=scenarios, my_sessions=my_sessions,
                           active_session=active_session)


@training_bp.route('/api/training/start/<int:scenario_id>', methods=['POST'])
@login_required
def start_session(scenario_id):
    scenario = TrainingScenario.query.get_or_404(scenario_id)

    # Check no active session
    active = TrainingSession.query.filter_by(user_id=current_user.id, status='active').first()
    if active:
        return jsonify({'error': 'Ya tienes una sesión activa', 'session_id': active.id}), 400

    session = TrainingSession(
        scenario_id=scenario.id,
        user_id=current_user.id,
        status='active',
        started_at=datetime.now(timezone.utc)
    )
    db.session.add(session)
    db.session.flush()

    # Generate first client message
    system_prompt = f"""Eres un cliente de Itaú Paraguay. Tu personalidad y situación:

{scenario.client_persona}

REGLAS:
- Actúa como un cliente REAL llamando al banco
- NO reveles que eres IA bajo ninguna circunstancia
- Reaccioná naturalmente a lo que dice el asesor
- Si el asesor resuelve bien tu problema, mostrá satisfacción gradual
- Si no te atiende bien, mostrá frustración realista pero sin insultar
- Respondé en español paraguayo natural
- Tus respuestas deben ser cortas (1-3 oraciones), como un cliente real en un chat
- Empezá la conversación describiendo tu problema o situación"""

    ai_messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': 'Iniciá la conversación como el cliente. Presentá tu problema.'}
    ]

    response_text, tokens = call_openai(ai_messages)

    # Save client's first message
    msg = TrainingMessage(
        session_id=session.id,
        role='client',
        content=response_text,
        word_count=len(response_text.split())
    )
    db.session.add(msg)
    session.tokens_used = tokens
    db.session.commit()

    return jsonify({
        'session_id': session.id,
        'session_name': f"Sesión {session.id} - {current_user.name}",
        'scenario_title': scenario.title,
        'first_message': response_text
    })


@training_bp.route('/training/session/<int:session_id>')
@login_required
def session_view(session_id):
    session = TrainingSession.query.filter_by(
        id=session_id, user_id=current_user.id
    ).first_or_404()
    return render_template('training/session.html', session=session)


@training_bp.route('/api/training/message', methods=['POST'])
@login_required
def send_message():
    data = request.get_json(silent=True) or {}
    session_id = data.get('session_id')
    message = data.get('message', '').strip()

    if not message or not session_id:
        return jsonify({'error': 'Datos incompletos'}), 400

    session = TrainingSession.query.filter_by(
        id=session_id, user_id=current_user.id, status='active'
    ).first()
    if not session:
        return jsonify({'error': 'Sesión no encontrada o finalizada'}), 404

    scenario = session.scenario
    word_count = len(message.split())

    # Save user message
    user_msg = TrainingMessage(
        session_id=session.id,
        role='user',
        content=message,
        word_count=word_count
    )
    db.session.add(user_msg)

    # Update session metrics
    session.total_messages = (session.total_messages or 0) + 1
    session.total_words_user = (session.total_words_user or 0) + word_count
    session.total_chars_user = (session.total_chars_user or 0) + len(message)

    # Calculate WPM
    elapsed = safe_elapsed(session.started_at)
    if elapsed > 0:
        session.words_per_minute = round(session.total_words_user / (elapsed / 60), 1)

    # Build conversation for OpenAI
    system_prompt = f"""Eres un cliente de Itaú Paraguay. Tu personalidad y situación:

{scenario.client_persona}

REGLAS:
- Actúa como un cliente REAL
- NO reveles que sos IA
- Reaccioná naturalmente al asesor
- Respuestas cortas (1-3 oraciones) como un cliente real en chat
- Si el asesor te ayuda bien, mostrá satisfacción
- Si no, mostrá frustración realista"""

    ai_messages = [{'role': 'system', 'content': system_prompt}]

    # Add conversation history
    for msg in session.messages:
        role = 'assistant' if msg.role == 'client' else 'user'
        ai_messages.append({'role': role, 'content': msg.content})

    response_text, tokens = call_openai(ai_messages)

    # Save client response
    client_msg = TrainingMessage(
        session_id=session.id,
        role='client',
        content=response_text,
        word_count=len(response_text.split())
    )
    db.session.add(client_msg)
    session.tokens_used = (session.tokens_used or 0) + tokens
    db.session.commit()

    return jsonify({
        'response': response_text,
        'metrics': {
            'messages': session.total_messages,
            'words': session.total_words_user,
            'wpm': session.words_per_minute,
            'elapsed_seconds': int(elapsed)
        }
    })


@training_bp.route('/api/training/end/<int:session_id>', methods=['POST'])
@login_required
def end_session(session_id):
    session = TrainingSession.query.filter_by(
        id=session_id, user_id=current_user.id, status='active'
    ).first()
    if not session:
        return jsonify({'error': 'Sesión no encontrada'}), 404

    scenario = session.scenario
    now = datetime.utcnow()

    # Calculate final metrics
    session.ended_at = now
    session.duration_seconds = int(safe_elapsed(session.started_at))
    if session.duration_seconds > 0 and session.total_words_user:
        session.words_per_minute = round(session.total_words_user / (session.duration_seconds / 60), 1)

    # Build full conversation text for evaluation
    conversation_text = ""
    for msg in session.messages:
        label = "ASESOR" if msg.role == 'user' else "CLIENTE"
        conversation_text += f"{label}: {msg.content}\n\n"

    # Get user messages for spelling check
    user_texts = ' '.join(m.content for m in session.messages if m.role == 'user')

    # Evaluate with OpenAI
    eval_prompt = f"""Evalúa la siguiente conversación entre un asesor bancario y un cliente simulado.

ESCENARIO: {scenario.title}
DESCRIPCIÓN: {scenario.description or ''}
RESPUESTA ESPERADA DEL ASESOR: {scenario.expected_response}

CONVERSACIÓN:
{conversation_text}

TEXTO DEL ASESOR (para revisar ortografía):
{user_texts}

Respondé EXACTAMENTE en este formato JSON (sin markdown, solo JSON puro):
{{
    "nps_score": <número del 0 al 10>,
    "response_correct": <true o false>,
    "spelling_errors": <número de errores ortográficos encontrados>,
    "feedback": "<retroalimentación detallada: qué hizo bien, qué debe mejorar, recomendaciones específicas>",
    "strengths": "<2-3 fortalezas observadas>",
    "improvements": "<2-3 áreas de mejora concretas>"
}}"""

    eval_messages = [
        {'role': 'system', 'content': 'Eres un evaluador experto en calidad de atención al cliente bancario. Evaluás con criterio CX profesional.'},
        {'role': 'user', 'content': eval_prompt}
    ]

    eval_response, eval_tokens = call_openai(eval_messages)
    session.tokens_used = (session.tokens_used or 0) + eval_tokens

    # Parse evaluation
    try:
        # Clean possible markdown wrapping
        clean = eval_response.strip()
        if clean.startswith('```'):
            clean = re.sub(r'^```\w*\n?', '', clean)
            clean = re.sub(r'\n?```$', '', clean)
        evaluation = json.loads(clean)

        session.nps_score = max(0, min(10, int(evaluation.get('nps_score', 5))))
        session.response_correct = evaluation.get('response_correct', False)
        session.spelling_errors = int(evaluation.get('spelling_errors', 0))
        session.ai_feedback = json.dumps({
            'feedback': evaluation.get('feedback', ''),
            'strengths': evaluation.get('strengths', ''),
            'improvements': evaluation.get('improvements', '')
        }, ensure_ascii=False)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[TRAINING] Eval parse error: {e}", flush=True)
        session.nps_score = 5
        session.response_correct = False
        session.spelling_errors = 0
        session.ai_feedback = json.dumps({
            'feedback': eval_response,
            'strengths': '',
            'improvements': ''
        }, ensure_ascii=False)

    session.status = 'completed'
    db.session.commit()

    # Auto-update Vex profile
    calculate_vex_profile(current_user.id)

    return jsonify({'ok': True, 'session_id': session.id})


@training_bp.route('/training/result/<int:session_id>')
@login_required
def result_view(session_id):
    session = TrainingSession.query.filter_by(id=session_id).first_or_404()
    # Allow own sessions or admin/permitted supervisor
    if session.user_id != current_user.id and not current_user.is_superadmin:
        perm = TrainingViewPermission.query.filter_by(supervisor_id=current_user.id).first()
        if not perm:
            flash('No tienes permisos.', 'error')
            return redirect(url_for('index'))
    return render_template('training/result.html', session=session)


# ===== Admin Routes =====

@training_bp.route('/admin/training')
@can_view_training
def admin_dashboard():
    return render_template('admin/training_dashboard.html')


@training_bp.route('/admin/training/scenarios')
@superadmin_required
def admin_scenarios():
    scenarios = TrainingScenario.query.order_by(TrainingScenario.created_at.desc()).all()
    return render_template('admin/training_scenarios.html', scenarios=scenarios)


@training_bp.route('/admin/training/scenarios/save', methods=['POST'])
@superadmin_required
def admin_scenario_save():
    s_id = request.form.get('id')
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    client_persona = request.form.get('client_persona', '').strip()
    expected_response = request.form.get('expected_response', '').strip()
    difficulty = request.form.get('difficulty', 'medio')
    category = request.form.get('category', '').strip()

    if not title or not client_persona or not expected_response:
        flash('Título, persona del cliente y respuesta esperada son obligatorios.', 'error')
        return redirect(url_for('training.admin_scenarios'))

    if s_id:
        s = TrainingScenario.query.get_or_404(int(s_id))
        s.title = title
        s.description = description
        s.client_persona = client_persona
        s.expected_response = expected_response
        s.difficulty = difficulty
        s.category = category
    else:
        s = TrainingScenario(
            title=title, description=description,
            client_persona=client_persona, expected_response=expected_response,
            difficulty=difficulty, category=category,
            created_by=current_user.id
        )
        db.session.add(s)

    db.session.commit()
    flash('Escenario guardado.', 'success')
    return redirect(url_for('training.admin_scenarios'))


@training_bp.route('/admin/training/scenarios/<int:s_id>/delete', methods=['POST'])
@superadmin_required
def admin_scenario_delete(s_id):
    s = TrainingScenario.query.get_or_404(s_id)
    s.is_active = False
    db.session.commit()
    flash('Escenario desactivado.', 'success')
    return redirect(url_for('training.admin_scenarios'))


@training_bp.route('/admin/training/permissions', methods=['POST'])
@superadmin_required
def admin_permissions():
    supervisor_id = request.form.get('supervisor_id')
    action = request.form.get('action', 'grant')

    if action == 'revoke':
        TrainingViewPermission.query.filter_by(supervisor_id=int(supervisor_id)).delete()
    else:
        existing = TrainingViewPermission.query.filter_by(supervisor_id=int(supervisor_id)).first()
        if not existing:
            perm = TrainingViewPermission(
                supervisor_id=int(supervisor_id),
                granted_by=current_user.id
            )
            db.session.add(perm)
    db.session.commit()
    flash('Permisos actualizados.', 'success')
    return redirect(url_for('training.admin_dashboard'))


@training_bp.route('/admin/api/training/insights')
@can_view_training
def api_training_insights():
    from sqlalchemy import func, cast, Date
    from datetime import timedelta

    date_from = request.args.get('from', '')
    date_to = request.args.get('to', '')

    if not date_from:
        dt_from = datetime(2020, 1, 1, tzinfo=timezone.utc)
    else:
        dt_from = datetime.strptime(date_from, '%Y-%m-%d').replace(tzinfo=timezone.utc)

    if not date_to:
        dt_to = datetime.now(timezone.utc)
    else:
        dt_to = datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)

    sessions = TrainingSession.query.filter(
        TrainingSession.status == 'completed',
        TrainingSession.created_at.between(dt_from, dt_to)
    ).all()

    total = len(sessions)
    avg_nps = sum(s.nps_score or 0 for s in sessions) / total if total else 0
    correct_rate = sum(1 for s in sessions if s.response_correct) / total * 100 if total else 0
    avg_wpm = sum(s.words_per_minute or 0 for s in sessions) / total if total else 0
    avg_duration = sum(s.duration_seconds or 0 for s in sessions) / total if total else 0

    # NPS per day
    nps_day = db.session.query(
        cast(TrainingSession.created_at, Date).label('date'),
        func.avg(TrainingSession.nps_score).label('avg_nps'),
        func.count(TrainingSession.id).label('count')
    ).filter(
        TrainingSession.status == 'completed',
        TrainingSession.created_at.between(dt_from, dt_to)
    ).group_by('date').order_by('date').all()

    # NPS distribution
    nps_dist = {i: 0 for i in range(11)}
    for s in sessions:
        if s.nps_score is not None:
            nps_dist[s.nps_score] = nps_dist.get(s.nps_score, 0) + 1

    # User rankings
    user_stats = {}
    for s in sessions:
        uid = s.user_id
        if uid not in user_stats:
            user_stats[uid] = {'name': s.user.name, 'role': s.user.role,
                               'sessions': 0, 'total_nps': 0, 'total_wpm': 0, 'correct': 0}
        user_stats[uid]['sessions'] += 1
        user_stats[uid]['total_nps'] += (s.nps_score or 0)
        user_stats[uid]['total_wpm'] += (s.words_per_minute or 0)
        if s.response_correct:
            user_stats[uid]['correct'] += 1

    rankings = []
    for uid, st in user_stats.items():
        rankings.append({
            'name': st['name'], 'role': st['role'],
            'sessions': st['sessions'],
            'avg_nps': round(st['total_nps'] / st['sessions'], 1),
            'avg_wpm': round(st['total_wpm'] / st['sessions'], 1),
            'correct_rate': round(st['correct'] / st['sessions'] * 100)
        })
    rankings.sort(key=lambda x: x['avg_nps'], reverse=True)

    # Scenario stats
    scenario_stats = {}
    for s in sessions:
        sid = s.scenario_id
        if sid not in scenario_stats:
            scenario_stats[sid] = {'title': s.scenario.title, 'difficulty': s.scenario.difficulty,
                                   'sessions': 0, 'total_nps': 0}
        scenario_stats[sid]['sessions'] += 1
        scenario_stats[sid]['total_nps'] += (s.nps_score or 0)

    scenarios_data = []
    for sid, st in scenario_stats.items():
        scenarios_data.append({
            'title': st['title'], 'difficulty': st['difficulty'],
            'sessions': st['sessions'],
            'avg_nps': round(st['total_nps'] / st['sessions'], 1)
        })

    # Recommendations
    recommendations = []
    if rankings:
        worst = min(rankings, key=lambda x: x['avg_nps'])
        if worst['avg_nps'] < 7 and worst['sessions'] >= 2:
            recommendations.append({
                'icon': '🎓', 'priority': 'alta',
                'title': f'{worst["name"]} necesita refuerzo',
                'desc': f'NPS promedio de {worst["avg_nps"]}/10 en {worst["sessions"]} sesiones. Programar capacitación personalizada.'
            })
        best = max(rankings, key=lambda x: x['avg_nps'])
        if best['avg_nps'] >= 9 and best['sessions'] >= 2:
            recommendations.append({
                'icon': '⭐', 'priority': 'info',
                'title': f'{best["name"]} es referente',
                'desc': f'NPS promedio de {best["avg_nps"]}/10. Considerar como mentor para el equipo.'
            })

    low_wpm = [r for r in rankings if r['avg_wpm'] < 20 and r['sessions'] >= 2]
    if low_wpm:
        recommendations.append({
            'icon': '⚡', 'priority': 'media',
            'title': f'{len(low_wpm)} usuario(s) con velocidad baja',
            'desc': 'WPM menor a 20. Practicar velocidad de tipeo y familiarización con procedimientos.'
        })

    if correct_rate < 60 and total >= 3:
        recommendations.append({
            'icon': '📋', 'priority': 'alta',
            'title': f'Tasa de acierto baja: {correct_rate:.0f}%',
            'desc': 'Menos del 60% de respuestas correctas. Revisar los escenarios y reforzar procedimientos.'
        })

    # Permissions
    supervisors = User.query.filter_by(role='supervisor', is_active_user=True).all()
    permissions = TrainingViewPermission.query.all()
    perm_ids = {p.supervisor_id for p in permissions}

    # Recent sessions
    recent = TrainingSession.query.filter_by(status='completed').order_by(
        TrainingSession.ended_at.desc()).limit(20).all()

    return jsonify({
        'stats': {
            'total_sessions': total,
            'avg_nps': round(avg_nps, 1),
            'correct_rate': round(correct_rate, 1),
            'avg_wpm': round(avg_wpm, 1),
            'avg_duration': round(avg_duration)
        },
        'nps_per_day': [{'date': str(d), 'avg_nps': round(float(n), 1), 'count': c} for d, n, c in nps_day],
        'nps_distribution': nps_dist,
        'rankings': rankings,
        'scenarios': scenarios_data,
        'recommendations': recommendations,
        'supervisors': [{'id': s.id, 'name': s.name, 'has_access': s.id in perm_ids} for s in supervisors],
        'recent_sessions': [{
            'id': s.id,
            'user': s.user.name,
            'scenario': s.scenario.title,
            'nps': s.nps_score,
            'wpm': s.words_per_minute,
            'correct': s.response_correct,
            'duration': s.duration_seconds,
            'date': s.ended_at.strftime('%d/%m/%Y %H:%M') if s.ended_at else ''
        } for s in recent]
    })


@training_bp.route('/admin/training/session/<int:session_id>/detail')
@can_view_training
def admin_session_detail(session_id):
    s = TrainingSession.query.get_or_404(session_id)
    feedback = {}
    try:
        feedback = json.loads(s.ai_feedback) if s.ai_feedback else {}
    except json.JSONDecodeError:
        feedback = {'feedback': s.ai_feedback or ''}

    return jsonify({
        'user': s.user.name,
        'scenario': s.scenario.title,
        'nps': s.nps_score,
        'correct': s.response_correct,
        'wpm': s.words_per_minute,
        'duration': s.duration_seconds,
        'spelling_errors': s.spelling_errors,
        'feedback': feedback,
        'messages': [{
            'role': m.role,
            'content': m.content,
            'created_at': m.created_at.strftime('%H:%M:%S') if m.created_at else ''
        } for m in s.messages]
    })


# ===== Vex People Skill Predictive =====

def calculate_vex_profile(user_id):
    """Calculate and update VexProfile for a user based on ALL completed sessions."""
    sessions = TrainingSession.query.filter_by(
        user_id=user_id, status='completed'
    ).all()

    if len(sessions) < 2:
        return None  # Minimum 2 sessions required

    # --- Raw metric aggregation ---
    total_sessions = len(sessions)
    total_words = sum(s.total_words_user or 0 for s in sessions)
    total_spelling = sum(s.spelling_errors or 0 for s in sessions)
    avg_nps = sum(s.nps_score or 0 for s in sessions) / total_sessions
    avg_wpm = sum(s.words_per_minute or 0 for s in sessions) / total_sessions
    avg_duration = sum(s.duration_seconds or 0 for s in sessions) / total_sessions
    correct_count = sum(1 for s in sessions if s.response_correct)
    correct_rate = correct_count / total_sessions
    spelling_rate = total_spelling / max(total_words, 1)
    unique_scenarios = len(set(s.scenario_id for s in sessions))
    total_scenarios = TrainingScenario.query.filter_by(is_active=True).count() or 1

    # Improvement trend (NPS slope across sessions ordered by date)
    sorted_sessions = sorted(sessions, key=lambda s: s.created_at or datetime.min)
    nps_values = [s.nps_score or 5 for s in sorted_sessions]
    if len(nps_values) >= 2:
        n = len(nps_values)
        x_mean = (n - 1) / 2
        y_mean = sum(nps_values) / n
        numerator = sum((i - x_mean) * (nps_values[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator > 0 else 0
        improvement_trend = max(0, min(1, (slope + 0.5) / 1.0))  # Normalize -0.5..+0.5 to 0..1
    else:
        improvement_trend = 0.5

    # --- Dimension raw scores (0-100) ---
    # 1. Communication: inverse spelling rate + message quality
    comm_raw = (1 - min(spelling_rate * 10, 1)) * 50 + (avg_nps / 10) * 50

    # 2. Empathy: primarily NPS (NPS captures how well agent treated the client)
    empathy_raw = avg_nps * 10  # 0-10 → 0-100

    # 3. Resolution: correct rate is king
    resolution_raw = correct_rate * 70 + (avg_nps / 10) * 30

    # 4. Speed: WPM normalized to 50 WPM benchmark + duration
    speed_wpm = min(100, (avg_wpm / 50) * 100)
    speed_dur = min(100, max(0, (600 - avg_duration) / 600 * 100))  # 600s = 10min benchmark
    speed_raw = speed_wpm * 0.6 + speed_dur * 0.4

    # 5. Adaptability: improvement + scenario variety
    variety = min(1, unique_scenarios / max(total_scenarios * 0.5, 1))
    adapt_raw = improvement_trend * 50 + variety * 50

    # 6. Compliance: correct rate + low errors
    compliance_raw = correct_rate * 60 + (1 - min(spelling_rate * 10, 1)) * 40

    raw_scores = [comm_raw, empathy_raw, resolution_raw, speed_raw, adapt_raw, compliance_raw]

    # --- Convert to Sten scale (1-10) ---
    def to_sten(raw):
        """Convert 0-100 raw score to 1-10 Sten using criterion-referenced approach."""
        sten = round(raw / 10)
        return max(1, min(10, sten))

    scores = [to_sten(r) for r in raw_scores]
    comm, empathy, resolution, speed, adapt, compliance = scores

    # --- Overall score (simple average) ---
    overall = round(sum(scores) / 6, 1)

    # --- Predictive Index (weighted composite) ---
    pi = (resolution * 0.25 + empathy * 0.20 + comm * 0.20 +
          speed * 0.15 + adapt * 0.10 + compliance * 0.10)
    pi_pct = round(pi * 10, 1)  # Convert to percentage (1-10 → 10-100%)

    # --- Profile Category ---
    if all(s >= 8 for s in scores):
        category = 'elite'
    elif overall >= 7 and all(s >= 5 for s in scores):
        category = 'alto'
    elif overall >= 5:
        category = 'desarrollo'
    else:
        category = 'refuerzo'

    # --- Recommendation ---
    if pi_pct >= 70:
        rec = 'recomendado'
    elif pi_pct >= 50:
        rec = 'observaciones'
    else:
        rec = 'no_recomendado'

    # --- Save/Update ---
    profile = VexProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        profile = VexProfile(user_id=user_id)
        db.session.add(profile)

    profile.communication_score = comm
    profile.empathy_score = empathy
    profile.resolution_score = resolution
    profile.speed_score = speed
    profile.adaptability_score = adapt
    profile.compliance_score = compliance
    profile.overall_score = overall
    profile.predictive_index = pi_pct
    profile.profile_category = category
    profile.recommendation = rec
    profile.sessions_analyzed = total_sessions
    profile.last_updated = datetime.utcnow()
    db.session.commit()

    return profile


# ===== Vex Routes =====

@training_bp.route('/admin/vex')
@superadmin_required
def vex_dashboard():
    profiles = VexProfile.query.join(User).order_by(VexProfile.overall_score.desc()).all()
    return render_template('admin/vex_dashboard.html', profiles=profiles)


@training_bp.route('/admin/vex/profile/<int:user_id>')
@superadmin_required
def vex_profile(user_id):
    # Recalculate before showing
    calculate_vex_profile(user_id)
    profile = VexProfile.query.filter_by(user_id=user_id).first_or_404()
    sessions = TrainingSession.query.filter_by(
        user_id=user_id, status='completed'
    ).order_by(TrainingSession.created_at.desc()).all()
    return render_template('admin/vex_profile.html', profile=profile, sessions=sessions)
