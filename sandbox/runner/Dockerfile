
FROM python:3.12-slim

WORKDIR /app

# Installer les outils nécessaires aux tests
RUN pip install --no-cache-dir pytest pytest-cov coverage

# Créer un utilisateur non privilégié
RUN useradd --create-home tester

# Préparer le dossier des résultats
RUN mkdir -p /tmp/test-results \
    && chown -R tester:tester /tmp/test-results

# Configurer Python et Coverage
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app
ENV COVERAGE_FILE=/tmp/test-results/.coverage

# Utiliser un utilisateur sans privilèges
USER tester

# Exécuter les tests et produire le rapport de couverture
CMD ["python", "-m", "pytest", "/app/tests", "-v", "-p", "no:cacheprovider", "--cov=shop.checkout", "--cov-branch", "--cov-report=json:/tmp/test-results/coverage_after.json", "--cov-report=term-missing"]
