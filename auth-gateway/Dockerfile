FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 10001 app \
    && mkdir /data \
    && chown app:app /data
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.txt

COPY app ./app

FROM base AS test

COPY requirements-dev.txt .
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements-dev.txt
COPY tests ./tests

USER app
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]

FROM base AS runtime

USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
