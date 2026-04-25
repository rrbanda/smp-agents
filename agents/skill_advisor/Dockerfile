FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml config.yaml ./
COPY shared/ shared/
COPY agents/skill_advisor/ agents/skill_advisor/

RUN pip install --no-cache-dir .

EXPOSE 8001

CMD ["uvicorn", "agents.skill_advisor.server:app", "--host", "0.0.0.0", "--port", "8001"]
