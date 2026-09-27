# [[agora bridge]]
#
# Part of the [[Agora of Flancia]] — an open knowledge commons.
# https://anagora.org/agora-bridge
#
# Connects the Agora to the fediverse and external streams.
# Runs alongside [[agora server]] (which renders nodes and the graph).
#
# In 2023, this started as a Debian + Poetry container for [[coop cloud]] (based on Docker Swarm).
# In 2026, we modernized it to Python 3.12 + [[uv]] for [[flan.agor.ai]] and the [[agora recipe]]:
# See https://anagora.org/agora-recipe for more.
#
# To build with [[podman]] or [[docker]]:
#
#   $ podman build -t agora-bridge .
#
# To drop into a debugging shell in the container:
#
#   $ podman run -it --entrypoint /bin/bash agora-bridge
#
# If you are running rootless, check that you can write to 'agora' in the container:
#
#   $ podman unshare chgrp -R 1000 agora
#
# To run interactively on port 5018, mounting your Agora root:
#
#   $ podman run -it -p 5018:5018 -v ${HOME}/agora:/home/agora/agora:Z -u agora agora-bridge
#
# Or run the full stack with [[podman-compose]] / [[docker compose]] from [[agora]]:
#
#   $ podman-compose up
#
# Enjoy! For the benefit of all beings.

FROM python:3.12-slim

LABEL maintainer="Flancian <0@flancia.org>"
LABEL org.opencontainers.image.source="https://github.com/flancian/agora-bridge"
LABEL org.opencontainers.image.description="Agora Bridge: federating the knowledge commons"

# Install system dependencies (git is required for pulling gardens and proof-of-work checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv from official image (fast, reproducible Python tooling)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# We run as the agora user (UID 1000)
RUN groupadd -r agora -g 1000 && useradd -u 1000 -r -g agora -s /bin/bash -c "Agora" agora \
    && mkdir -p /home/agora/agora /home/agora/agora-bridge \
    && chown -R agora:agora /home/agora

WORKDIR /home/agora/agora-bridge
USER agora
ENV PATH="/home/agora/.local/bin:$PATH"

# Install Python dependencies first for caching layers
COPY --chown=agora:agora pyproject.toml README.md ./
RUN uv sync --no-install-project

# Copy application code from local context
COPY --chown=agora:agora . .
RUN uv sync

EXPOSE 5018
ENV FLASK_APP=api
ENV FLASK_ENV=production
ENV AGORA_PATH=/home/agora/agora

# Default to running the bridge API via gunicorn
CMD ["uv", "run", "gunicorn", "-w", "4", "-b", "0.0.0.0:5018", "api:create_app()"]
