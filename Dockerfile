FROM python:3.11-slim

WORKDIR /app

# Dependencias de sistema:
# - libpango/libcairo/libgdk-pixbuf: WeasyPrint (PDF nativo de reportes Iterum)
# - libffi: dependencia transitiva de WeasyPrint
# - shared-mime-info: deteccion de mime types en WeasyPrint
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    shared-mime-info \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

# On start: copy images to persistent disk if empty, then migrate, then run
CMD ["sh", "-c", "\
  if [ -d /persistent ] && [ ! -f /persistent/.initialized ]; then \
    echo 'Copying images to persistent disk...' && \
    cp -r /app/static/imagenes/* /persistent/ 2>/dev/null; \
    cp -r /app/iXpert/imagenes/* /persistent/ 2>/dev/null; \
    mkdir -p /persistent/nucleo && \
    cp -r /app/iXpert/imagenes/nucleo/* /persistent/nucleo/ 2>/dev/null; \
    touch /persistent/.initialized && \
    echo 'Images copied to persistent disk'; \
  fi && \
  python migrate_pre.py && \
  python migrate.py && \
  python migrate_v2.py && \
  python migrate_v5.py && \
  python migrate_v6.py && \
  python migrate_v7.py && \
  python migrate_v8.py && \
  python migrate_v9.py && \
  python migrate_v10.py && \
  python migrate_v11.py && \
  python migrate_v12.py && \
  python migrate_iterum.py && \
  python migrate_iterum_retire_legacy.py && \
  python migrate_iterum_normalize_cells.py && \
  python update_keywords.py && \
  gunicorn --bind 0.0.0.0:10000 --timeout 120 app:app"]
