#!/bin/bash
. venv/bin/activate
OUTPUT=/home/agora/agora/stream/agora@botsin.space
mkdir ${OUTPUT}
./agora-bot.py --config agora-bot.yaml --output=${OUTPUT} --catch-up $@
