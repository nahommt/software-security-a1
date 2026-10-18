FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 10001 app
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.txt

COPY requirements-carreport.txt .
COPY wheels ./wheels
RUN pip install --no-cache-dir --no-index --no-deps --find-links ./wheels -r requirements-carreport.txt \
    && rm -rf ./wheels

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
