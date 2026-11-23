FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Keep application code read-only to the runtime account. The entrypoint starts
# as root only long enough to retain compatibility with existing data volumes,
# then drops privileges before Uvicorn starts.
RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --home-dir /nonexistent --shell /usr/sbin/nologin appuser

COPY . .
COPY entrypoint.sh /usr/local/bin/novaledger-entrypoint
RUN chmod 755 /usr/local/bin/novaledger-entrypoint \
    && mkdir -p /data/uploads \
    && chown -R appuser:appuser /data

ENTRYPOINT ["/usr/local/bin/novaledger-entrypoint"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
