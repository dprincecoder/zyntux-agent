FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (if we ever need git/ca-certificates/etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY core ./core
COPY tg_bot ./tg_bot
COPY run_agent.py ./run_agent.py
COPY skill.md ./skill.md

EXPOSE 8000

CMD ["python", "run_agent.py"]

