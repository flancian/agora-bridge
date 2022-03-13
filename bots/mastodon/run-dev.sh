#!/bin/bash
. venv/bin/activate
OUTPUT=/home/flancian/agora/stream/agora@botsin.space
mkdir ${OUTPUT}
./agora-bot.py --config agora-bot.yaml --catch-up --dry-run --output=${OUTPUT} $@
