"""Modelos SQLAlchemy de Iterum.

Comparten la instancia `db` definida en models.py raiz para no romper la sesion
global. Se importan desde iterum/__init__.py por efecto colateral al registrar
el blueprint, asi quedan registrados en `db.metadata` y db.create_all() los
detecta automaticamente.
"""
from datetime import datetime, timezone
from models import db


def _utcnow():
    return datetime.now(timezone.utc)


# ============================================================================
# NPSUpload — registro de cada XLSX cargado (auditoria de quien subio que)
# ============================================================================
class NPSUpload(db.Model):
    __tablename__ = 'nps_upload'

    id = db.Column(db.Integer, primary_key=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename = db.Column(db.String(255))
    file_hash = db.Column(db.String(64), unique=True, index=True)
    file_size_bytes = db.Column(db.Integer, default=0)

    # Estado del procesamiento en background
    # pending -> processing -> done | failed
    status = db.Column(db.String(20), default='pending', index=True)
    error_message = db.Column(db.Text)

    rows_total = db.Column(db.Integer, default=0)
    rows_new = db.Column(db.Integer, default=0)
    rows_duplicate = db.Column(db.Integer, default=0)
    rows_invalid = db.Column(db.Integer, default=0)

    period_start = db.Column(db.Date)
    period_end = db.Column(db.Date)

    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    processed_at = db.Column(db.DateTime)

    uploader = db.relationship('User', foreign_keys=[uploaded_by_id])


# ============================================================================
# NPSSurvey — una fila por respuesta NPS (granularidad atomica)
# ============================================================================
class NPSSurvey(db.Model):
    __tablename__ = 'nps_survey'

    id = db.Column(db.Integer, primary_key=True)
    upload_id = db.Column(db.Integer, db.ForeignKey('nps_upload.id'), index=True)

    response_date = db.Column(db.DateTime, index=True)
    channel = db.Column(db.String(20), index=True)        # whatsapp | call
    cell = db.Column(db.String(100), index=True)
    agent_name = db.Column(db.String(150))
    agent_doc = db.Column(db.String(50), index=True)
    nps_score = db.Column(db.Integer, index=True)
    category = db.Column(db.String(20), index=True)        # promotor | pasivo | detractor
    comment = db.Column(db.Text)

    # === Campos enriquecidos desde XLSX del banco ===
    client_name = db.Column(db.String(200))
    client_doc = db.Column(db.String(50))
    gender = db.Column(db.String(20))                      # Femenino | Masculino | No Detectado
    effort = db.Column(db.String(30))                      # Muy facil | Facil | Neutro | Dificil | Muy dificil
    resolution = db.Column(db.String(20))                  # Si | No | Parcial (de RESOLUCION)
    resolved = db.Column(db.String(20))                    # de Se_Resolvio (Si/No/Parcial)
    motive = db.Column(db.String(200))                     # Motivo_Cliente
    gestion_type = db.Column(db.String(100))               # Tipo_Gestion
    origin = db.Column(db.String(150))                     # Origen_Principal
    problem_description = db.Column(db.Text)               # Problema_Descrito
    why_1 = db.Column(db.Text)                             # Porque_1
    why_2 = db.Column(db.Text)                             # Porque_2
    why_3 = db.Column(db.Text)                             # Porque_3_Raiz
    root_cause_type = db.Column(db.String(100))            # Tipo_Causa_Raiz
    responsibility = db.Column(db.String(50))              # Depende_de (asesor/proceso/externo)

    # Auditoria de etiquetado (revisado por analista)
    review_status = db.Column(db.String(20), default='sin_revisar', index=True)
    # sin_revisar | correcto | dudoso | incorrecto
    review_note = db.Column(db.Text)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)

    # Dedupe a nivel respuesta (hash de date+agent+score+comment+channel)
    unique_hash = db.Column(db.String(64), unique=True, index=True)

    created_at = db.Column(db.DateTime, default=_utcnow)

    audit = db.relationship('NPSAudit', backref='survey', uselist=False,
                            cascade='all, delete-orphan')
    root_cause = db.relationship('NPSRootCause', backref='survey', uselist=False,
                                 cascade='all, delete-orphan')

    __table_args__ = (
        db.Index('ix_survey_channel_date', 'channel', 'response_date'),
        db.Index('ix_survey_cell_date', 'cell', 'response_date'),
        db.Index('ix_survey_agent_date', 'agent_doc', 'response_date'),
    )


# ============================================================================
# NPSAudit — veredicto operativo del analista por encuesta
# ============================================================================
class NPSAudit(db.Model):
    __tablename__ = 'nps_audit'

    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.Integer, db.ForeignKey('nps_survey.id'),
                          unique=True, nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    verdict = db.Column(db.String(10), index=True)         # ok | warn | err
    classification = db.Column(db.String(100))             # motivo
    notes = db.Column(db.Text)

    reviewed_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    reviewer = db.relationship('User', foreign_keys=[reviewer_id])


# ============================================================================
# NPSRootCause — 5 Porques para detractores
# ============================================================================
class NPSRootCause(db.Model):
    __tablename__ = 'nps_root_cause'

    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.Integer, db.ForeignKey('nps_survey.id'),
                          unique=True, nullable=False)

    why_1 = db.Column(db.Text)
    why_2 = db.Column(db.Text)
    why_3 = db.Column(db.Text)
    why_4 = db.Column(db.Text)
    why_5 = db.Column(db.Text)
    root_cause = db.Column(db.Text)

    action_owner_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='open', index=True)  # open|in_progress|done

    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    action_owner = db.relationship('User', foreign_keys=[action_owner_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])


# ============================================================================
# NPSCoaching — sesiones de coaching agendadas/realizadas
# ============================================================================
class NPSCoaching(db.Model):
    __tablename__ = 'nps_coaching'

    id = db.Column(db.Integer, primary_key=True)
    agent_doc = db.Column(db.String(50), index=True, nullable=False)
    agent_name = db.Column(db.String(150))
    coach_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # JSON array de survey ids relacionados (ej: detractores que motivaron el coaching)
    related_survey_ids = db.Column(db.Text)

    urgency = db.Column(db.String(10), default='med', index=True)   # low | med | high
    status = db.Column(db.String(20), default='pending', index=True)  # pending|done|skipped
    topic = db.Column(db.String(200))
    notes = db.Column(db.Text)

    scheduled_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    coach = db.relationship('User', foreign_keys=[coach_id])


# ============================================================================
# NPSReportSnapshot — reporte ejecutivo persistido (HTML + payload + PDF)
# ============================================================================
class NPSReportSnapshot(db.Model):
    __tablename__ = 'nps_report_snapshot'

    id = db.Column(db.Integer, primary_key=True)
    generated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    period_label = db.Column(db.String(100))
    filters_json = db.Column(db.Text)            # snapshot de filtros aplicados
    payload_json = db.Column(db.Text)            # KPIs serializados
    html_blob = db.Column(db.Text)               # HTML standalone del reporte
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)

    generated_by = db.relationship('User', foreign_keys=[generated_by_id])


# ============================================================================
# NPSAccessLog — Auditoria LEGAL: quien vio/edito que cuando
# ============================================================================
# Persiste accesos a datos sensibles (comentarios de clientes, veredictos
# operativos) y cambios para cumplimiento bancario interno.
class NPSAccessLog(db.Model):
    __tablename__ = 'nps_access_log'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True, nullable=False)

    # view | create | update | delete | export | login | upload
    action = db.Column(db.String(20), index=True, nullable=False)

    # Entidad afectada (survey, audit, coaching, report, upload)
    entity_type = db.Column(db.String(30), index=True)
    entity_id = db.Column(db.Integer, index=True)

    # Snapshot del cambio (JSON con before/after o filtros usados)
    payload_json = db.Column(db.Text)

    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)

    user = db.relationship('User', foreign_keys=[user_id])
