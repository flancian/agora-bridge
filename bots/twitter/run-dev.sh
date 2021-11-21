#!/bin/bash
. venv/bin/activate
OUTPUT=/home/agora/agora/garden/an_agora
mkdir -p ${OUTPUT}
./agora-bot.py --config agora-bot.yaml --dry-run --output-dir=${OUTPUT} $@ 
