#!/bin/bash
# Development script for the Bluesky bot.

echo "Starting Bluesky bot in development mode..."
uv run python -m bots.bluesky.agora-bot \
    --config="bots/bluesky/agora-bot.yaml" \
    --output-dir="$HOME/agora/stream/bluesky" \
    --verbose=True \
    --write