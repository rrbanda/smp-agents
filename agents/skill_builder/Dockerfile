FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml config.yaml ./
COPY shared/ shared/
COPY agents/skill_builder/ agents/skill_builder/

RUN pip install --no-cache-dir .

EXPOSE 8005

CMD ["uvicorn", "agents.skill_builder.server:app", "--host", "0.0.0.0", "--port", "8005"]
