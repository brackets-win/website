ARG PYTHON_VERSION=3.11-slim-bullseye

# --- Stage 1: Build frontend ---
FROM node:20-slim AS frontend-build

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Django application ---
FROM python:${PYTHON_VERSION}

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y libpq-dev gcc

RUN mkdir -p /code

WORKDIR /code

RUN pip install poetry
COPY backend/pyproject.toml backend/poetry.lock /code/
RUN poetry config virtualenvs.create false
RUN poetry install --only main --no-root --no-interaction
COPY backend/ /code/

# Copy frontend build output into Django
COPY --from=frontend-build /frontend/dist/index.html /code/frontend_dist/index.html
COPY --from=frontend-build /frontend/dist/assets /code/frontend_dist/assets

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["bash", "run.sh"]
