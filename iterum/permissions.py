"""Decoradores de permisos para Iterum.

Roles iXpert mapeados a capacidades Iterum:
- superadmin : todo
- analista   : todo
- supervisor : lectura + auditar su celula (read-mostly)
- asesor     : sin acceso
"""
from functools import wraps
from flask import abort, request
from flask_login import current_user


def iterum_required(f):
    """Acceso minimo a Iterum (cualquier rol salvo asesor)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if current_user.role == 'asesor':
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def iterum_editor_required(f):
    """Permisos de escritura: superadmin + analista."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.can_admin_training:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def iterum_admin_required(f):
    """Solo superadmin (snapshots ejecutivos, reset, logs)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.is_superadmin:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def log_access(action, entity_type=None, entity_id=None, payload=None):
    """Helper para registrar acceso en NPSAccessLog. Best-effort, nunca rompe.
    Importa adentro para evitar ciclos."""
    try:
        import json
        from models import db
        from iterum.models import NPSAccessLog
        entry = NPSAccessLog(
            user_id=current_user.id if current_user.is_authenticated else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=json.dumps(payload, ensure_ascii=False) if payload else None,
            ip_address=request.remote_addr if request else None,
            user_agent=(request.headers.get('User-Agent', '')[:500]) if request else None,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        try:
            from models import db as _db
            _db.session.rollback()
        except Exception:
            pass
