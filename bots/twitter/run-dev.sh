#!/bin/bash
. venv/bin/activate
OUTPUT=/home/agora/agora/stream/an_agora@twitter.com
mkdir -p ${OUTPUT}
./agora-bot.py --config agora-bot.yaml --dry-run --output-dir=${OUTPUT} $@ 
