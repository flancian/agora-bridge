#!/bin/bash
# Trying to move to [[poetry]] across the board.
# . venv/bin/activate
OUTPUT=$HOME/agora/stream/
mkdir -p ${OUTPUT}
# Install poetry with pipx install poetry or similar if you don't have it.
~/.local/bin/poetry run ./agora-bot.py --config agora-bot.yaml --output=${OUTPUT} --write $@
