FROM python:3.11-slim

WORKDIR /app

COPY apps/tg-bot/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY apps/tg-bot/src/ /app/src/
COPY apps/tg-bot/tests/ /app/apps/tg-bot/tests/
COPY apps/tg-bot/scripts/ /app/apps/tg-bot/scripts/
COPY apps/tg-bot/assets/ /app/apps/tg-bot/assets/
COPY packages/db/src/ /app/packages/db/src/
COPY packages/db/migrations/ /app/packages/db/migrations/
COPY packages/db/tests/ /app/packages/db/tests/
COPY packages/engine/ /app/packages/engine/
COPY packages/llm/ /app/packages/llm/
COPY content/ /app/content/

RUN python - <<'PY'
from pathlib import Path
root = Path('/app')
for path in root.rglob('*.py'):
    text = path.read_text(encoding='utf-8', errors='ignore')
    if '<<<<<<< ' in text or '\n=======\n' in text or '>>>>>>> ' in text:
        raise SystemExit(f'merge markers found in {path}')
print('merge-marker guard: OK')
PY

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app:/app/packages/db/src

CMD ["python", "-m", "src.bot_app"]
