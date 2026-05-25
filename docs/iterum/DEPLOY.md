# Iterum · Deployment

## Dependencias nuevas

### Python
- `openpyxl==3.1.5` — parseo XLSX server-side
- `weasyprint==62.3` — generación de PDF nativo

### Sistema (Debian/Ubuntu, ya en Dockerfile)
- `libpango-1.0-0`, `libpangoft2-1.0-0` — text shaping
- `libcairo2` — graphics backend
- `libgdk-pixbuf2.0-0` — image support
- `libffi8` — cffi runtime
- `shared-mime-info` — mime detection
- `fonts-liberation` — fonts del PDF

## Migración

El Dockerfile ejecuta en orden:

```
migrate_pre.py
migrate.py (... v2 a v12 ...)
migrate_iterum.py            ← crea 7 tablas Iterum
migrate_iterum_retire_legacy.py  ← desactiva /content/iterum-cx
update_keywords.py
```

Ambas migraciones de Iterum son **idempotentes**: se pueden re-correr sin riesgo.

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `ITERUM_JOB_WORKERS` | 2 | Threads del pool de procesamiento de uploads |
| `DATABASE_URL` | — | Postgres en producción, sqlite en tests |

## Verificación post-deploy

1. `GET /iterum/dashboard` con un superadmin → 200
2. Subir un XLSX de prueba en `/iterum/upload` → polling de status hasta `done`
3. Comprobar que `/iterum/api/access-log` registra el view + upload
4. Generar un snapshot y descargar el PDF → debe llegar < 5s

## Rollback

Las tablas Iterum no afectan al resto del sistema. Para rollback:

1. Revertir el deploy (volver al commit anterior)
2. Las tablas Iterum quedan en la DB sin uso (no se borran datos)
3. El contenido legacy `iterum-cx` se puede re-activar:
   ```sql
   UPDATE contents SET is_active = true WHERE slug = 'iterum-cx';
   ```

## Worker múltiples

Si gunicorn corre con varios workers, cada uno tiene su propio ThreadPoolExecutor.
El job vive en el worker que recibió el POST. Otros workers pueden consultar el
estado vía DB sin problema.

Si un worker se reinicia mid-job, queda un upload en `processing`. El sweeper que
corre al startup (`sweep_stale_processing`) marca como `failed` los uploads
trabados más de 15 min.

## Monitoreo

Logs estructurados con prefijo `[iterum.<modulo>]`:

```
[iterum.jobs] upload=42 done total=2500 new=2470 dup=30 inv=0
[iterum.jobs] upload=43 failed: La planilla esta vacia...
[iterum.jobs] sweep marked 1 stale uploads as failed
```

Buscar `[iterum.` en los logs de Render para troubleshooting.

## Backups recomendados

Las tablas críticas para backup nightly:
- `nps_survey` (datos crudos)
- `nps_audit` (trabajo de los analistas)
- `nps_root_cause` (análisis estructurados)
- `nps_coaching` (sesiones programadas)
- `nps_access_log` (auditoría legal — **nunca** truncar)
