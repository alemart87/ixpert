"""Fixtures pytest comunes a los tests de Iterum.

Importante: la app NO mantiene un app_context activo durante el test, porque
Flask-Login cachea current_user en `g` y eso confunde a tests que hacen multiples
logins en distintos clients dentro del mismo test (g._login_user persistiria).
Cada fixture/setup abre su propio app_context corto.
"""
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('SECRET_KEY', 'test-secret')


@pytest.fixture
def app():
    from app import app as flask_app
    from models import db
    flask_app.config['TESTING'] = True
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with flask_app.app_context():
        db.drop_all()
        import iterum.models  # noqa: F401
        db.create_all()
    yield flask_app
    with flask_app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def db_session(app):
    """Sesion de DB dentro de un app_context. Solo para tests que NO usan
    test_client (services/models puros)."""
    from models import db
    with app.app_context():
        yield db.session
        db.session.remove()


def _make_user(app, email, name, role):
    from models import db, User
    with app.app_context():
        u = User(email=email, name=name, role=role)
        u.set_password('x')
        db.session.add(u)
        db.session.commit()
        # Forzar carga de atributos antes de detach
        _ = (u.id, u.email, u.role, u.name)
        db.session.expunge(u)
        return u


@pytest.fixture
def user_superadmin(app):
    return _make_user(app, 'admin@test', 'Admin', 'superadmin')


@pytest.fixture
def user_analista(app):
    return _make_user(app, 'analista@test', 'Analista', 'analista')


@pytest.fixture
def user_supervisor(app):
    return _make_user(app, 'sup@test', 'Sup', 'supervisor')


@pytest.fixture
def user_asesor(app):
    return _make_user(app, 'ase@test', 'Asesor', 'asesor')


@pytest.fixture
def login_as(app):
    def _login(user):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
        return client
    return _login


@pytest.fixture
def sample_xlsx():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['Fecha', 'Canal', 'Celula', 'Asesor', 'Documento', 'NPS', 'Comentario'])
    ws.append(['2026-05-01 10:00', 'WhatsApp', 'Cell1', 'Juan Perez', '111', 10, 'Excelente'])
    ws.append(['2026-05-01 11:00', 'WhatsApp', 'Cell1', 'Juan Perez', '111', 8, 'Bueno'])
    ws.append(['2026-05-02 09:00', 'Llamada',  'Cell2', 'Ana Lopez',  '222', 5, 'Pasable'])
    ws.append(['2026-05-02 10:00', 'Llamada',  'Cell2', 'Ana Lopez',  '222', 2, 'Mal servicio'])
    ws.append(['2026-05-03 12:00', 'WhatsApp', 'Cell1', 'Juan Perez', '111', 9, 'Bien'])
    fd, path = tempfile.mkstemp(suffix='.xlsx')
    os.close(fd)
    wb.save(path)
    yield path
    if os.path.exists(path):
        os.remove(path)
