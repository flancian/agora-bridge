#!/bin/bash
. venv/bin/activate
./agora-bot.py --config agora-bot.yaml --dry-run $@
