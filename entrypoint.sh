#!/bin/bash
# [[agora bridge]] container entrypoint.
#
# Part of the [[Agora of Flancia]] — an open knowledge commons.
# https://anagora.org/agora-bridge
# For a supported way to run an Agora on containers, please refer to [[agora recipe]] for [[coop cloud]]: https://anagora.org/agora-recipe

# If running in a live git repo with network, attempt pull
git pull 2>/dev/null || true

# If running alongside an Agora directory, clean up any stale git lock files
if [ -d "${AGORA_PATH:-$HOME/agora}" ]; then
    (cd "${AGORA_PATH:-$HOME/agora}" && find . -name 'index.lock' -exec rm -f {} \;) 2>/dev/null || true
fi

export FLASK_APP=api
export FLASK_ENV="${FLASK_ENV:-production}"
export PORT="${PORT:-5018}"
export GUNICORN_WORKERS="${GUNICORN_WORKERS:-4}"

if [ "${FLASK_ENV}" = "development" ]; then
    exec uv run flask run -h 0.0.0.0 -p "${PORT}"
else
    exec uv run gunicorn -w "${GUNICORN_WORKERS}" -b "0.0.0.0:${PORT}" "api:create_app()"
fi

