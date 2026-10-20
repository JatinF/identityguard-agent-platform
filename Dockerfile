FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY datasets ./datasets
ENV IG_DATA_DIR=/app/datasets
ENV IG_STATE_DIR=/data
ENV MODEL_PROVIDER=mock
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["uvicorn", "identityguard.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
