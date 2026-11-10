FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# State (dedupe, exclusions, quiet-hours queue) lives on a volume so it
# survives redeploys.
ENV DATABASE_PATH=/data/app.db
VOLUME /data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
