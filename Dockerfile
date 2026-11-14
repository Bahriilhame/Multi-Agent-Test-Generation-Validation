
FROM python:3.11-slim

WORKDIR /workspace

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY tests/ ./tests/
COPY pyproject.toml .

ENV PYTHONPATH=/workspace/src
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["pytest", "--cov=shop", "--cov-branch", "--cov-report=term-missing"]
