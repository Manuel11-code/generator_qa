# ============================================
# STAGE 1: builder
# ============================================
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ============================================
# STAGE 2: imagen final
# ============================================
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

COPY . .

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Crear usuario y darle permisos sobre /app ANTES de cambiar de usuario
RUN useradd --create-home appuser \
    && mkdir -p /app/staticfiles \
    && chown -R appuser:appuser /app

USER appuser

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "qa_generator.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]