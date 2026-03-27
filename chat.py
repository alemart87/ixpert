import os
import re
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models import db, Content, ChatConversation, ChatMessage
from datetime import datetime, timezone

chat_bp = Blueprint('chat', __name__)

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

SYSTEM_PROMPT = """Eres iXpert AI, asistente virtual de la plataforma de ayuda en línea de Itaú.
Respondes en español de forma clara y concisa.
Usa SOLO la información proporcionada como contexto para responder.
Si no tienes información suficiente en el contexto, dilo honestamente y sugiere buscar en la plataforma.
Siempre incluye el link al artículo relevante cuando sea posible usando formato markdown: [Título](/content/slug)
Sé amigable y profesional. No inventes información que no esté en el contexto."""


def find_relevant_contents(query, limit=3):
    """Find the most relevant content articles for a query."""
    query_lower = query.lower()
    words = re.findall(r'\w+', query_lower)

    contents = Content.query.filter_by(is_active=True).all()
    scored = []

    for c in contents:
        score = 0
        keywords = (c.keywords or '').lower()
        title = c.title.lower()
        desc = (c.description or '').lower()

        for word in words:
            if len(word) < 3:
                continue
            if word in keywords:
                score += 3
            if word in title:
                score += 2
            if word in desc:
                score += 1

        if score > 0:
            scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:limit]]


def strip_html(html):
    """Remove HTML tags and get plain text, truncated."""
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:1500]  # Max 1500 chars per article to save tokens


def call_openai(messages):
    """Call OpenAI API."""
    if not OPENAI_API_KEY:
        return "Lo siento, el servicio de IA no está configurado. Contacta al administrador.", 0

    import json
    from urllib.request import Request, urlopen
    from urllib.error import URLError

    payload = json.dumps({
        'model': 'gpt-4o-mini',
        'messages': messages,
        'max_tokens': 800,
        'temperature': 0.3
    }).encode('utf-8')

    req = Request(
        'https://api.openai.com/v1/chat/completions',
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {OPENAI_API_KEY}'
        }
    )

    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            content = data['choices'][0]['message']['content']
            tokens = data.get('usage', {}).get('total_tokens', 0)
            return content, tokens
    except URLError as e:
        print(f"[CHAT] OpenAI error: {e}", flush=True)
        return "Lo siento, hubo un error al procesar tu consulta. Intenta de nuevo.", 0
    except Exception as e:
        print(f"[CHAT] Unexpected error: {e}", flush=True)
        return "Error inesperado. Por favor intenta de nuevo.", 0


@chat_bp.route('/api/chat/send', methods=['POST'])
@login_required
def chat_send():
    data = request.get_json(silent=True) or {}
    message = data.get('message', '').strip()
    conversation_id = data.get('conversation_id')

    if not message:
        return jsonify({'error': 'Mensaje vacío'}), 400

    # Get or create conversation
    if conversation_id:
        conv = ChatConversation.query.filter_by(
            id=conversation_id, user_id=current_user.id
        ).first()
        if not conv:
            return jsonify({'error': 'Conversación no encontrada'}), 404
    else:
        conv = ChatConversation(
            user_id=current_user.id,
            title=message[:100]
        )
        db.session.add(conv)
        db.session.flush()

    # Save user message
    user_msg = ChatMessage(
        conversation_id=conv.id,
        role='user',
        content=message
    )
    db.session.add(user_msg)

    # Find relevant content
    relevant = find_relevant_contents(message)
    context_parts = []
    ref_links = []
    for c in relevant:
        plain = strip_html(c.html_content)
        context_parts.append(f"Artículo: {c.title}\nURL: /content/{c.slug}\nContenido: {plain}")
        ref_links.append({'title': c.title, 'slug': c.slug})

    context_text = "\n\n---\n\n".join(context_parts) if context_parts else "No se encontró información relevante en la base de conocimiento."

    # Build messages for OpenAI
    ai_messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]
    ai_messages.append({'role': 'system', 'content': f"CONTEXTO DE LA BASE DE CONOCIMIENTO:\n\n{context_text}"})

    # Add recent conversation history (last 6 messages)
    recent = ChatMessage.query.filter_by(
        conversation_id=conv.id
    ).order_by(ChatMessage.created_at.desc()).limit(6).all()
    recent.reverse()
    for msg in recent[:-1]:  # Exclude the message we just added
        ai_messages.append({'role': msg.role, 'content': msg.content})

    ai_messages.append({'role': 'user', 'content': message})

    # Call OpenAI
    response_text, tokens = call_openai(ai_messages)

    # Save assistant message
    assistant_msg = ChatMessage(
        conversation_id=conv.id,
        role='assistant',
        content=response_text,
        tokens_used=tokens
    )
    db.session.add(assistant_msg)
    conv.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        'conversation_id': conv.id,
        'message': response_text,
        'references': ref_links,
        'tokens_used': tokens
    })


@chat_bp.route('/api/chat/conversations')
@login_required
def chat_conversations():
    convs = ChatConversation.query.filter_by(
        user_id=current_user.id
    ).order_by(ChatConversation.updated_at.desc()).limit(20).all()

    return jsonify([{
        'id': c.id,
        'title': c.title,
        'updated_at': c.updated_at.isoformat() if c.updated_at else '',
        'message_count': len(c.messages)
    } for c in convs])


@chat_bp.route('/api/chat/conversations/<int:conv_id>')
@login_required
def chat_conversation_messages(conv_id):
    conv = ChatConversation.query.filter_by(
        id=conv_id, user_id=current_user.id
    ).first_or_404()

    return jsonify({
        'id': conv.id,
        'title': conv.title,
        'messages': [{
            'role': m.role,
            'content': m.content,
            'created_at': m.created_at.isoformat() if m.created_at else ''
        } for m in conv.messages]
    })


@chat_bp.route('/api/chat/conversations/<int:conv_id>', methods=['DELETE'])
@login_required
def chat_conversation_delete(conv_id):
    conv = ChatConversation.query.filter_by(
        id=conv_id, user_id=current_user.id
    ).first_or_404()

    ChatMessage.query.filter_by(conversation_id=conv.id).delete()
    db.session.delete(conv)
    db.session.commit()
    return jsonify({'ok': True})
