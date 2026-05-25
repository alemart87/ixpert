"""Tablas para el AI Analyst de Iterum (chats + mensajes + canvas).

- IterumAIChat: una conversacion. Titulo auto-generado por el LLM.
- IterumAIMessage: cada mensaje (user, assistant, tool_call, tool_output, reasoning).
- IterumAICanvas: workspace donde el modelo y el admin colaboran. 1:1 con chat.
"""
from datetime import datetime, timezone
from models import db


def _utcnow():
    return datetime.now(timezone.utc)


class IterumAIChat(db.Model):
    __tablename__ = 'iterum_ai_chat'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(200), default='Nueva conversacion')
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    last_message_at = db.Column(db.DateTime, default=_utcnow)
    total_tokens = db.Column(db.Integer, default=0)
    total_cost_usd = db.Column(db.Float, default=0.0)
    model = db.Column(db.String(50))
    archived = db.Column(db.Boolean, default=False, index=True)

    user = db.relationship('User', foreign_keys=[user_id])
    messages = db.relationship('IterumAIMessage', backref='chat', lazy=True,
                               cascade='all, delete-orphan',
                               order_by='IterumAIMessage.created_at')
    canvas = db.relationship('IterumAICanvas', backref='chat', uselist=False,
                             cascade='all, delete-orphan')


class IterumAIMessage(db.Model):
    __tablename__ = 'iterum_ai_message'

    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('iterum_ai_chat.id'),
                        nullable=False, index=True)
    # user | assistant | reasoning | tool_call | tool_output | canvas | system
    role = db.Column(db.String(20), nullable=False, index=True)
    content = db.Column(db.Text)
    tool_name = db.Column(db.String(100))
    tool_args_json = db.Column(db.Text)
    tool_result_json = db.Column(db.Text)
    tokens = db.Column(db.Integer, default=0)
    model = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)


class IterumAICanvas(db.Model):
    __tablename__ = 'iterum_ai_canvas'

    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('iterum_ai_chat.id'),
                        unique=True, nullable=False)
    title = db.Column(db.String(200), default='Workspace')
    content_md = db.Column(db.Text, default='')
    content_data_json = db.Column(db.Text)  # opcional: tabla/payload estructurado
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
    version = db.Column(db.Integer, default=1)
