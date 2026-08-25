FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git xmlsec1 libxml2 libxmlsec1-openssl libssl-dev gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/metadata
EXPOSE 8010
CMD ["gunicorn", "--bind", "0.0.0.0:8010", "--workers", "2", "config.wsgi:application"]
