FROM python:3.12.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY server/requirements.txt /app/server/requirements.txt
RUN --mount=type=secret,id=pip_ca \
    if [ -f /run/secrets/pip_ca ]; then export PIP_CERT=/run/secrets/pip_ca; fi; \
    pip install --no-cache-dir -r server/requirements.txt \
    && useradd --create-home --uid 10001 kral \
    && mkdir /data && chown kral:kral /data && chmod 700 /data
COPY --chown=kral:kral server /app/server
USER 10001:10001
ENV KRAL_BIND=0.0.0.0 PORT=8080 OMEGA_DATA_DB=/data/kral.sqlite3 OMEGA_NONCE_DB=/data/kral-nonces.sqlite3
EXPOSE 8080
# Mount a persistent private volume at /data; terminate HTTPS at the trusted proxy.
CMD ["python", "-m", "server.gateway"]
