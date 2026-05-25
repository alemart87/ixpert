# Iterum · API REST

Base URL: `/iterum/api`

Todas las rutas requieren `@login_required`. Permisos adicionales por endpoint.

## Convenciones

- Respuestas JSON con `Content-Type: application/json; charset=utf-8`
- Errores: `{"error": "mensaje"}` + HTTP status apropiado
- Filtros via query string: `channel`, `cell`, `agent_doc`, `from_date`, `to_date`
- Paginación: `page` (default 1), `per_page` (default 50, max 100)

## Endpoints

### Upload

| Método | Path | Rol | Cuerpo | Respuesta |
|---|---|---|---|---|
| POST | `/upload` | editor+ | multipart `file` | `{upload_id, status, message}` (202) |
| GET | `/upload/<id>/status` | sup+ | — | estado + stats |
| GET | `/uploads` | sup+ | — | últimos 50 |

### Surveys

| Método | Path | Rol | Cuerpo / Query | Respuesta |
|---|---|---|---|---|
| GET | `/surveys` | sup+ | filtros + `page`, `per_page`, `category`, `q` | lista paginada |
| GET | `/surveys/<id>` | sup+ | — | detalle + audit + root_cause |

### KPIs

| Método | Path | Rol | Query | Respuesta |
|---|---|---|---|---|
| GET | `/kpi/dashboard` | sup+ | filtros + `granularity` | KPIs + breakdowns + timeseries |
| GET | `/kpi/ranking` | sup+ | filtros + `limit` | ranking de agentes |

### Audit

| Método | Path | Rol | Cuerpo | Respuesta |
|---|---|---|---|---|
| POST / PUT | `/audit/<survey_id>` | editor+ | `{verdict, classification, notes}` | audit serializado |
| GET | `/audit` | sup+ | `reviewer_id`, `verdict` | lista |

### Root Cause

| Método | Path | Rol | Cuerpo | Respuesta |
|---|---|---|---|---|
| POST / PUT | `/root-cause/<survey_id>` | editor+ | `{whys[], root_cause, action_owner_id, due_date, status}` | rc serializado |
| GET | `/root-cause/<survey_id>` | sup+ | — | rc o null |
| GET | `/root-causes` | sup+ | — | abiertas + en progreso |

### Coaching

| Método | Path | Rol | Cuerpo | Respuesta |
|---|---|---|---|---|
| POST | `/coaching` | editor+ | `{agent_doc, agent_name?, topic?, urgency?, scheduled_at?}` | coaching (201) |
| PATCH | `/coaching/<id>` | editor+ | `{status?, notes?, topic?, urgency?}` | coaching |
| GET | `/coaching` | sup+ | `coach_id`, `status`, `agent_doc` | lista |

### Report

| Método | Path | Rol | Cuerpo | Respuesta |
|---|---|---|---|---|
| GET | `/report/preview` | sup+ | filtros | payload sin persistir |
| POST | `/report/snapshot` | **admin** | filtros + `period_label` | snapshot creado |
| GET | `/report/<id>.html` | sup+ | — | HTML del reporte |
| GET | `/report/<id>.pdf` | sup+ | — | PDF nativo (download) |
| GET | `/reports` | sup+ | — | lista de snapshots |

### Access Log (auditoría legal)

| Método | Path | Rol | Query | Respuesta |
|---|---|---|---|---|
| GET | `/access-log` | **admin** | `limit`, `action`, `entity_type`, `user_id` | últimas 100 entradas |

### Meta

| Método | Path | Rol | Respuesta |
|---|---|---|---|
| GET | `/meta/filters` | sup+ | `{cells:[], channels:[]}` |

## Códigos HTTP

| Código | Significado |
|---|---|
| 200 | OK |
| 201 | Created |
| 202 | Accepted (upload encolado) |
| 400 | Validación falló |
| 401 | No autenticado |
| 403 | Sin permisos |
| 404 | No encontrado |
| 500 | Error inesperado |
| 503 | PDF nativo no disponible (WeasyPrint missing) |
