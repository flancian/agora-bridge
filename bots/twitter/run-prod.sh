#!/bin/bash
# Moved to poetry.
# . venv/bin/activate
OUTPUT=/home/agora/agora/stream/
mkdir -p ${OUTPUT}
# 10080 = 7d in minutes
poetry run ./agora-bot.py --config agora-bot.yaml --output-dir=${OUTPUT} --max-age=10080 $@ 
