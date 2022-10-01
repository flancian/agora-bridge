#!/bin/bash
# Moved to poetry.
# . venv/bin/activate
OUTPUT=/home/agora/agora/stream/
mkdir -p ${OUTPUT}
poetry run ./agora-bot.py --config agora-bot.yaml --dry-run --follow --new-api --output-dir=${OUTPUT} $@ 
