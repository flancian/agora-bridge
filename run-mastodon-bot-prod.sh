#!/bin/bash
# Production script for the Mastodon bot.

# Ensure we can find uv if it's installed in the user's local bin
export PATH="$HOME/.local/bin:$PATH"

echo "Starting Mastodon bot in production mode..."
uv run python -m bots.mastodon.agora-bot \
    --config="bots/mastodon/agora-bot.yaml" \
    --output-dir="$HOME/agora/stream/mastodon" \
    --catch-up
