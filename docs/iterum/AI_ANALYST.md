# Iterum · AI Analyst

Agente de IA con razonamiento (gpt-5.4 + reasoning medium) exclusivo para SuperAdmin.
Conversa sobre los datos del NPS, llama tools para consultar la base, y trabaja
con un **canvas** colaborativo para producir planes de acción.

## Stack

- **SDK:** [`openai-agents`](https://github.com/openai/openai-agents-python) (oficial)
- **Modelo:** `gpt-5.4` con `ModelSettings(reasoning=Reasoning(effort='medium', summary='detailed'))`
- **API key:** reusa `OPENAI_API_KEY` (la del chat normal)
- **Streaming:** SSE (Server-Sent Events) hacia el navegador
- **Persistencia:** 3 tablas Postgres

## Arquitectura

```
iterum/ai/
├── __init__.py     Registra modelos + rutas
├── models.py       IterumAIChat / IterumAIMessage / IterumAICanvas
├── tools.py        15 @function_tool: lectura + canvas + mutaciones
├── agent.py        SYSTEM_PROMPT + Agent factory + Runner streamed
└── routes.py       8 endpoints REST + SSE
```

## Tools disponibles al agente (15 total)

### Lectura (9)
| Tool | Para qué |
|---|---|
| `get_dashboard_kpis` | KPIs principales con filtros + nps_target=77 |
| `get_ranking` | Ranking ordenable de asesores |
| `get_agent_detail` | Detalle de un asesor: KPIs + últimos D y P |
| `get_top_detractors` | Peores casos con causa raíz |
| `get_keyword_patterns` | Patrones detectados + origen + top alertas |
| `get_root_cause_breakdown` | 4 distribuciones (tipo/responsabilidad/motivo/origen) |
| `get_coaching_panel` | Panel coaching agrupado por urgencia |
| `search_comments` | Búsqueda textual en comentarios libres |
| `compare_periods` | Compara KPIs entre 2 ventanas temporales |

### Canvas (3)
| Tool | Para qué |
|---|---|
| `canvas_write` | Sobrescribe el workspace con markdown |
| `canvas_append` | Agrega contenido al final |
| `canvas_read` | Lee el estado actual (incluye ediciones manuales del admin) |

### Mutaciones (3)
| Tool | Para qué |
|---|---|
| `set_audit_review` | Marca survey como correcto/dudoso/incorrecto |
| `create_coaching_session` | Crea ficha de coaching para un asesor |
| `add_root_cause_analysis` | Registra 5 porqués de un detractor |

Las mutaciones solo se usan cuando el admin lo pide explícitamente — el SYSTEM_PROMPT
instruye al modelo a confirmar antes de mutar.

## Flujo de un mensaje

```
1. Admin escribe pregunta
   POST /iterum/api/ai/chats/<id>/message  { "content": "..." }

2. Backend persiste el mensaje user, encola un thread async

3. Thread llama Runner.run_streamed() con el Agent + previous_messages

4. SDK abre conexión a OpenAI, recibe eventos:
   - response.reasoning_summary_text.delta  → razonamiento del modelo
   - tool_call_item                         → modelo invoca una tool
   - tool_call_output_item                  → resultado de la tool
   - response.output_text.delta             → token de respuesta final

5. Cada evento se traduce a SSE y se envía al navegador:
   event: reasoning      data: {"delta": "..."}
   event: tool_call      data: {"name": "...", "args": {...}}
   event: tool_output    data: {"name": "...", "result": {...}}
   event: canvas_update  data: {"version": 5, "content_md": "..."}
   event: assistant_delta data: {"delta": "..."}
   event: done           data: {"message_id": 42}

6. El JS del cliente renderiza en vivo:
   - Bloque "🧠 Razonamiento" colapsable (auto-collapse cuando arranca la respuesta)
   - Chips "🔧 tool_name → resultado" colapsables
   - Texto de respuesta token a token
   - Canvas flashea cuando el modelo lo actualiza

7. Backend persiste cada item en iterum_ai_message + actualiza iterum_ai_canvas
```

## Canvas (workspace)

Panel derecho de la UI con 2 secciones:
- **Editor (textarea)**: markdown editable. Ctrl+S guarda.
- **Preview (HTML)**: render live del markdown.

El admin puede:
- Editar manualmente cualquier momento (queda en la próxima request)
- Pedir al modelo: *"actualizá el canvas con la lista de los 10 detractores urgentes"*

El modelo puede:
- `canvas_write(content_md, title)` → reemplaza todo
- `canvas_append(content_md)` → agrega al final
- `canvas_read()` → lee lo que está actualmente (incluso ediciones manuales)

Cada operación incrementa `version` y el canvas se loggea en `NPSAccessLog`.

## Esquema de DB

```python
iterum_ai_chat
  id, user_id (FK users), title, created_at, last_message_at,
  total_tokens, total_cost_usd, model, archived

iterum_ai_message
  id, chat_id (FK), role (user|assistant|reasoning|tool_call|tool_output|canvas),
  content, tool_name, tool_args_json, tool_result_json,
  tokens, model, created_at

iterum_ai_canvas
  id, chat_id (FK UNIQUE), title, content_md, content_data_json,
  updated_at, version
```

Cada chat tiene exactamente 1 canvas (cascade delete). Cada mensaje preserva el
tool call/output completo para auditoría legal.

## Permisos

- **`/iterum/ai`** (página): `@iterum_admin_required` → solo superadmin
- **`/iterum/api/ai/*`**: idem
- Los chats están aislados por `user_id` (un admin no ve los chats de otro admin)
- Cada acción se loggea en `NPSAccessLog` con `action=ai_*`

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `OPENAI_API_KEY` | — | (requerido) Token del chat normal, se reusa |
| `ITERUM_AI_MODEL` | `gpt-5.4` | Modelo a usar (cambiable a `gpt-5.4-mini`, etc.) |
| `ITERUM_AI_REASONING_EFFORT` | `medium` | `low` / `medium` / `high` |

## Migración

```bash
python migrate_iterum_ai.py   # idempotente
```

Encadenada en Dockerfile después de las migraciones de Iterum.

## Costos estimados

Con `gpt-5.4` + reasoning medium:
- ~$0.05-0.15 USD por conversación de 10 turnos con tool use
- Si lo usás 5 conversaciones/día: ~$10-25 USD/mes
- Cada chat trackea `total_cost_usd` (próxima iteración: parsear usage del SDK)

## Limitaciones conocidas

- El thread async corre dentro del worker de gunicorn → con `--workers 4` y muchos
  usuarios concurrentes hay que aumentar el pool. Para 1 admin a la vez está bien.
- El parser de `tool_args` asume JSON; si el SDK cambia el formato puede romper.
- El reasoning_summary depende del modelo; si OpenAI lo restringe en alguna versión,
  el panel "🧠 Razonamiento" puede quedar vacío sin afectar el resto.
- No hay rate limiting hardcoded — agregar si abre a más de 1 admin.

## Próximas iteraciones (sugeridas)

- Tracking de tokens reales por mensaje (extraer de `usage` en los eventos del SDK)
- Tool `export_canvas_pdf` para que el admin descargue el plan como PDF (reusa WeasyPrint)
- Tool `send_canvas_email` para mandar el plan al equipo
- Mostrar costo USD por conversación en el sidebar
- Búsqueda dentro del historial de chats
- Estrellas en mensajes útiles para fine-tuning futuro
