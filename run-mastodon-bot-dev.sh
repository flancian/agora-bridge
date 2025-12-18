#!/bin/bash
# Development script for the Mastodon bot.

echo "Starting Mastodon bot in development mode..."
uv run python -m bots.mastodon.agora-bot \
    --config="bots/mastodon/agora-bot.yaml" \
    --output-dir="$HOME/agora/stream/mastodon" \
    --verbose=True \
    --catch-up