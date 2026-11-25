FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FLASK_ENV=production FLASK_APP=run.py
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
# non-root user; /data holds the encrypted prescription files (mounted as a volume)
RUN useradd -m -u 10001 appuser && mkdir -p /data/prescriptions && chown -R appuser /app /data
USER appuser
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/v1/health', timeout=4)" || exit 1
CMD ["gunicorn", "-b", "0.0.0.0:5000", "-w", "3", "--timeout", "60", "--access-logfile", "-", "run:app"]
