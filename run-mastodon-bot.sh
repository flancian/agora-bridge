#!/bin/bash
# Runs the Mastodon bot from the project root.

# Default config path
CONFIG_FILE="bots/mastodon/agora-bot.yaml"
OUTPUT_DIR="$HOME/agora/stream"

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Configuration file not found at $CONFIG_FILE"
    echo "Please copy bots/mastodon/agora-bot.yaml.example to $CONFIG_FILE and fill in your details."
    exit 1
fi

echo "Starting Mastodon bot..."
# Pass all script arguments (like --dry-run) to the python script
uv run python bots/mastodon/agora-bot.py --config "$CONFIG_FILE" --output-dir "$OUTPUT_DIR" "$@"
