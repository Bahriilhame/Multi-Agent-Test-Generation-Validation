
FROM python:3.12-slim

WORKDIR /app

# Installer uniquement les dépendances nécessaires aux tests
RUN pip install --no-cache-dir pytest pytest-cov coverage

# Créer un utilisateur non privilégié
RUN useradd --create-home tester

# Préparer les dossiers de travail
RUN mkdir -p /app/shop /app/tests /tmp/test-results \
    && chown -R tester:tester /app /tmp/test-results

USER tester

# Lancer pytest avec le rapport de couverture
CMD ["python", "-m", "pytest", "/app/tests", "-v", "--cov=shop.checkout", "--cov-report=json:/tmp/test-results/coverage_after.json", "--cov-report=term-missing"]
