FROM python:3.12-slim
RUN pip install --no-cache-dir pytest pytest-cov coverage 'Flask>=3,<4' \
    && useradd --create-home tester
WORKDIR /app
ENV PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1
USER tester
