import os
import re
import json
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models import db, Content, ChatConversation, ChatMessage
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError

chat_bp = Blueprint('chat', __name__)

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

SYSTEM_PROMPT = """Eres iXpert AI, el asistente virtual inteligente de la plataforma iXpert de Itaú.
Tu rol es ayudar a los asesores y supervisores del banco con información precisa.

REGLAS:
- Respondes SIEMPRE en español
- Saluda al usuario por su nombre cuando sea la primera interacción
- Usa la información del CONTEXTO proporcionado para responder
- Si encuentras información relevante, incluye el link: [Título del artículo](/content/slug)
- Si NO hay información suficiente en el contexto, dilo honestamente y sugiere qué buscar
- Sé conciso pero completo. Usa listas cuando sea apropiado
- No inventes procedimientos ni pasos que no estén en el contexto
- Puedes hacer preguntas de seguimiento para entender mejor qué necesita el usuario"""


def strip_html(html):
    """Remove HTML tags and get clean plain text."""
    # Remove script and style blocks completely
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Replace block elements with newlines
    text = re.sub(r'<(?:br|p|div|h[1-6]|li|tr)[^>]*>', '\n', text, flags=re.IGNORECASE)
    # Remove remaining tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Clean whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()[:2500]


STOP_WORDS = {'de', 'la', 'el', 'en', 'un', 'una', 'los', 'las', 'es', 'que', 'por',
               'se', 'del', 'al', 'con', 'para', 'su', 'como', 'mas', 'ya', 'le', 'lo',
               'me', 'si', 'no', 'mi', 'te', 'tu', 'hay', 'ser', 'son', 'era', 'fue'}


def get_stem_variants(word):
    """Generate simple Spanish stem variants for fuzzy matching."""
    variants = {word}
    # Plural/singular
    if word.endswith('es'):
        variants.add(word[:-2])
        variants.add(word[:-1])
    elif word.endswith('s'):
        variants.add(word[:-1])
    else:
        variants.add(word + 's')
        variants.add(word + 'es')
    # Common suffixes
    if word.endswith('ción'):
        variants.add(word.replace('ción', 'ciones'))
    if word.endswith('ciones'):
        variants.add(word.replace('ciones', 'ción'))
    # ando/endo -> ar/er
    if word.endswith('ando'):
        variants.add(word[:-4] + 'ar')
    if word.endswith('endo'):
        variants.add(word[:-4] + 'er')
    return variants


def find_relevant_contents(query, limit=4):
    """Find relevant content using full-text search with fuzzy matching."""
    query_lower = query.lower()
    words = [w for w in re.findall(r'\w+', query_lower) if len(w) >= 2 and w not in STOP_WORDS]

    if not words:
        return []

    # Pre-compute stem variants for all query words
    word_variants = {}
    for w in words:
        word_variants[w] = get_stem_variants(w)

    contents = Content.query.filter_by(is_active=True).all()
    scored = []

    for c in contents:
        score = 0
        keywords = (c.keywords or '').lower()
        title = c.title.lower()
        desc = (c.description or '').lower()
        body_text = strip_html(c.html_content).lower()
        # Combine all searchable text
        all_text = f"{keywords} {title} {desc} {body_text}"

        for word in words:
            # Check all variants of the word
            for variant in word_variants[word]:
                if variant in keywords:
                    score += 5
                    break
            for variant in word_variants[word]:
                if variant in title:
                    score += 4
                    break
            for variant in word_variants[word]:
                if variant in desc:
                    score += 2
                    break
            for variant in word_variants[word]:
                if variant in body_text:
                    score += 1
                    break

        # Bonus: multi-word phrase match
        if len(words) > 1:
            phrase = ' '.join(words)
            if phrase in all_text:
                score += 10
            # Partial phrase (adjacent words)
            for i in range(len(words) - 1):
                pair = words[i] + ' ' + words[i+1]
                if pair in all_text:
                    score += 4

        if score > 0:
            scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:limit]]


def call_openai(messages):
    """Call OpenAI API."""
    if not OPENAI_API_KEY:
        return "Lo siento, el servicio de IA no está configurado. Contacta al administrador.", 0

    payload = json.dumps({
        'model': 'gpt-4o-mini',
        'messages': messages,
        'max_tokens': 1000,
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
        context_parts.append(f"ARTÍCULO: {c.title}\nURL: /content/{c.slug}\nCATEGORÍA: {c.category.name if c.category else 'General'}\nCONTENIDO:\n{plain}")
        ref_links.append({'title': c.title, 'slug': c.slug})

    context_text = "\n\n===\n\n".join(context_parts) if context_parts else "No se encontró información directamente relevante. Sugiere al usuario buscar en la plataforma o reformular su pregunta."

    # Build messages for OpenAI
    user_info = f"El usuario se llama {current_user.name} y tiene el rol de {current_user.role}."
    ai_messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'system', 'content': f"INFORMACIÓN DEL USUARIO: {user_info}"},
        {'role': 'system', 'content': f"CONTEXTO DE LA BASE DE CONOCIMIENTO:\n\n{context_text}"}
    ]

    # Add recent conversation history (last 8 messages)
    recent = ChatMessage.query.filter_by(
        conversation_id=conv.id
    ).order_by(ChatMessage.created_at.desc()).limit(8).all()
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


@chat_bp.route('/api/chat/my-stats')
@login_required
def chat_my_stats():
    """User's own chat stats with training suggestions."""
    from sqlalchemy import func

    total_convs = ChatConversation.query.filter_by(user_id=current_user.id).count()
    total_msgs = ChatMessage.query.join(ChatConversation).filter(
        ChatConversation.user_id == current_user.id,
        ChatMessage.role == 'user'
    ).count()

    # Get top topics from conversation titles
    convs = ChatConversation.query.filter_by(
        user_id=current_user.id
    ).order_by(ChatConversation.updated_at.desc()).limit(20).all()
    topics = [c.title for c in convs if c.title][:5]

    # Generate training suggestions based on what they DON'T ask about
    from models import Category
    all_categories = Category.query.filter_by(is_active=True).all()
    cat_names = [c.name for c in all_categories]

    # Find categories the user hasn't explored
    user_topics_text = ' '.join(topics).lower()
    suggestions = []
    for cat in cat_names:
        if cat.lower() not in user_topics_text:
            suggestions.append(f'Explora la sección "{cat}" para ampliar tu conocimiento.')
    suggestions = suggestions[:4]

    if total_convs > 5:
        suggestions.insert(0, 'Llevas ' + str(total_convs) + ' consultas. Revisa tus temas más frecuentes para identificar áreas de mejora.')

    return jsonify({
        'total_conversations': total_convs,
        'total_messages': total_msgs,
        'top_topics': topics,
        'suggestions': suggestions
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
