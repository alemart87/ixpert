"""Iterum AI Analyst — agente reasoning con canvas y herramientas de gestion.

Modelo: gpt-5.4 con reasoning effort=medium (configurable via env).
SDK: openai-agents oficial (function tools + streaming + sessions).

Estructura:
- models.py    : tablas iterum_ai_chat / iterum_ai_message / iterum_ai_canvas
- tools.py     : ~15 @function_tool que el agente puede llamar
- agent.py     : system prompt + Agent + Runner wrapper streamed
- routes.py    : endpoints REST + SSE (/iterum/ai, /iterum/api/ai/*)

Para activar: importar este modulo desde iterum/__init__.py o iterum/routes.py.
"""
# Importar models para que SQLAlchemy los registre en db.metadata
from . import models  # noqa: F401
# Importar routes para que se registren los endpoints en el blueprint
from . import routes  # noqa: F401
