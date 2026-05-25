# Iterum · CX Management Platform

Iterum es el módulo de iXpert para gestión integral de la experiencia del cliente (NPS).
Convierte cada experiencia negativa en un ciclo de mejora continua mediante ingesta de
encuestas, dashboard operativo, ranking, auditoría, análisis de causa raíz (5 Porqués),
coaching y reportes ejecutivos en PDF nativo.

## Visión

```
Cliente → Encuesta NPS → Upload XLSX → Iterum
                                        ├── Dashboard / Ranking / Patrones
                                        ├── Auditoría operativa (con trazabilidad legal)
                                        ├── Causa Raíz (5 Porqués) → Plan de acción
                                        ├── Coaching del asesor
                                        └── Reporte ejecutivo (PDF)
```

## Arquitectura (por qué modular)

El HTML original tenía ~4400 líneas en un solo archivo. Iterum en iXpert se rompe en
**capas testeables** para mantener cada archivo bajo 500 líneas:

```
iterum/
├── __init__.py           Exposición del blueprint
├── routes.py             Vistas HTML (200L)
├── api.py                Endpoints JSON (~400L)
├── models.py             7 modelos SQLAlchemy (~180L)
├── permissions.py        Decoradores + log de acceso (~80L)
├── schemas.py            Validación de payloads (~70L)
└── services/             Lógica de negocio pura
    ├── excel_parser.py   Parseo XLSX tolerante a columnas
    ├── dedup.py          Hashing para deduplicación
    ├── jobs.py           Procesamiento en background (ThreadPoolExecutor)
    ├── scoring.py        KPIs, ranking, timeseries
    ├── audit.py          Veredictos operativos
    ├── root_cause.py     5 Porqués + plan de acción
    ├── coaching.py       Sesiones de coaching
    └── reports.py        Snapshot + PDF nativo
```

**Regla de oro:** la lógica de negocio vive en `services/`. Las rutas sólo validan
permisos, parsean payloads y delegan. Esto permite testear sin Flask.

## Componentes del frontend

| Página | Template | JS | Permisos |
|---|---|---|---|
| Dashboard | dashboard.html | iterum-dashboard.js | sup+ |
| Ranking | ranking.html | iterum-ranking.js | sup+ |
| Comentarios | comments.html | iterum-comments.js | sup+ |
| Patrones | patterns.html | iterum-patterns.js | sup+ |
| Auditoría | audit.html | iterum-audit.js | editor+ |
| Causa Raíz | root_cause.html | iterum-root-cause.js | editor+ |
| Coaching | coaching.html | iterum-coaching.js | sup+ |
| Reporte | report.html | iterum-report.js | sup+ (snapshot: admin) |
| Cargar datos | upload.html | iterum-upload.js | editor+ |

CSS scopeado en `static/iterum/css/iterum-base.css` con prefijo `.iterum-` para no
chocar con `static/css/style.css` del portal.

## Roles y permisos

| Rol | Ver | Editar | Auditar | Snapshots | Access Log |
|---|---|---|---|---|---|
| superadmin | ✅ | ✅ | ✅ | ✅ | ✅ |
| analista | ✅ | ✅ | ✅ | ❌ | ❌ |
| supervisor | ✅ | ❌ | ❌ | ❌ | ❌ |
| asesor | ❌ | ❌ | ❌ | ❌ | ❌ |

Decoradores en `iterum/permissions.py`:
- `@iterum_required` — bloquea solo asesores
- `@iterum_editor_required` — superadmin + analista
- `@iterum_admin_required` — solo superadmin

## Modelo de datos

Ver [DATA_MODEL.md](./DATA_MODEL.md). Resumen:

- **nps_upload** — historial de cargas XLSX (quién, cuándo, qué archivo)
- **nps_survey** — una fila por respuesta NPS (granularidad atómica + dedupe por hash)
- **nps_audit** — veredicto operativo por encuesta (1:1 con survey)
- **nps_root_cause** — 5 Porqués + plan de acción (1:1 con survey detractor)
- **nps_coaching** — sesiones de coaching agendadas/realizadas
- **nps_report_snapshot** — reportes ejecutivos persistidos
- **nps_access_log** — auditoría legal: todo acceso/cambio queda registrado

## Procesamiento en background

Para no trancar requests con uploads grandes (~50k filas), se usa
`concurrent.futures.ThreadPoolExecutor` (2 workers por defecto, configurable con
`ITERUM_JOB_WORKERS`). El estado vive en `nps_upload.status`:

```
pending → processing → done | failed
```

El frontend hace polling a `/iterum/api/upload/<id>/status` cada 2s. Si un worker
muere mid-job, el sweeper (`sweep_stale_processing`) marca como failed los uploads
trabados más de 15 minutos.

## PDF nativo

Generado con **WeasyPrint** (HTML/CSS → PDF). Dependencias del sistema en Dockerfile:
`libpango libcairo libgdk-pixbuf`. El template `report_standalone.html` define un
layout A4 print-ready.

## Auditoría legal (compliance bancario)

Toda acción sobre datos sensibles (ver comentarios de clientes, crear/editar veredictos,
generar reportes, exportar PDF) registra una entrada en `nps_access_log` con:
- `user_id` + `ip_address` + `user_agent`
- `action` (view/create/update/delete/export/upload)
- `entity_type` + `entity_id`
- `payload_json` (snapshot del cambio)

El log es consultable solo por superadmin en `/iterum/api/access-log`.

## Cómo agregar una nueva métrica

1. Implementar el cálculo en `iterum/services/scoring.py` (función pura testable).
2. Agregar test en `tests/test_iterum/test_scoring.py`.
3. Exponer endpoint en `iterum/api.py` reutilizando filtros de `schemas.parse_filters`.
4. Renderizar en el template de la página que la consume.

## Cómo agregar una nueva clasificación de auditoría

Las clasificaciones son strings libres por ahora (no enum) para flexibilidad.
Si querés constraint, agregá un campo a `iterum/services/audit.py`.

## Mantenimiento

- Cualquier `.py` que supere 500 líneas → partir en módulos
- Cualquier `.js` que supere 400 líneas → partir por feature
- Migraciones siempre idempotentes (`CREATE TABLE IF NOT EXISTS`, `_ensure_column`, etc.)
- Tests en `tests/test_iterum/` con SQLite en memoria (rápido, aislado)
- Logs con prefijo `[iterum.<modulo>]` (ej: `[iterum.jobs] upload=42 done...`)

## Comandos útiles

```bash
# Correr tests
python -m pytest tests/test_iterum/ -v

# Aplicar migración manualmente (idempotente)
python migrate_iterum.py

# Retirar contenido legacy (idempotente)
python migrate_iterum_retire_legacy.py

# Procesar uploads atascados manualmente
python -c "from app import app; from iterum.services.jobs import sweep_stale_processing; sweep_stale_processing(app)"
```

## Roadmap (no implementado)

- IA semántica sobre comentarios (call_openai en chat.py)
- Notificaciones push de coaching pendiente
- Export Excel del reporte
- Comparativa entre períodos (delta NPS semana/semana)
