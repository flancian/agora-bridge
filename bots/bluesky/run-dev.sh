#!/bin/bash
# Trying to move to [[poetry]] across the board.
# . venv/bin/activate
OUTPUT=$HOME/agora/stream/
mkdir -p ${OUTPUT}
poetry run ./agora-bot.py --config agora-bot.yaml --dry-run --output=${OUTPUT} $@
