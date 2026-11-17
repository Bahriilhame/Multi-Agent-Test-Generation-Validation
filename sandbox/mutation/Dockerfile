FROM python:3.12-slim

WORKDIR /workspace

RUN pip install --no-cache-dir pytest pytest-cov coverage mutmut

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/workspace/src

CMD ["mutmut", "run"]
