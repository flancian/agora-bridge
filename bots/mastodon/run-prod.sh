#!/bin/bash
. venv/bin/activate
OUTPUT=/home/agora/agora/garden/agora@botsin.space
mkdir ${OUTPUT}
./agora-bot.py --config agora-bot.yaml --output=${OUTPUT} $@
