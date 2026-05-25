# Iterum · Formato de XLSX

El parser (`iterum/services/excel_parser.py`) detecta automáticamente variaciones
de nombres de columnas. La detección es **case-insensitive** y **acento-insensitive**.

## Columnas obligatorias

| Canónica | Aliases reconocidos |
|---|---|
| `response_date` | fecha, fecha respuesta, fecha de respuesta, fecha encuesta, date, timestamp, fecha hora, fecha y hora |
| `nps_score` | nps, score, puntaje, nota, calificación, rating, puntuación |

Si faltan, el upload falla con HTTP 400 antes de procesar.

## Columnas opcionales

| Canónica | Aliases reconocidos |
|---|---|
| `channel` | canal, channel, medio, tipo, tipo canal, canal contacto |
| `cell` | célula, celula, cell, equipo, grupo, sector, célula operativa |
| `agent_name` | asesor, agente, agent, nombre asesor, nombre agente, operador, representante, ejecutivo |
| `agent_doc` | documento, doc, dni, cédula, cedula, ci, legajo, id asesor, id agente |
| `comment` | comentario, comment, feedback, observación, observacion, opinión, opinion, mensaje |

## Formatos de fecha aceptados

- `2026-05-01 10:00:00`
- `2026-05-01 10:00`
- `2026-05-01`
- `01/05/2026 10:00:00`
- `01/05/2026 10:00`
- `01/05/2026`
- `01-05-2026`
- `05/01/2026` (formato US)
- Excel native datetime cells

## Normalización del canal

El parser normaliza variantes del campo `channel` a 2 valores canónicos:

- `whatsapp` ← "whatsapp", "wpp", "wsp", "wa", "WhatsApp", etc.
- `call` ← "llamada", "call", "telefónico", "phone", "voz", etc.

Cualquier otra cadena se preserva tal cual (truncada a 20 chars).

## Categorización NPS

```
9-10 → promotor
7-8  → pasivo
0-6  → detractor
```

## Deduplicación

Cada fila se hashea con sha256 de:

```
fecha_minuto + agent_doc + nps_score + comment[:200] + channel
```

Si el hash ya existe en la DB (de una carga previa), la fila se cuenta como
`rows_duplicate` y no se inserta. Esto permite cargas incrementales del mismo
sistema upstream sin temor a duplicar.

## Filas inválidas

Una fila se cuenta como `rows_invalid` (y no se inserta) si:
- No tiene fecha parseable
- No tiene NPS score válido (entero entre 0 y 10)

El resto de los campos pueden faltar — quedan como NULL.

## Tamaño máximo

50 MB por archivo (heredado del `MAX_CONTENT_LENGTH` global de iXpert).

## Procesamiento async

El archivo se sube y se devuelve `202 Accepted` con `upload_id`. El cliente debe
hacer polling a `/iterum/api/upload/<id>/status` cada 2s hasta que `status` sea
`done` o `failed`. Tiempo típico: 1-10 segundos para hasta 50k filas.
