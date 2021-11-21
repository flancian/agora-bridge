#!/bin/bash
. venv/bin/activate
./agora-bot.py --config agora-bot.yaml --dry-run --max-age=60000 --output-dir=/home/flancian/agora/garden/an_agora $@ 
