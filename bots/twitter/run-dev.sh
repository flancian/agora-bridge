#!/bin/bash
. venv/bin/activate
OUTPUT=/home/agora/agora/stream/
mkdir -p ${OUTPUT}
./agora-bot.py --config agora-bot.yaml --dry-run --new-api --output-dir=${OUTPUT} $@ 
