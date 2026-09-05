FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY services ./services
RUN chmod +x /app/backend/entrypoint.sh

WORKDIR /app/backend
CMD ["./entrypoint.sh"]
