FROM python:3.11-slim

WORKDIR /app

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
  python migrate.py && \
  gunicorn --bind 0.0.0.0:10000 --timeout 120 app:app"]
