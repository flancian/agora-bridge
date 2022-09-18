#!/bin/bash
. venv/bin/activate
OUTPUT=/home/agora/agora/stream/
mkdir -p ${OUTPUT}
# 10080 = 7d in minutes
./agora-bot.py --config agora-bot.yaml --output-dir=${OUTPUT} --max-age=10080 $@ 
