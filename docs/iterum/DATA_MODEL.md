# Iterum · Modelo de datos

Todos los modelos viven en `iterum/models.py` y comparten la instancia `db` del proyecto.

## Diagrama de relaciones

```
users (existente)
   │
   ├─ nps_upload.uploaded_by_id
   ├─ nps_audit.reviewer_id
   ├─ nps_root_cause.created_by_id / action_owner_id
   ├─ nps_coaching.coach_id
   ├─ nps_report_snapshot.generated_by_id
   └─ nps_access_log.user_id

nps_upload (1) ──── (n) nps_survey
nps_survey (1) ──── (0..1) nps_audit
nps_survey (1) ──── (0..1) nps_root_cause
nps_survey  →  nps_coaching.related_survey_ids (JSON array, no FK)
```

## Tablas

### `nps_upload`
Registro de cada XLSX cargado. Auditoría de quién subió qué.

| Columna | Tipo | Notas |
|---|---|---|
| id | int PK | |
| uploaded_by_id | int FK → users.id | quién subió |
| filename | str | nombre original |
| file_hash | str(64) UNIQUE | sha256 del archivo |
| file_size_bytes | int | |
| status | str(20) | pending / processing / done / failed |
| error_message | text | si failed |
| rows_total, rows_new, rows_duplicate, rows_invalid | int | métricas del job |
| period_start, period_end | date | rango detectado del XLSX |
| created_at, processed_at | datetime | |

### `nps_survey`
Respuesta NPS individual (granularidad atómica).

| Columna | Tipo | Notas |
|---|---|---|
| id | int PK | |
| upload_id | int FK → nps_upload.id | |
| response_date | datetime, index | |
| channel | str(20), index | whatsapp / call |
| cell | str(100), index | célula operativa |
| agent_name, agent_doc | str | doc index |
| nps_score | int, index | 0..10 |
| category | str(20), index | promotor / pasivo / detractor |
| comment | text | |
| unique_hash | str(64) UNIQUE, index | dedupe por (date+doc+score+comment+channel) |

Índices compuestos:
- `(channel, response_date)` - filtros de dashboard
- `(cell, response_date)` - filtros por célula
- `(agent_doc, response_date)` - ranking de agentes

### `nps_audit`
Veredicto operativo del analista. 1:1 con survey.

| Columna | Tipo | Notas |
|---|---|---|
| id | int PK | |
| survey_id | int FK → nps_survey.id UNIQUE | uno por survey |
| reviewer_id | int FK → users.id | analista responsable |
| verdict | str(10), index | ok / warn / err |
| classification | str(100) | motivo (string libre) |
| notes | text | |
| reviewed_at, updated_at | datetime | |

### `nps_root_cause`
5 Porqués + plan de acción para detractores.

| Columna | Tipo | Notas |
|---|---|---|
| id | int PK | |
| survey_id | int FK UNIQUE | 1:1 |
| why_1..why_5 | text | escalonado |
| root_cause | text | causa raíz consolidada |
| action_owner_id | int FK → users.id | responsable del fix |
| due_date | date | |
| status | str(20), index | open / in_progress / done |
| created_by_id | int FK | |

### `nps_coaching`
Sesiones de coaching.

| Columna | Tipo | Notas |
|---|---|---|
| id | int PK | |
| agent_doc | str(50), index | documento del asesor |
| agent_name | str(150) | |
| coach_id | int FK → users.id | |
| related_survey_ids | text | JSON array de ids (no FK, soft link) |
| urgency | str(10), index | low / med / high |
| status | str(20), index | pending / done / skipped |
| topic, notes | str/text | |
| scheduled_at, completed_at | datetime | |

### `nps_report_snapshot`
Reporte ejecutivo persistido.

| Columna | Tipo | Notas |
|---|---|---|
| id | int PK | |
| generated_by_id | int FK → users.id | |
| period_label | str(100) | "Mayo 2026 · Sem 21" |
| filters_json | text | snapshot de filtros |
| payload_json | text | KPIs serializados |
| html_blob | text | HTML standalone del reporte |
| created_at | datetime, index | |

El PDF se genera on-the-fly con WeasyPrint a partir de `html_blob` (no se guarda
el binario para no inflar la DB).

### `nps_access_log`
Auditoría LEGAL: todo acceso/cambio a datos sensibles.

| Columna | Tipo | Notas |
|---|---|---|
| id | int PK | |
| user_id | int FK → users.id, index | |
| action | str(20), index | view/create/update/delete/export/upload |
| entity_type | str(30), index | survey/audit/report/coaching/upload/iterum |
| entity_id | int, index | |
| payload_json | text | snapshot (filtros usados, diff, etc) |
| ip_address | str(45) | |
| user_agent | str(500) | |
| created_at | datetime, index | |

Visible solo para superadmin en `/iterum/api/access-log` (paginable por acción, entidad, usuario).
