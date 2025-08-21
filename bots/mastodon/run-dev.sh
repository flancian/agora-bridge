#!/bin/bash
# Trying to move to [[poetry]] across the board.
# . venv/bin/activate
OUTPUT=/home/flancian/agora/stream/
mkdir ${OUTPUT}
uv run ./agora-bot.py --config agora-bot.yaml --catch-up --output=${OUTPUT} $@
