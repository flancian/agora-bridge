#!/bin="bash"
# Production script for the Bluesky bot.

# Ensure we can find uv if it's installed in the user's local bin
export PATH="$HOME/.local/bin:$PATH"

echo "Starting Bluesky bot in production mode..."
uv run python -m bots.bluesky.agora-bot \
    --config="bots/bluesky/agora-bot.yaml" \
    --output-dir="$HOME/agora/stream/bluesky" \
    --write


