FROM python:3.12-slim

RUN useradd --create-home --uid 10001 app
WORKDIR /srv

COPY requirements.txt .
COPY wheels ./wheels
RUN pip install --no-cache-dir --no-index --find-links ./wheels -r requirements.txt \
    && rm -rf ./wheels

COPY app ./app

USER app
CMD ["python", "-c", "print('report-service: not implemented yet')"]
