#!/bin/bash
. venv/bin/activate
OUTPUT=/home/agora/agora/stream/
mkdir -p ${OUTPUT}
./agora-bot.py --config agora-bot.yaml --output-dir=${OUTPUT} --max-age=604800 $@ 
