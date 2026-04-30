# Sistema de Scoring — Vex People Predictive

Documento de referencia del modelo predictivo de talento. Detalla cómo se evalúa cada sesión de entrenamiento y cómo se agregan los resultados en el perfil VEX del asesor.

> **Fuente única de verdad:** `training.py` (función `calculate_vex_profile` y endpoint `end_session`) y `scoring_modes.py` (defaults de cada modo). Si modificás las fórmulas, actualizá este documento.

---

## Tabla de contenidos

- [0. Modos de Scoring](#0-modos-de-scoring-flexible--standard--exigente)
- [1. Capa 1 — Evaluación por sesión (IA)](#1-capa-1--evaluación-por-sesión-ia)
- [2. Capa 2 — Perfil VEX (agregación)](#2-capa-2--perfil-vex-agregación)
- [3. ART — Average Response Time](#3-art--average-response-time)
- [4. Resumen de cambios vs versión anterior](#4-resumen-de-cambios-vs-versión-anterior)
- [5. Campos persistidos](#5-campos-persistidos)
- [6. Migraciones](#6-migraciones)

---

## 0. Modos de Scoring (Flexible / Standard / Exigente)

Cada escenario tiene asignado un modo. Cuando se inicia un entrenamiento, el `TrainingBatch` toma un **snapshot** del modo del escenario, que queda fijo para esa evaluación aunque el escenario se modifique después. Las sesiones previas a esta versión (`scoring_mode = NULL`) son tratadas como **legacy** y se evalúan con `standard`, pero la UI las etiqueta `⚪ Legacy`.

| Modo | Cuándo usar | Recomendado PI ≥ | Saturación ortografía | ART meta |
|------|-------------|------------------|------------------------|----------|
| 🟢 **Flexible** | Nuevos ingresos, capacitación, selección | 55% | 2.85% errores | ≤ 180-240 s |
| 🔵 **Standard** | Asesores en producción (default) | 65% | 4% errores | ≤ 120-180 s |
| 🔴 **Exigente** | Expertos, calibración, excelencia | 75% | 6.6% errores | ≤ 60-120 s |

**El modo afecta:**

- Pesos del Predictive Index
- Pisos mínimos por dimensión
- Saturación de la penalización ortográfica
- Mezcla empatía (pilares vs NPS)
- Curva ART (los 4 cortes)
- Umbrales de categoría (Elite / Alto / Desarrollo)
- Umbrales de recomendación (Recomendado / Observaciones)
- Hint que recibe la IA evaluadora (más generosa o más estricta)

**Customización (solo SuperAdmin):** la vista `/admin/vex/modos` permite editar los parámetros internos de cada modo. Los overrides se guardan en la tabla `scoring_mode_overrides`. Si no hay override, se usan los defaults de fábrica definidos en `scoring_modes.py:DEFAULT_MODES`. El botón "Volver a valores de fábrica" elimina el override.

**Aplicación al perfil VEX agregado:** `calculate_vex_profile` usa el modo del **batch más reciente** del usuario para los cálculos. Las dimensiones Sten son objetivas, pero los pisos, la curva ART y los umbrales finales dependen del modo activo.

---

## 1. Capa 1 — Evaluación por sesión (IA)

Cada sesión cerrada se evalúa con OpenAI (**GPT-5.4 mini**, ID: `gpt-5.4-mini`). El modelo recibe la conversación completa, el escenario, la respuesta esperada y un texto consolidado del asesor para revisión ortográfica. Devuelve un JSON estructurado con las señales que alimentan el perfil agregado.

El cliente simulado durante la sesión y la evaluación final usan el mismo modelo. Si necesitás cambiar el modelo, editá `chat.py` (función `call_openai`).

> ⚠ **GPT-5.x usa `max_completion_tokens`** (no `max_tokens`). Si volvés a un modelo de la familia GPT-4 hay que renombrar el parámetro de vuelta.

### 1.1 Auto-fail

Si el asesor envió **menos de 2 mensajes** o escribió **menos de 8 palabras**, la sesión recibe `nps_score = 1` sin llamar al modelo. Evita inflar tokens en interacciones vacías y deja una marca clara de "no hubo trabajo real".

### 1.2 Salidas del modelo

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `nps_score` | int 0-10 | Sentimiento del cliente al cerrar el chat |
| `response_correct` | bool | ¿Cubrió la esencia del procedimiento? |
| `spelling_errors` | int | Errores que afectan la comprensión (no tildes ni abreviaciones) |
| `empathy_breakdown` | objeto | Cumplimiento de los 4 pilares (ver 1.3) |
| `feedback` | string | Retroalimentación al asesor |
| `strengths` | string | 2-3 fortalezas |
| `improvements` | string | 2-3 áreas de mejora |

### 1.3 Rúbrica de Empatía (jerárquica)

La empatía se evalúa con cuatro pilares ordenados por importancia operativa. Ningún pilar es eliminatorio, pero los que pesan más al final son los últimos: la calidad de la atención manda sobre formulismos.

| Orden | Pilar | Pregunta clave | Peso en empatía |
|-------|-------|----------------|-----------------|
| 1 | **Nombre** | ¿Mencionó el nombre del cliente al menos una vez? | 15% |
| 2 | **Contexto** | ¿Demostró comprender el problema (parafrasear, reconocer)? | 25% |
| 3 | **Calidez** | ¿Tono amable/humano (o emojis adecuados)? | 25% |
| 4 | **Resolución** | ¿Se enfocó en ayudar, no en recitar un speech? | 35% |

**Mezcla final de empatía:** 70% pilares + 30% NPS (peso configurable por modo). Sesiones legacy sin `empathy_breakdown` caen al cálculo histórico (100% NPS).

### 1.4 Reglas de Ortografía (lenientes)

El modelo recibe instrucciones explícitas para **NO penalizar**:

- Tildes omitidas
- Mayúsculas iniciales en chat informal
- Abreviaciones comunes (`xq`, `q`, `tmb`, `pq`, `graxs`)
- Emojis
- Apertura de signos (`¿`, `¡`)
- Errores tipográficos menores que no afectan la comprensión

**Solo se cuenta como error** lo que **cambia el significado** o **impide entender** el mensaje. La mayoría de los chats bien escritos deben dar `0` errores.

---

## 2. Capa 2 — Perfil VEX (agregación)

Se calcula con `calculate_vex_profile(user_id)` y requiere **≥ 2 sesiones completadas**. El resultado se persiste en `vex_profiles`. El modo a aplicar es el del **batch más reciente** del usuario (legacy → Standard).

### 2.1 Métricas base agregadas

| Métrica | Cálculo |
|---------|---------|
| `avg_nps` | Promedio de `nps_score` por sesión |
| `correct_rate` | Sesiones con `response_correct = true` / total |
| `spelling_rate` | Σ `spelling_errors` / Σ `total_words_user` |
| `avg_wpm` | Promedio de `words_per_minute` |
| `avg_art` | Promedio del ART (sólo sesiones con ART > 0) |
| `improvement_trend` | Pendiente lineal del NPS por fecha, normalizada a 0–1 |
| `variety` | `unique_scenarios / max(total_scenarios × 0.4, 1)`, cap 1 |
| `empathy_pillar_rate` | Tasa de cumplimiento por pilar (Nombre / Contexto / Calidez / Resolución) |

### 2.2 Penalización ortográfica suavizada

```
spelling_penalty = min(spelling_rate × multiplicador_modo, 1)
```

| Modo | Multiplicador | Saturación |
|------|---------------|------------|
| Flexible | 35 | 2.85% errores |
| Standard | 25 | 4% errores |
| Exigente | 15 | 6.6% errores |

Antes era `× 10` fijo (saturaba al 10%). Con las reglas lenientes del modelo, en chats bien escritos `spelling_rate` será cercano a `0`.

### 2.3 Dimensiones (escala raw 0-100)

Cada dimensión tiene un **piso mínimo** definido por el modo, para que las primeras sesiones no aplasten el perfil cuando una métrica puntual sale baja. Las fórmulas siguientes son las del **modo Standard**.

#### Comunicación

```
Comunicación = 30 + (1 - spelling_penalty) × 30 + (avg_nps / 10) × 40
```

NPS pesa más que ortografía (40 vs 30). Piso 30.

#### Empatía

```
si pillar_count > 0:
    pillars = nombre×15 + contexto×25 + calidez×25 + resolucion×35
    Empatía = pillars × 0.7 + (avg_nps × 10) × 0.3
si no:
    Empatía = avg_nps × 10        # legacy
```

#### Resolución

```
Resolución = 25 + correct_rate × 50 + (avg_nps / 10) × 25
```

Piso 25. El correct_rate sigue siendo el factor dominante (50%) pero ya no es dictador único.

#### Velocidad — basada en ART (Average Response Time)

ART = tiempo medio en segundos entre el mensaje del cliente y la respuesta del asesor. **No** mide la duración total del chat ni penaliza al asesor por la lentitud del cliente.

```
avg_art ≤ 120s         → speed_art = 100      (excelente)
120s < avg_art ≤ 180s  → 100 → 80             (saludable)
180s < avg_art ≤ 300s  → 80 → 50              (aceptable)
300s < avg_art ≤ 600s  → 50 → 20              (lento)
avg_art > 600s         → 20                   (muy lento, cap)
avg_art = 0            → 65                   (sin datos, neutro)
```

Meta operativa con 5 chats simultáneos: **120-180 s** de ART.

```
speed_wpm = min(100, (avg_wpm / 25) × 100)    # 25 WPM = 100%
Velocidad = speed_art × 0.7 + speed_wpm × 0.3
```

ART pesa **70%** (capacidad de respuesta) y WPM **30%** (velocidad de tipeo).

#### Adaptabilidad

```
Adaptabilidad = 30 + improvement_trend × 35 + variety × 35
```

Piso 30. Premia mejorar con el tiempo y rotar entre escenarios.

#### Compliance

```
Compliance = 25 + correct_rate × 45 + (1 - spelling_penalty) × 30
```

### 2.4 Conversión a escala Sten (1-10)

```python
def to_sten(raw):
    sten = int(raw / 10) + (1 if (raw % 10) >= 4 else 0)
    return clamp(sten, 1, 10)
```

Redondeo "amigable": umbral 4 en lugar de 5. Un raw de 64 sube a Sten 7 en lugar de bajar a 6.

### 2.5 Predictive Index (compuesto ponderado)

Pesos del modo **Standard**:

| Dimensión | Peso |
|-----------|------|
| Empatía | 25% |
| Resolución | 22% |
| Comunicación | 18% |
| Velocidad | 15% |
| Adaptabilidad | 10% |
| Compliance | 10% |

```
PI (1-10)  = empatía×0.25 + resolución×0.22 + comunicación×0.18
           + velocidad×0.15 + adaptabilidad×0.10 + compliance×0.10
PI (%)     = PI × 10
```

**Cambio clave vs versión anterior:** empatía sube de 20% a 25% por la nueva rúbrica de 4 pilares. Resolución baja de 25% a 22%. Comunicación de 20% a 18%.

Los modos **Flexible** y **Exigente** redistribuyen estos pesos según el contexto operativo (ver `scoring_modes.py:DEFAULT_MODES`).

### 2.6 Categoría del perfil

Umbrales del modo **Standard** (más alcanzables que la versión inicial):

| Categoría | Condición |
|-----------|-----------|
| **Elite** | Overall ≥ 8.5 y todas las dimensiones ≥ 7 |
| **Alto** | Overall ≥ 6.5 y todas las dimensiones ≥ 4 |
| **Desarrollo** | Overall ≥ 4.5 |
| **Refuerzo** | Overall < 4.5 |

### 2.7 Recomendación

| Recomendación | Predictive Index (Standard) |
|---------------|----------------------------|
| **Recomendado** | ≥ 65% |
| **Observaciones** | 45 – 65% |
| **No Recomendado** | < 45% |

Antes era 70% / 50%. Bajamos 5 puntos para alinear con la curva más generosa. **Flexible** los relaja a 55% / 35%; **Exigente** los endurece a 75% / 55%.

---

## 3. ART — Average Response Time

Métrica principal de velocidad. ART = tiempo medio en segundos entre el último mensaje del cliente y la siguiente respuesta del asesor.

### 3.1 Cómo se calcula por sesión

En `end_session` se recorren los mensajes y por cada respuesta del asesor se mide el segundo entre el último mensaje del cliente y la réplica:

```python
gap = (msg_asesor.created_at - prev_cliente.created_at).total_seconds()
gap = max(0, min(gap, 600))   # cap 600s para evitar idle extremo
response_gaps.append(gap)

session.avg_response_time = mean(response_gaps)
```

### 3.2 Qué NO mide

- **No** mide la duración total del chat.
- **No** castiga al asesor por la lentitud del cliente.
- **No** acumula tiempo cuando el asesor habla primero o cuando hay varias respuestas seguidas del cliente (sólo cuenta el último gap antes de cada respuesta del asesor).

### 3.3 Por qué el cap de 600s

Si un cliente desaparece 20 minutos y vuelve, no es justo que ese gap arruine el ART del asesor. **600 s (10 min)** es el máximo razonable que podemos atribuir a "el asesor no respondió a tiempo".

### 3.4 Migración

Sesiones existentes tienen `avg_response_time = 0` (default DB) y reciben puntaje neutro de **65** en velocidad-ART (modo Standard). Las nuevas sesiones empiezan a poblar el campo automáticamente desde el primer cierre.

---

## 4. Resumen de cambios vs versión anterior

| Área | Antes | Ahora |
|------|-------|-------|
| Modelo IA | GPT-4o-mini (`max_tokens`) | GPT-5.4 mini (`max_completion_tokens`) |
| Penalización ortográfica | × 10 (10% errores → 0) | × 25 en Standard (4% errores → 0), configurable por modo |
| Reglas de ortografía | "errores claros" | Solo si afectan la comprensión |
| Empatía | 100% NPS | 70% pilares + 30% NPS |
| Pilares de empatía | — | Nombre / Contexto / Calidez / Resolución (15 / 25 / 25 / 35) |
| Velocidad | WPM + duración total | ART + WPM (70 / 30) |
| WPM benchmark | 30 WPM | 25 WPM |
| Pisos mínimos por dimensión | 0 | 25–30 según dimensión y modo |
| Conversión Sten | `round(raw/10)` | `int(raw/10) + (1 si resto ≥ 4)` |
| Peso empatía en PI | 20% | 25% |
| Categoría Elite | todas ≥ 8 | Overall ≥ 8.5 y todas ≥ 7 |
| Categoría Alto | overall ≥ 7 y todas ≥ 5 | Overall ≥ 6.5 y todas ≥ 4 |
| Recomendado | PI ≥ 70% | PI ≥ 65% (Standard) |
| Observaciones | 50–70% | 45–65% (Standard) |
| Modos | único (implícito) | 3 modos (Flexible / Standard / Exigente) + overrides editables |

---

## 5. Campos persistidos

### `training_sessions`

| Campo | Tipo | Origen |
|-------|------|--------|
| `nps_score` | int | IA |
| `response_correct` | bool | IA |
| `spelling_errors` | int | IA (lenient) |
| `words_per_minute` | float | calculado al cerrar |
| `avg_response_time` | float | calculado al cerrar (**nuevo**) |
| `ai_feedback` | json | IA — incluye `empathy_breakdown` desde esta versión |

### `training_scenarios`

| Campo | Tipo | Detalle |
|-------|------|---------|
| `scoring_mode` | string | `flexible` / `standard` / `exigente` / `null` (legacy) |

### `training_batches`

| Campo | Tipo | Detalle |
|-------|------|---------|
| `scoring_mode` | string | Snapshot del modo del escenario al iniciar el batch |

### `scoring_mode_overrides`

| Campo | Tipo | Detalle |
|-------|------|---------|
| `mode` | string (unique) | `flexible` / `standard` / `exigente` |
| `config_json` | text | JSON con las claves a override sobre los defaults |
| `updated_by` | int (FK users) | SuperAdmin que guardó el override |
| `updated_at` | datetime | — |

### `vex_profiles`

Sin cambios de esquema. Los valores persistidos siguen las nuevas fórmulas.

---

## 6. Migraciones

Ambas migraciones son **idempotentes** (usan `IF NOT EXISTS`) y se ejecutan automáticamente al arranque del contenedor (ver `Dockerfile`).

| Archivo | Cambios |
|---------|---------|
| `migrate_v5.py` | Añade `avg_response_time` (DOUBLE PRECISION DEFAULT 0) a `training_sessions`. |
| `migrate_v6.py` | Añade `scoring_mode` (VARCHAR 20) a `training_scenarios` y `training_batches`. Crea la tabla `scoring_mode_overrides`. |

Para correrlas manualmente en local:

```bash
python migrate_v5.py
python migrate_v6.py
```
