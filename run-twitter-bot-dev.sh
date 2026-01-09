#!/bin/bash
# Development script for the Twitter bot.

echo "Starting Twitter bot in development mode..."
uv run python -m bots.twitter.agora-bot \
    --config="bots/twitter/agora-bot.yaml" \
    --tweets="bots/twitter/tweets.yaml" \
    --friends="bots/twitter/friends.yaml" \
    --output-dir="$HOME/agora/stream/twitter" \
    --verbose=True \
    --timeline \
    --follow
