#!/bin/bash
# Moved to poetry.
# . venv/bin/activate
OUTPUT=/home/agora/agora/stream/
mkdir -p ${OUTPUT}
# This shouldn't be needed but it is when running as a systemd service for some reason.
export PATH=$HOME/.local/bin:${PATH}
# 10080 = 7d in minutes
# 40320 = 4w in minutes
poetry run ./agora-bot.py --config agora-bot.yaml --timeline --output-dir=${OUTPUT} --max-age=40320 $@ 
