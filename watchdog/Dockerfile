FROM python:3.12-slim

# ping + fuseaux horaires
RUN apt-get update \
 && apt-get install -y --no-install-recommends iputils-ping tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY *.py ./

# Utilisateur sans privilèges
RUN useradd --create-home --shell /usr/sbin/nologin watchdog
USER watchdog

CMD ["python", "-u", "watchdog.py"]
