#!/bin/bash
# Trying to move to [[poetry]] across the board.
# . venv/bin/activate
OUTPUT=/home/flancian/agora/stream/agora@botsin.space
mkdir ${OUTPUT}
poetry run ./agora-bot.py --config agora-bot.yaml --catch-up --dry-run --output=${OUTPUT} $@
