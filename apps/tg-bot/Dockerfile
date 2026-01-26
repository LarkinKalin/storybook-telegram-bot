FROM python:3.11-slim

WORKDIR /app

COPY apps/tg-bot/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY apps/tg-bot/src/ /app/src/
COPY apps/tg-bot/scripts/ /app/apps/tg-bot/scripts/
COPY packages/db/src/ /app/packages/db/src/
COPY packages/db/migrations/ /app/packages/db/migrations/
COPY packages/engine/ /app/packages/engine/
COPY packages/llm/ /app/packages/llm/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app:/app/packages/db/src

CMD ["python", "-m", "src.bot_app"]
