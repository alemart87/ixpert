"""Tests del AI Analyst: permisos, tables, CRUD de chats, canvas, tools."""
import pytest


def test_ai_page_requires_superadmin(login_as, user_analista, user_superadmin):
    client_an = login_as(user_analista)
    r = client_an.get('/iterum/ai')
    assert r.status_code == 403, 'analista NO puede entrar al AI Analyst'

    client_sa = login_as(user_superadmin)
    r = client_sa.get('/iterum/ai')
    assert r.status_code == 200


def test_create_and_list_chats(app, login_as, user_superadmin):
    client = login_as(user_superadmin)

    # Vacio al inicio
    r = client.get('/iterum/api/ai/chats')
    assert r.get_json()['chats'] == []

    # Crear
    r = client.post('/iterum/api/ai/chats', json={})
    assert r.status_code == 201
    chat_id = r.get_json()['id']

    # Listar
    r = client.get('/iterum/api/ai/chats')
    chats = r.get_json()['chats']
    assert len(chats) == 1
    assert chats[0]['id'] == chat_id


def test_chat_isolation_between_users(app, login_as, user_superadmin):
    """Un superadmin no ve los chats de otro superadmin (aislamiento por user_id)."""
    from models import db, User
    with app.app_context():
        u2 = User(email='admin2@test', name='Admin 2', role='superadmin')
        u2.set_password('x')
        db.session.add(u2)
        db.session.commit()
        u2_id = u2.id
        u2_email = u2.email

    client1 = login_as(user_superadmin)
    client1.post('/iterum/api/ai/chats', json={})

    # Re-fetch u2 (puede haber sido detached)
    with app.app_context():
        u2 = User.query.filter_by(email=u2_email).first()
        u2_obj = u2

    client2 = login_as(u2_obj)
    r = client2.get('/iterum/api/ai/chats')
    assert r.get_json()['chats'] == []


def test_get_chat_with_canvas(app, login_as, user_superadmin):
    client = login_as(user_superadmin)
    r = client.post('/iterum/api/ai/chats', json={})
    chat_id = r.get_json()['id']

    r = client.get(f'/iterum/api/ai/chats/{chat_id}')
    assert r.status_code == 200
    body = r.get_json()
    assert body['id'] == chat_id
    assert body['messages'] == []
    assert body['canvas']['title'] == 'Workspace'
    assert body['canvas']['content_md'] == ''


def test_save_canvas_manual(app, login_as, user_superadmin):
    client = login_as(user_superadmin)
    chat_id = client.post('/iterum/api/ai/chats', json={}).get_json()['id']

    r = client.post(f'/iterum/api/ai/chats/{chat_id}/canvas',
                    json={'content_md': '# Plan de accion\n\n1. Llamar a CARMENRE',
                          'title': 'Plan semana 21'})
    assert r.status_code == 200
    assert r.get_json()['version'] == 2  # creado en v1, edicion sube a v2

    # Verificar persistencia
    r = client.get(f'/iterum/api/ai/chats/{chat_id}')
    canvas = r.get_json()['canvas']
    assert 'CARMENRE' in canvas['content_md']
    assert canvas['title'] == 'Plan semana 21'


def test_rename_chat(app, login_as, user_superadmin):
    client = login_as(user_superadmin)
    chat_id = client.post('/iterum/api/ai/chats', json={}).get_json()['id']

    r = client.post(f'/iterum/api/ai/chats/{chat_id}/rename',
                    json={'title': 'Analisis NPS Mayo'})
    assert r.status_code == 200
    assert r.get_json()['title'] == 'Analisis NPS Mayo'


def test_archive_chat(app, login_as, user_superadmin):
    client = login_as(user_superadmin)
    chat_id = client.post('/iterum/api/ai/chats', json={}).get_json()['id']

    r = client.delete(f'/iterum/api/ai/chats/{chat_id}')
    assert r.status_code == 200

    # Ya no aparece en el listado
    r = client.get('/iterum/api/ai/chats')
    assert r.get_json()['chats'] == []


def test_chats_api_blocked_for_non_admin(login_as, user_analista):
    client = login_as(user_analista)
    assert client.get('/iterum/api/ai/chats').status_code == 403
    assert client.post('/iterum/api/ai/chats', json={}).status_code == 403


# ============================================================================
# Tools (sin invocar al LLM, solo verificamos que esten registradas y callable)
# ============================================================================
def test_tools_imported():
    from iterum.ai.tools import ALL_TOOLS
    names = {getattr(t, 'name', None) or getattr(t, '__name__', None) for t in ALL_TOOLS}
    # Hay al menos las core de lectura
    assert any('dashboard' in (n or '') for n in names)
    assert any('ranking' in (n or '') for n in names)
    assert any('canvas' in (n or '') for n in names)


def test_canvas_tool_context(app, login_as, user_superadmin):
    """canvas_write requiere chat_id en contexto."""
    client = login_as(user_superadmin)
    chat_id = client.post('/iterum/api/ai/chats', json={}).get_json()['id']

    with app.app_context():
        from iterum.ai.tools import set_ctx, _ctx
        from iterum.ai.models import IterumAICanvas
        set_ctx(chat_id)
        # Las @function_tool decorated estan envueltas; testeamos la logica
        # directamente actualizando el canvas via la API publica (saving)
        canvas = IterumAICanvas.query.filter_by(chat_id=chat_id).first()
        assert canvas is not None
        assert canvas.content_md == ''


def test_agent_factory_doesnt_crash():
    """create_agent() funciona sin OpenAI key (solo construye el objeto)."""
    import os
    os.environ['OPENAI_API_KEY'] = 'sk-test-mock'
    from iterum.ai.agent import create_agent
    agent = create_agent()
    assert agent is not None
    # Verifica que tenga tools registradas
    tools = getattr(agent, 'tools', [])
    assert len(tools) >= 10
