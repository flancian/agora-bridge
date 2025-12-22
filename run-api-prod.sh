#!/bin/bash
# Production script for the Agora Bridge API.

export FLASK_APP="api"
export FLASK_ENV="production"

# If you want to have repo provisioning work, you need to define and export the following variables:
# export AGORA_FORGEJO_URL="https://git.anagora.org/api/v1"
# export AGORA_FORGEJO_TOKEN="forgejo_app_token_here"

# Use uv to run gunicorn.
echo "Starting Agora Bridge API server (Production)..."
uv run gunicorn -w 4 -b 0.0.0.0:5018 "api:create_app()"
