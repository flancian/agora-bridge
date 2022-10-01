#!/bin/bash
# Moved to poetry.
# . venv/bin/activate
OUTPUT=/home/agora/agora/stream/
mkdir -p ${OUTPUT}
# 10080 = 7d in minutes
# 40320 = 4w in minutes
poetry run ./agora-bot.py --config agora-bot.yaml --timeline --output-dir=${OUTPUT} --max-age=40320 $@ 
