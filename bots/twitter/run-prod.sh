#!/bin/bash
. venv/bin/activate
OUTPUT=/home/agora/agora/stream/an_agora@twitter.com
mkdir -p ${OUTPUT}
./agora-bot.py --config agora-bot.yaml --output-dir=${OUTPUT} --max-age=99999999 $@ 
