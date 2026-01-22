FROM python:3.11-slim

WORKDIR /app

COPY apps/tg-bot/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY apps/tg-bot/src/ /app/src/
COPY packages/db/src/ /app/packages/db/src/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src:/app/packages/db/src

CMD ["python", "-m", "src.bot_app"]
