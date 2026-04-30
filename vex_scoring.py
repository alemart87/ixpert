"""
Vex People Skill Predictive — scoring engine.

Agrega todas las sesiones completadas del usuario y produce el perfil
VexProfile (6 dimensiones, indice predictivo, categoria y recomendacion).

Mantiene la misma logica que estaba en training.py para no introducir
cambios funcionales en este commit; el split aisla esta funcion para
que las modificaciones futuras (ART, scoring banca) no requieran
re-subir el training.py completo (que tiene mas de 40KB).
"""
from datetime import datetime
from models import db, TrainingSession, TrainingScenario, VexProfile


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
        improvement_trend = max(0, min(1, (slope + 0.5) / 1.0))
    else:
        improvement_trend = 0.5

    # --- Dimension raw scores (0-100) ---
    comm_raw = (1 - min(spelling_rate * 10, 1)) * 50 + (avg_nps / 10) * 50
    empathy_raw = avg_nps * 10
    resolution_raw = correct_rate * 70 + (avg_nps / 10) * 30

    speed_wpm = min(100, (avg_wpm / 30) * 100)
    speed_dur = min(100, max(0, (600 - avg_duration) / 600 * 100))
    speed_raw = speed_wpm * 0.6 + speed_dur * 0.4

    variety = min(1, unique_scenarios / max(total_scenarios * 0.5, 1))
    adapt_raw = improvement_trend * 50 + variety * 50

    compliance_raw = correct_rate * 60 + (1 - min(spelling_rate * 10, 1)) * 40

    raw_scores = [comm_raw, empathy_raw, resolution_raw, speed_raw, adapt_raw, compliance_raw]

    # --- Convert to Sten scale (1-10) ---
    def to_sten(raw):
        sten = round(raw / 10)
        return max(1, min(10, sten))

    scores = [to_sten(r) for r in raw_scores]
    comm, empathy, resolution, speed, adapt, compliance = scores

    overall = round(sum(scores) / 6, 1)

    pi = (resolution * 0.25 + empathy * 0.20 + comm * 0.20 +
          speed * 0.15 + adapt * 0.10 + compliance * 0.10)
    pi_pct = round(pi * 10, 1)

    if all(s >= 8 for s in scores):
        category = 'elite'
    elif overall >= 7 and all(s >= 5 for s in scores):
        category = 'alto'
    elif overall >= 5:
        category = 'desarrollo'
    else:
        category = 'refuerzo'

    if pi_pct >= 70:
        rec = 'recomendado'
    elif pi_pct >= 50:
        rec = 'observaciones'
    else:
        rec = 'no_recomendado'

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
