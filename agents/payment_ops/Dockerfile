FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml config.yaml ./
COPY shared/ shared/
COPY agents/payment_ops/ agents/payment_ops/

RUN pip install --no-cache-dir .

EXPOSE 8006

CMD ["uvicorn", "agents.payment_ops.server:app", "--host", "0.0.0.0", "--port", "8006"]
