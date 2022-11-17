#!/bin/bash
# Will migrate to poetry.
# . venv/bin/activate
OUTPUT=/home/agora/agora/stream/agora@botsin.space
mkdir ${OUTPUT}
# This shouldn't be needed but it is when running something based on Poetry as a systemd service for some reason.
export PATH=$HOME/.local/bin:${PATH}
poetry run ./agora-bot.py --config agora-bot.yaml --output=${OUTPUT} --catch-up $@
