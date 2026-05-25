# Iterum · Formato de XLSX

El parser (`iterum/services/excel_parser.py`) detecta automáticamente variaciones
de nombres de columnas. La detección es **case-insensitive** y **acento-insensitive**.

## Matching de columnas (token-based)

El parser **tokeniza** cada header (lo divide en palabras alfanuméricas) y busca
tokens disparadores. Esto significa que "FECHA_REGISTRADA (-04:00 GMT)" matchea
por el token `fecha`, "AGENTE_ATENCION" por `agente`, "COMENTARIO_COMPLETO" por
`comentario`, etc.

## Columnas obligatorias

| Canónica | Tokens disparadores |
|---|---|
| `response_date` | `fecha`, `date`, `timestamp` |
| `nps_score` | `nps`, `nota`, `puntaje`, `calificacion`, `rating`, `puntuacion`, `score` |

Si faltan, el upload falla en `processing` y se marca como `failed` con mensaje
explicativo.

## Columnas opcionales

| Canónica | Tokens disparadores |
|---|---|
| `channel` | `canal`, `channel`, `medio`, `sucursal` |
| `cell` | `celula`, `equipo`, `sector` |
| `agent_name` | `asesor`, `agente`, `agent`, `operador`, `representante`, `ejecutivo` |
| `agent_doc` | `documento`, `dni`, `cedula`, `legajo` |
| `comment` | `comentario`, `comment`, `feedback`, `observacion`, `opinion`, `mensaje` |

**Nota sobre `sucursal`:** algunos sistemas del banco guardan el canal (WHATSAPP,
LLAMADA) en la columna llamada `SUCURSAL_ATENCION`. Por eso `sucursal` se incluye
como disparador de `channel`. Los valores se normalizan después a `whatsapp` o `call`.

## Prioridad de matching

Los campos se procesan en este orden para evitar conflictos:
1. `agent_doc` (más específico: doc, dni, cédula)
2. `response_date`
3. `nps_score`
4. `comment`
5. `cell`
6. `channel`
7. `agent_name`

Una vez que una columna se asigna a un campo, no se considera para los siguientes.
Esto evita que `DOC_ASESOR` matchee primero `agent_name` por la palabra "asesor".

## Columnas que NO matchean (por diseño)

Estas columnas del export real del banco son ignoradas, lo cual es correcto:
- `TIPO_RESPUESTA`, `NRO_CLIENTE`, `NOMBRE` (cliente, no asesor), `SEGMENTO`
- `PROVEEDOR_ATENCION`, `ESFUERZO`, `RESOLUCION`, `ENCUESTA`
- `YY`, `MM`, `DD`, `SEM` (descomposición de fecha — usamos `FECHA_REGISTRADA`)
- `Tipo_Gestion`, `Motivo_Cliente`, `Origen_Principal`, `Problema_Descrito`
- `Porque_1`, `Porque_2`, `Porque_3_Raiz` (5 porqués operativos — se cargan
  manualmente desde la UI de Causa Raíz, no del upload)
- `Historial del chat`, `Cliente recurrente en WP`

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
