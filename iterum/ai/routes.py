"""Endpoints del AI Analyst.

- GET  /iterum/ai                       -> pagina del chat
- GET  /iterum/api/ai/chats             -> listar conversaciones
- POST /iterum/api/ai/chats             -> crear nueva conversacion
- GET  /iterum/api/ai/chats/<id>        -> historial de mensajes + canvas
- DEL  /iterum/api/ai/chats/<id>        -> archivar conversacion
- POST /iterum/api/ai/chats/<id>/message  -> enviar mensaje (SSE stream)
- POST /iterum/api/ai/chats/<id>/canvas -> guardar edicion manual del canvas
- POST /iterum/api/ai/chats/<id>/rename -> renombrar chat
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from threading import Thread
from queue import Queue, Empty

from flask import (render_template, request, jsonify, Response, stream_with_context,
                   abort, current_app)
from flask_login import login_required, current_user

from models import db, User
from iterum.routes import iterum_bp
from iterum.permissions import iterum_admin_required, log_access
from iterum.ai.models import IterumAIChat, IterumAIMessage, IterumAICanvas
from iterum.ai.agent import run_streamed, MODEL_NAME, MAX_TURNS


# ============================================================================
# Pagina
# ============================================================================
@iterum_bp.route('/ai')
@login_required
@iterum_admin_required
def ai_page():
    log_access('view', 'ai', None, {'page': 'analyst'})
    return render_template('iterum/ai.html')


# ============================================================================
# Conversaciones CRUD
# ============================================================================
@iterum_bp.route('/api/ai/chats', methods=['GET'])
@login_required
@iterum_admin_required
def ai_list_chats():
    rows = IterumAIChat.query.filter_by(
        user_id=current_user.id, archived=False,
    ).order_by(IterumAIChat.last_message_at.desc()).limit(100).all()
    return jsonify({
        'chats': [{
            'id': c.id, 'title': c.title,
            'created_at': c.created_at.isoformat() if c.created_at else None,
            'last_message_at': c.last_message_at.isoformat() if c.last_message_at else None,
            'total_tokens': c.total_tokens,
        } for c in rows]
    })


@iterum_bp.route('/api/ai/chats', methods=['POST'])
@login_required
@iterum_admin_required
def ai_create_chat():
    c = IterumAIChat(user_id=current_user.id, title='Nueva conversacion',
                     model=MODEL_NAME)
    db.session.add(c)
    db.session.commit()
    canvas = IterumAICanvas(chat_id=c.id, content_md='', version=1)
    db.session.add(canvas)
    db.session.commit()
    log_access('create', 'ai_chat', c.id)
    return jsonify({'id': c.id, 'title': c.title}), 201


@iterum_bp.route('/api/ai/chats/<int:chat_id>', methods=['GET'])
@login_required
@iterum_admin_required
def ai_get_chat(chat_id):
    c = db.session.get(IterumAIChat, chat_id)
    if not c or c.user_id != current_user.id:
        abort(404)
    return jsonify({
        'id': c.id, 'title': c.title, 'created_at': c.created_at.isoformat(),
        'total_tokens': c.total_tokens,
        'total_cost_usd': c.total_cost_usd,
        'messages': [{
            'id': m.id, 'role': m.role, 'content': m.content,
            'tool_name': m.tool_name,
            'tool_args': json.loads(m.tool_args_json) if m.tool_args_json else None,
            'tool_result': json.loads(m.tool_result_json) if m.tool_result_json else None,
            'created_at': m.created_at.isoformat() if m.created_at else None,
        } for m in c.messages],
        'canvas': {
            'title': c.canvas.title if c.canvas else 'Workspace',
            'content_md': c.canvas.content_md if c.canvas else '',
            'version': c.canvas.version if c.canvas else 0,
        },
    })


@iterum_bp.route('/api/ai/chats/<int:chat_id>', methods=['DELETE'])
@login_required
@iterum_admin_required
def ai_archive_chat(chat_id):
    c = db.session.get(IterumAIChat, chat_id)
    if not c or c.user_id != current_user.id:
        abort(404)
    c.archived = True
    db.session.commit()
    log_access('delete', 'ai_chat', chat_id)
    return jsonify({'archived': True})


@iterum_bp.route('/api/ai/chats/<int:chat_id>/rename', methods=['POST'])
@login_required
@iterum_admin_required
def ai_rename_chat(chat_id):
    c = db.session.get(IterumAIChat, chat_id)
    if not c or c.user_id != current_user.id:
        abort(404)
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()[:200]
    if not title:
        return jsonify({'error': 'titulo requerido'}), 400
    c.title = title
    db.session.commit()
    return jsonify({'id': c.id, 'title': c.title})


@iterum_bp.route('/api/ai/chats/<int:chat_id>/canvas', methods=['POST'])
@login_required
@iterum_admin_required
def ai_save_canvas(chat_id):
    """Permite al admin editar el canvas manualmente desde la UI."""
    c = db.session.get(IterumAIChat, chat_id)
    if not c or c.user_id != current_user.id:
        abort(404)
    data = request.get_json(silent=True) or {}
    canvas = c.canvas
    if not canvas:
        canvas = IterumAICanvas(chat_id=chat_id)
        db.session.add(canvas)
    if 'content_md' in data:
        canvas.content_md = data['content_md']
    if 'title' in data and data['title']:
        canvas.title = str(data['title'])[:200]
    canvas.version = (canvas.version or 0) + 1
    db.session.commit()
    return jsonify({'version': canvas.version})


# ============================================================================
# Streaming SSE de un nuevo mensaje
# ============================================================================
@iterum_bp.route('/api/ai/chats/<int:chat_id>/message', methods=['POST'])
@login_required
@iterum_admin_required
def ai_send_message(chat_id):
    """Envia un mensaje del usuario y stremea la respuesta como SSE.

    Eventos SSE emitidos:
    - event: user_msg       -> mensaje del usuario persistido (con id)
    - event: reasoning      -> chunk del razonamiento del modelo
    - event: tool_call      -> {name, args}
    - event: tool_output    -> {name, result}
    - event: canvas_update  -> {version, content_md}
    - event: assistant_delta-> chunk de texto de la respuesta final
    - event: done           -> {message_id, tokens}
    - event: error          -> {error}
    """
    c = db.session.get(IterumAIChat, chat_id)
    if not c or c.user_id != current_user.id:
        abort(404)
    data = request.get_json(silent=True) or {}
    user_text = (data.get('content') or '').strip()
    if not user_text:
        return jsonify({'error': 'mensaje vacio'}), 400

    # Persistir mensaje del usuario antes de empezar a stremear
    user_msg = IterumAIMessage(
        chat_id=chat_id, role='user', content=user_text, model=MODEL_NAME,
    )
    db.session.add(user_msg)
    c.last_message_at = datetime.now(timezone.utc)
    db.session.commit()
    log_access('create', 'ai_message', user_msg.id, {'chat_id': chat_id})
    user_msg_id = user_msg.id

    # Historial previo (excluyendo el que acabamos de crear y items internos)
    previous_messages = []
    for m in c.messages[:-1]:
        if m.role == 'user':
            previous_messages.append({'role': 'user', 'content': m.content or ''})
        elif m.role == 'assistant' and m.content:
            previous_messages.append({'role': 'assistant', 'content': m.content})
        # Los tool_call/output se reconstruyen del historial del SDK,
        # no los mandamos como input (el modelo los reconsultara si lo necesita).

    app_obj = current_app._get_current_object()
    user_id = current_user.id

    # Worker thread que corre el async loop y va metiendo eventos en una queue.
    # SSE lee de la queue y serializa al cliente.
    q: Queue = Queue()

    def _worker():
        async def _run():
            try:
                # Necesitamos app_context para que las tools de DB funcionen
                with app_obj.app_context():
                    result = await run_streamed(
                        user_text, chat_id=chat_id, user_id=user_id,
                        previous_messages=previous_messages,
                    )
                    assistant_text = []
                    reasoning_buf = []
                    last_canvas_version = c.canvas.version if c.canvas else 0
                    total_tokens = 0
                    tool_calls_by_id: dict[str, str] = {}  # call_id -> tool_name

                    async for event in result.stream_events():
                        ev_type = getattr(event, 'type', None)

                        # Razonamiento (gpt-5.4 streaming)
                        if ev_type == 'raw_response_event':
                            inner = getattr(event, 'data', None)
                            inner_type = getattr(inner, 'type', '') if inner else ''
                            if inner_type == 'response.reasoning_summary_text.delta':
                                delta = getattr(inner, 'delta', '') or ''
                                if delta:
                                    reasoning_buf.append(delta)
                                    q.put({'event': 'reasoning', 'data': {'delta': delta}})
                            elif inner_type == 'response.output_text.delta':
                                delta = getattr(inner, 'delta', '') or ''
                                if delta:
                                    assistant_text.append(delta)
                                    q.put({'event': 'assistant_delta', 'data': {'delta': delta}})
                            continue

                        # run item events: tool calls, outputs, mensajes finales
                        if ev_type == 'run_item_stream_event':
                            item = getattr(event, 'item', None)
                            item_type = getattr(item, 'type', '') if item else ''
                            if item_type == 'tool_call_item':
                                raw = getattr(item, 'raw_item', None)
                                tname = getattr(raw, 'name', 'tool')
                                targs = getattr(raw, 'arguments', None)
                                call_id = getattr(raw, 'call_id', None) or getattr(raw, 'id', None)
                                if call_id and tname:
                                    tool_calls_by_id[call_id] = tname
                                try:
                                    targs_parsed = json.loads(targs) if isinstance(targs, str) else targs
                                except Exception:
                                    targs_parsed = {'raw': str(targs)[:500]}
                                q.put({'event': 'tool_call', 'data': {
                                    'name': tname, 'args': targs_parsed,
                                }})
                                # Persistir el tool call
                                with app_obj.app_context():
                                    db.session.add(IterumAIMessage(
                                        chat_id=chat_id, role='tool_call',
                                        tool_name=tname,
                                        tool_args_json=json.dumps(targs_parsed, default=str, ensure_ascii=False),
                                        model=MODEL_NAME,
                                    ))
                                    db.session.commit()
                            elif item_type == 'tool_call_output_item':
                                out = getattr(item, 'output', None)
                                # Resolver tool name desde el raw_item (que es tool_call_output
                                # con call_id) buscando en el historial de calls del run.
                                raw = getattr(item, 'raw_item', None)
                                tname = getattr(raw, 'name', None) or ''
                                if not tname and raw is not None:
                                    call_id = getattr(raw, 'call_id', None) or (
                                        raw.get('call_id') if isinstance(raw, dict) else None)
                                    if call_id and call_id in tool_calls_by_id:
                                        tname = tool_calls_by_id[call_id]
                                q.put({'event': 'tool_output', 'data': {
                                    'name': tname,
                                    'result': out if isinstance(out, (dict, list)) else str(out)[:2000],
                                }})
                                with app_obj.app_context():
                                    db.session.add(IterumAIMessage(
                                        chat_id=chat_id, role='tool_output',
                                        tool_name=tname,
                                        tool_result_json=json.dumps(out, default=str, ensure_ascii=False)[:50000],
                                        model=MODEL_NAME,
                                    ))
                                    db.session.commit()
                                # Chequear canvas DESPUES de cualquier tool — el modelo
                                # puede modificar el workspace sin que coincida el tname
                                with app_obj.app_context():
                                    canvas = IterumAICanvas.query.filter_by(chat_id=chat_id).first()
                                    if canvas and (canvas.version or 0) != last_canvas_version:
                                        last_canvas_version = canvas.version
                                        q.put({'event': 'canvas_update', 'data': {
                                            'version': canvas.version,
                                            'content_md': canvas.content_md or '',
                                            'title': canvas.title,
                                        }})

                    # Cerrar: guardar el mensaje final del assistant
                    final_text = ''.join(assistant_text).strip()
                    reasoning_full = ''.join(reasoning_buf).strip()
                    with app_obj.app_context():
                        if reasoning_full:
                            db.session.add(IterumAIMessage(
                                chat_id=chat_id, role='reasoning',
                                content=reasoning_full, model=MODEL_NAME,
                            ))
                        msg = IterumAIMessage(
                            chat_id=chat_id, role='assistant',
                            content=final_text or '(sin respuesta)',
                            model=MODEL_NAME,
                        )
                        db.session.add(msg)
                        # Actualizar contador del chat
                        chat_obj = db.session.get(IterumAIChat, chat_id)
                        if chat_obj:
                            chat_obj.last_message_at = datetime.now(timezone.utc)
                            # Title auto: primeros 60 chars del primer user msg si sigue "Nueva conversacion"
                            if chat_obj.title == 'Nueva conversacion':
                                chat_obj.title = (user_text[:60] + ('...' if len(user_text) > 60 else ''))
                        db.session.commit()
                        q.put({'event': 'done', 'data': {
                            'message_id': msg.id,
                            'title': chat_obj.title if chat_obj else None,
                        }})
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                exc_name = type(e).__name__
                friendly = str(e)
                # Si pegamos contra el limite de turnos, mensaje claro
                if 'MaxTurns' in exc_name or 'max_turns' in friendly.lower():
                    friendly = (
                        f'El agente uso las {MAX_TURNS} iteraciones disponibles. '
                        'Decime que querias y lo retomamos en una conversacion nueva mas '
                        'enfocada, o subimos ITERUM_AI_MAX_TURNS en config.'
                    )
                current_app.logger.exception('[iterum.ai] stream error: %s', exc_name)
                q.put({'event': 'error', 'data': {
                    'error': friendly, 'type': exc_name,
                    'trace': tb[:2000],
                }})
            finally:
                q.put(None)  # sentinel

        try:
            asyncio.run(_run())
        except Exception as e:
            q.put({'event': 'error', 'data': {'error': str(e)}})
            q.put(None)

    Thread(target=_worker, daemon=True).start()

    @stream_with_context
    def _sse():
        # 2KB de padding fuerza al browser y al proxy a abrir el stream
        yield ':' + ' ' * 2048 + '\n\n'
        # Emit user_msg primero (ya persistido)
        yield _sse_event('user_msg', {'id': user_msg_id, 'content': user_text})
        # Bucle con keep-alive cada 5s para evitar buffering en proxies
        while True:
            try:
                item = q.get(timeout=5)
            except Empty:
                # keep-alive comment (no event) — fuerza el flush
                yield ': keepalive\n\n'
                continue
            if item is None:
                return
            yield _sse_event(item['event'], item['data'])

    return Response(_sse(), mimetype='text/event-stream',
                    headers={
                        'Cache-Control': 'no-cache, no-transform',
                        'X-Accel-Buffering': 'no',
                        'Connection': 'keep-alive',
                        'Content-Encoding': 'identity',  # evita gzip que bufferea
                    })


def _sse_event(event: str, data: dict) -> str:
    return f'event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n'
