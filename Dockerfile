FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/data/campusclaw.db \
    UPLOAD_DIR=/data/uploads

EXPOSE 8000
CMD ["python", "-m", "app"]
