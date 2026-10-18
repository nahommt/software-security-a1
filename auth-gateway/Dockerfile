FROM python:3.12-slim

RUN useradd --create-home --uid 10001 app
WORKDIR /srv

COPY requirements.txt .
COPY app ./app

USER app
CMD ["python", "-c", "print('auth-gateway: not implemented yet')"]
