"""Agente principal de Iterum (gpt-5.4 con reasoning medium).

Wrapper alrededor del SDK openai-agents para integrar con Flask:
- create_agent(): construye el Agent con tools, instructions, reasoning settings
- stream_run(): generador asincronico que cede eventos para SSE
"""
from __future__ import annotations

import os
from agents import Agent, Runner, ModelSettings

try:
    from openai.types.shared.reasoning import Reasoning
except Exception:  # pragma: no cover
    Reasoning = None

from iterum.ai.tools import ALL_TOOLS, set_ctx
from iterum.services import analytics as iterum_analytics


MODEL_NAME = os.environ.get('ITERUM_AI_MODEL', 'gpt-5.4')
REASONING_EFFORT = os.environ.get('ITERUM_AI_REASONING_EFFORT', 'medium')


SYSTEM_PROMPT = """Sos el AI Analyst de Iterum, plataforma de CX Management del banco Itau.
Asistis al SuperAdmin a entender los datos NPS, encontrar causas raiz, y
proponer planes de accion concretos para mejorar el indice.

CONTEXTO DEL NEGOCIO:
- Objetivo del canal: 77% NPS. Por debajo de 60% = accion prioritaria.
- Roles del banco: superadmin, analista, supervisor, asesor.
- Categorias: promotor (>=9), pasivo (7-8), detractor (<=6).
- Metricas que rastreas: NPS, % resolucion, esfuerzo percibido, motivo del
  cliente, causa raiz (5 porques), responsabilidad (asesor/proceso/externo).
- Canales tipicos: WHATSAPP, LLAMADA.
- Celulas operativas: agrupaciones de asesores. PB = Personal Bank.

COMO TRABAJAS:
1. **Razonar primero**: usa la tool get_dashboard_kpis al inicio si te falta
   contexto. No inventes numeros. Si no sabes algo, llama a la tool.
2. **Citar IDs**: cuando menciones un caso, da el survey_id para que el
   admin pueda buscarlo.
3. **Canvas para entregables**: cuando produzcas un plan de accion, lista
   de coaching, draft de comunicado, etc., usa canvas_write o canvas_append
   para que el admin lo vea en el workspace lateral y pueda editarlo.
4. **Mutaciones con prudencia**: las tools que modifican datos
   (set_audit_review, create_coaching_session, add_root_cause_analysis)
   solo se usan si el admin las pide explicitamente. NUNCA las uses sin
   permiso claro. Antes de mutar, confirma con el admin que esta de acuerdo.
5. **Respuestas en espanol, accionables, sin floritura**. Datos primero,
   interpretacion despues. Si proponer pasos, numera (1, 2, 3...).
6. **Honestidad sobre limites**: si los datos no alcanzan para responder,
   decilo. No fabriques conclusiones.

ESTRUCTURA TIPICA DE RESPUESTA:
- 1-2 oraciones de respuesta directa.
- Bullet list con los datos clave (con ID si aplica).
- Opcional: actualizar el canvas con un plan estructurado.
- Cierre con la proxima accion sugerida.
"""


def create_agent() -> Agent:
    """Construye una instancia nueva del Agent. El SDK es stateless por agente,
    asi que es seguro crear una por request (o cachear si fuera caro)."""
    kwargs = {
        'name': 'Iterum Analyst',
        'instructions': SYSTEM_PROMPT,
        'model': MODEL_NAME,
        'tools': ALL_TOOLS,
    }
    if Reasoning is not None:
        kwargs['model_settings'] = ModelSettings(
            reasoning=Reasoning(effort=REASONING_EFFORT, summary='detailed'),
        )
    return Agent(**kwargs)


async def run_streamed(input_text: str, chat_id: int, user_id: int,
                       previous_messages: list | None = None):
    """Corre el agente en modo streaming. Devuelve un RunResultStreaming del SDK.

    El caller hace `async for event in result.stream_events():` para iterar.
    Set chat_id y user_id en el contexto thread-local para que las tools del
    canvas y de mutacion sepan donde escribir/quien actua.
    """
    set_ctx(chat_id)  # tools del canvas
    # Tambien guardamos user_id para mutaciones
    from iterum.ai.tools import _ctx
    _ctx['user_id'] = user_id

    agent = create_agent()

    # Construir el input: si hay historial, se pasa como lista de items
    if previous_messages:
        full_input = previous_messages + [{'role': 'user', 'content': input_text}]
    else:
        full_input = input_text

    return Runner.run_streamed(agent, input=full_input)
