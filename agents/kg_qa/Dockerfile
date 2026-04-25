FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml config.yaml ./
COPY shared/ shared/
COPY agents/kg_qa/ agents/kg_qa/

RUN pip install --no-cache-dir .

EXPOSE 8003

CMD ["uvicorn", "agents.kg_qa.server:app", "--host", "0.0.0.0", "--port", "8003"]
