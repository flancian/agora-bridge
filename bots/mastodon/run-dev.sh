#!/bin/bash
. venv/bin/activate
OUTPUT=/home/flancian/agora/garden/agora@botsin.space
mkdir ${OUTPUT}
./agora-bot.py --config agora-bot.yaml --dry-run --output=${OUTPUT} $@
