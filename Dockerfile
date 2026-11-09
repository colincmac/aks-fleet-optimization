FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --create-home --uid 10001 advisor
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
USER advisor
ENTRYPOINT ["aks-fleet-advisor"]
CMD ["--help"]
