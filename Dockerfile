FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
COPY pyproject.toml README.md requirements.lock ./
COPY atlas ./atlas
COPY scripts ./scripts
COPY models ./models
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home atlas
COPY data ./data
RUN mkdir -p /app/runtime && chown -R atlas:atlas /app/runtime
USER atlas
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import os,urllib.request;urllib.request.urlopen('http://localhost:'+os.environ.get('PORT','8000')+'/health',timeout=4)"
CMD ["sh", "-c", "python -m uvicorn atlas.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
