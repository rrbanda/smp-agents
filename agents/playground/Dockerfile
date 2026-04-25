FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml config.yaml ./
COPY shared/ shared/
COPY agents/playground/ agents/playground/

RUN pip install --no-cache-dir .

EXPOSE 8004

CMD ["uvicorn", "agents.playground.server:app", "--host", "0.0.0.0", "--port", "8004"]
