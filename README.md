# iXpert — Portal de Conocimiento + Vex People Predictive

Portal interno con base de conocimiento, asistente de IA, **simulador de entrenamiento** con clientes ficticios, y un **sistema de evaluación predictivo (Vex)** que mide el desempeño del asesor en 6 dimensiones y emite una recomendación de incorporación.

---

## Tabla de contenido

- [Descripción](#descripción)
- [Stack técnico](#stack-técnico)
- [Roles y permisos](#roles-y-permisos)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Variables de entorno](#variables-de-entorno)
- [Despliegue](#despliegue-en-rendercom)
- [Desarrollo local](#desarrollo-local)
- [Migraciones de BD](#migraciones-de-base-de-datos)
- [Modelos de IA](#modelos-de-ia)
- [Sistema de scoring (resumen)](#sistema-de-scoring-resumen)
- [Modos de Scoring](#modos-de-scoring)
- [Tipos de contenido](#tipos-de-contenido)
- [Editor de Trivia](#editor-de-trivia)
- [Documentación adicional](#documentación-adicional)

---

## Descripción

**iXpert** permite a una organización:

- Centralizar contenido operativo (procedimientos, FAQs, tutoriales, calculadoras y juegos).
- Asistente IA (**iXpert AI**) que responde consultas en base al contenido cargado.
- **Entrenamiento con clientes simulados**: el asesor chatea con una persona ficticia interpretada por un LLM y al cerrar la sesión recibe evaluación automática (NPS, correctitud, ortografía, breakdown de empatía).
- **Vex People Skill Predictive**: agrega los resultados en un perfil de 6 dimensiones (Comunicación, Empatía, Resolución, Velocidad, Adaptabilidad, Compliance) → `Predictive Index` → categoría (Elite / Alto / Desarrollo / Refuerzo) → recomendación (Recomendado / Observaciones / No Recomendado).
- **Modos de scoring** configurables (Flexible / Standard / Exigente) con barreras de competencia básica que protegen contra perfiles inflados por sesiones abandonadas.
- **Editor PRO** de contenido en 3 modos: visual (Quill), trivia (formulario) y HTML/JS personalizado (sandbox).
- **Página de novedades** integrada para comunicar al equipo qué cambió.

---

## Stack técnico

| Componente | Tecnología |
|---|---|
| Backend | Flask 3.1 + SQLAlchemy + Flask-Login |
| Base de datos | PostgreSQL (Render) / SQLite (tests) |
| Frontend | Jinja2 + Vanilla JS + Quill + Chart.js |
| IA | OpenAI **GPT-5.4 mini** (`max_completion_tokens`) |
| Server | Gunicorn |
| Despliegue | Docker en [Render.com](https://render.com) |

---

## Roles y permisos

Cuatro roles. Solo el **SuperAdmin** crea usuarios.

| Acción | Asesor | Supervisor | **Analista** | SuperAdmin |
|---|:-:|:-:|:-:|:-:|
| Mis entrenamientos | ✓ | ✓ | ✓ | ✓ |
| Crear escenarios | | | ✓ | ✓ |
| CX Dashboard | | con permiso | ✓ | ✓ |
| Vex Resultados / Metodología | | con permiso | ✓ | ✓ |
| **Reiniciar métricas con snapshot** | | | ✓ | ✓ |
| Modos de Scoring | | | | ✓ |
| Gestión de usuarios | | | | ✓ |
| Gestión de contenidos | | | | ✓ |
| Novedades | | | | ✓ |

- **SuperAdmin** se crea por variable de entorno (`SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD`); no se puede crear desde la UI.
- **Analista** y **Supervisor** y **Asesor** los crea el SuperAdmin desde `/admin/users`.
- **Supervisor** entra al CX Dashboard solo si el SuperAdmin le otorga `TrainingViewPermission`.

---

## Estructura del proyecto

```
ixpert/
├── app.py                      # Flask app, login, viewer, filtros Jinja
├── models.py                   # SQLAlchemy: User, Content, Category, Training*, VexProfile, ScoringModeOverride
├── admin.py                    # CRUD contenidos / categorías / usuarios + Insights AI + /admin/novedades
├── training.py                 # Blueprint training: escenarios, sesiones, batches, ART, Vex
├── chat.py                     # Blueprint chat: iXpert AI (GPT-5.4 mini, max_completion_tokens)
├── analytics.py                # Tracking: pageview / click / search
├── scoring_modes.py            # Defaults Flexible/Standard/Exigente + helpers
├── scoring.md                  # Referencia técnica del scoring
├── migrate_pre.py              # ALTER TABLE de columnas nuevas (corre PRIMERO en deploy)
├── migrate.py                  # Importa HTMLs iniciales de iXpert/* a BD
├── migrate_v2.py               # Tablas Training/Batch/VexProfile
├── migrate_v5.py               # avg_response_time (ART)
├── migrate_v6.py               # scoring_mode + tabla scoring_mode_overrides
├── migrate_v7.py               # client_response_delay_seconds
├── migrate_v8.py               # Backfill HTML completo desde disco
├── migrate_v9.py               # content_type + source_hash + sync from disk
├── migrate_v10.py              # content_data (JSON) + extracción 42 preguntas trivia
├── update_keywords.py          # Enriquece keywords desde headings/strong + diccionario
├── Dockerfile                  # Render: orquesta migrate_pre → migrate → v* → keywords → gunicorn
├── requirements.txt
├── iXpert/                     # HTMLs originales que se importan al primer deploy
├── static/
│   ├── css/                    # style.css, chat.css, training.css
│   ├── js/                     # chat.js, training.js, tracking.js
│   ├── img/                    # assets
│   └── imagenes/               # uploads via Quill
└── templates/
    ├── base.html               # Header, nav, chat widget, loader, footer
    ├── login.html, viewer.html, index.html, category.html
    ├── games/
    │   └── trivia.html         # Plantilla stock del juego (preguntas inyectadas)
    ├── admin/
    │   ├── dashboard.html, content_list.html, content_edit.html
    │   ├── categories.html, users.html, chat_analytics.html
    │   ├── training_dashboard.html, training_scenarios.html
    │   ├── vex_dashboard.html, vex_profile.html, vex_methodology.html
    │   ├── vex_modos.html      # Editor de modos (SuperAdmin)
    │   └── novedades.html      # Página de novedades destacada
    └── training/
        ├── index.html, session.html, result.html, batch_result.html
```

---

## Variables de entorno

Crear `.env` en la raíz:

```
DATABASE_URL=postgresql://user:password@host:5432/dbname
SECRET_KEY=tu-clave-secreta-larga-y-aleatoria
[email protected]
SUPERADMIN_PASSWORD=contraseña-segura
OPENAI_API_KEY=sk-tu-api-key-de-openai
```

| Variable | Requerida | Descripción |
|---|:-:|---|
| `DATABASE_URL` | sí | URI PostgreSQL (`postgres://` también vale, se normaliza). |
| `SECRET_KEY` | sí | Sesión Flask. Cualquier string largo aleatorio. |
| `SUPERADMIN_EMAIL` | sí | Email del admin principal. |
| `SUPERADMIN_PASSWORD` | sí | Contraseña inicial del admin. |
| `OPENAI_API_KEY` | sí | Key con acceso a `gpt-5.4-mini`. |
| `UPLOAD_DIR` | no | Path para uploads (default `static/imagenes`). En Render conviene apuntar a un disco persistente. |

---

## Despliegue en Render.com

1. **Crear PostgreSQL**
   - New → PostgreSQL. Plan Free o Starter.
   - Copiar la *Internal Database URL*.

2. **Crear Web Service**
   - New → Web Service → conectar el repo.
   - Runtime: **Docker**.
   - Variables (ver arriba).
   - Opcional: Persistent Disk montado en `/persistent` + `UPLOAD_DIR=/persistent`.

3. **Primer arranque**
   - Render lee `Dockerfile`, instala deps y ejecuta el chain:
     ```
     migrate_pre.py        # ALTER TABLE columnas nuevas
     migrate.py            # importar HTMLs iniciales
     migrate_v2.py         # tablas training
     migrate_v5.py         # ART
     migrate_v6.py         # modos de scoring
     migrate_v7.py         # delay del cliente
     migrate_v8.py         # backfill HTML completo
     migrate_v9.py         # content_type + source_hash
     migrate_v10.py        # content_data trivia
     update_keywords.py    # keywords
     gunicorn app:app
     ```

4. **Post-deploy**
   - Login con SUPERADMIN_EMAIL/PASSWORD.
   - El SuperAdmin crea usuarios (Asesor / Supervisor / Analista) en `/admin/users`.

---

## Desarrollo local

```bash
git clone <repo>
cd ixpert
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # editar con tus valores
python migrate_pre.py
python migrate.py
python migrate_v2.py
python migrate_v5.py
python migrate_v6.py
python migrate_v7.py
python migrate_v8.py
python migrate_v9.py
python migrate_v10.py
python update_keywords.py
python app.py          # http://localhost:5000
```

---

## Migraciones de base de datos

Cada migración es **idempotente** (verifica si la columna/tabla ya existe).

| Archivo | Cambia |
|---|---|
| `migrate_pre.py` | ALTER TABLE para columnas nuevas (corre PRIMERO en producción para que el ORM no falle). |
| `migrate.py` | Importa los `iXpert/*.html` a la tabla `contents`. |
| `migrate_v2.py` | Crea tablas `training_*` y `vex_profiles`. |
| `migrate_v5.py` | `training_sessions.avg_response_time` (ART). |
| `migrate_v6.py` | `scoring_mode` en escenario y batch + tabla `scoring_mode_overrides`. |
| `migrate_v7.py` | `client_response_delay_seconds` en escenario y batch. |
| `migrate_v8.py` | Backfill: re-importa HTMLs completos desde `iXpert/*` a slugs cuya BD venía truncada. |
| `migrate_v9.py` | `contents.content_type` + `source_hash` + sync inteligente desde disco. |
| `migrate_v10.py` | `contents.content_data` + extrae las 42 preguntas del trivia y arma JSON estructurado. |

---

## Modelos de IA

**iXpert AI (asistente del portal) y cliente simulado / evaluador de entrenamientos** usan el mismo modelo: **`gpt-5.4-mini`** vía la API de OpenAI con `max_completion_tokens`.

Si volvés a un modelo de la familia GPT-4 hay que renombrar el parámetro a `max_tokens` (ver `chat.py:call_openai`).

Captura de errores robusta: la implementación distingue `HTTPError` de `URLError` y loguea el body de la respuesta cuando OpenAI rechaza un request — útil para diagnosticar parámetros inválidos / modelo sin acceso.

---

## Sistema de scoring (resumen)

Cada **sesión de entrenamiento** cerrada se evalúa con IA y produce:
- `nps_score` (0-10)
- `response_correct` (bool)
- `spelling_errors` (cuenta solo errores que afectan comprensión)
- `empathy_breakdown` con 4 pilares jerárquicos: Nombre / Contexto / Calidez / Resolución (15 / 25 / 25 / 35 %)

El **perfil VEX agregado** (`calculate_vex_profile`) procesa todas las sesiones completadas (mín. 2) y produce 6 dimensiones en escala Sten 1-10:

| Dimensión | Peso PI (Standard) |
|---|:-:|
| Empatía (rúbrica + NPS) | 25% |
| Resolución | 22% |
| Comunicación | 18% |
| Velocidad (ART + WPM) | 15% |
| Adaptabilidad | 10% |
| Compliance | 10% |

**Métrica clave: ART (Average Response Time)** — tiempo medio entre el mensaje del cliente y la respuesta del asesor. Mide solo lo que el asesor controla (no la lentitud del cliente).

**Hard caps universales** (independientes del modo):
- `abandonment_rate > 40%` → max categoría Desarrollo, max recomendación Observaciones
- `correct_rate < 0.5` → max Observaciones
- `avg_nps < 4` → max Observaciones

Detalle completo de fórmulas, pisos y conversión Sten → ver [`scoring.md`](./scoring.md).

---

## Modos de Scoring

Cada escenario se evalúa con **uno de tres modos**. Al iniciar un entrenamiento, el batch hace *snapshot* del modo (no cambia aunque después editen el escenario).

| Modo | Cuándo | Recomendado PI ≥ |
|---|---|:-:|
| 🟢 **Flexible** | Nuevos ingresos, capacitación, selección | 55% |
| 🔵 **Standard** | Producción real (default) | 65% |
| 🔴 **Exigente** | Expertos, calibración | 75% |

El SuperAdmin puede personalizar los parámetros internos (pesos, pisos, curva ART, umbrales) en `/admin/vex/modos`. Los overrides se guardan en `scoring_mode_overrides`. Botón "Volver a valores de fábrica" disponible.

---

## Tipos de contenido

Tres modos al crear/editar contenido:

| Tipo | Editor | Render | Casos de uso |
|---|---|---|---|
| `visual` | Quill (texto enriquecido) | Inline | Artículos, tutoriales, FAQs |
| `trivia` | Formulario de preguntas (sin código) | iframe sandbox con plantilla stock | Juegos de preguntas y respuestas |
| `raw_html` | Textarea + previsualización | iframe sandbox | Calculadoras, simuladores, juegos custom |

Detección automática + sincronización con `iXpert/*` vía `source_hash`: contenidos sin tocar por el admin se actualizan automáticamente cuando cambia el repo; contenidos editados en la UI se preservan.

---

## Editor de Trivia

Acceso: `/admin/contents/<id>/edit` con tipo "🎮 Trivia (juego)".

- Título del juego, pantalla de bienvenida, preguntas por partida, tiempo por pregunta.
- Cards de pregunta con texto + 4 opciones (A/B/C/D) + radio button para marcar la correcta.
- Agregar/eliminar preguntas dinámicamente.
- Las preguntas se guardan como JSON en `content_data`.
- Al ver `/content/<slug>` se renderiza la plantilla `templates/games/trivia.html` con las preguntas inyectadas, dentro de un iframe sandbox que ocupa casi todo el viewport.

Por defecto al primer deploy, `migrate_v10.py` extrae las 42 preguntas del archivo `iXpert/varios/game1.html` y las carga en `content_data` para el slug `game1`.

---

## Documentación adicional

- [`scoring.md`](./scoring.md) — Referencia técnica completa del sistema de scoring (fórmulas, pisos, umbrales, hard caps, ART).
- `/admin/vex/methodology` — Versión visible al usuario (HTML) con la metodología, dimensiones, escala Sten, patrones diagnósticos y referencias bibliográficas.
- `/admin/novedades` — Página de novedades destacada para el SuperAdmin: explica los cambios recientes en lenguaje claro para compartir con el equipo.
- [`docs/iterum/README.md`](./docs/iterum/README.md) — Iterum CX Management Platform (NPS, auditoría, causa raíz, coaching, reportes PDF).
- [`docs/iterum/DATA_MODEL.md`](./docs/iterum/DATA_MODEL.md) — Esquema de tablas Iterum.
- [`docs/iterum/API.md`](./docs/iterum/API.md) — Contrato REST de Iterum.
- [`docs/iterum/EXCEL_FORMAT.md`](./docs/iterum/EXCEL_FORMAT.md) — Formato de XLSX aceptado.
- [`docs/iterum/DEPLOY.md`](./docs/iterum/DEPLOY.md) — Deploy y rollback de Iterum.

## Iterum · CX Management Platform

Módulo de gestión integral del NPS (mayo 2026). Reemplaza al HTML standalone
legacy `/content/iterum-cx` por una app full-stack con:

- Ingesta server-side de XLSX (background jobs con ThreadPoolExecutor, polling de estado)
- Deduplicación automática (hash sha256 por respuesta) → cargas incrementales seguras
- Dashboard, ranking de asesores, breakdown por canal/célula, evolución temporal
- Auditoría operativa con trazabilidad legal (NPSAccessLog: quién vio/editó qué)
- Causa Raíz (5 Porqués) + plan de acción con responsable y vencimiento
- Coaching con urgencia automática basada en proporción de detractores
- Reporte ejecutivo persistido como snapshot + export **PDF nativo** (WeasyPrint)
- Acceso vía dropdown navbar para superadmin/analista/supervisor (asesor sin acceso)

Roles: superadmin (todo), analista (todo salvo snapshots), supervisor (read-only).
Snapshots ejecutivos y consulta del access-log restringidos a superadmin.

Arquitectura modular (`iterum/routes.py` + `api.py` + `services/*` + `models.py`),
cada archivo bajo 500 líneas para facilitar mantenimiento. 27 tests automatizados
cubren parser, dedupe, scoring, audit, root cause, coaching, permisos y access log.

---

## Licencia

Sistema desarrollado por ArrowX. Motor de evaluación: **Vex People Skill Predictive v2.0**.
