#!/bin/bash
# Production script for the Twitter bot.

echo "Starting Twitter bot in production mode..."
uv run python -m bots.twitter.agora-bot \
    --config="bots/twitter/agora-bot.yaml" \
    --tweets="bots/twitter/tweets.yaml" \
    --friends="bots/twitter/friends.yaml" \
    --output-dir="$HOME/agora/stream/twitter" \
    --timeline \
    --follow
