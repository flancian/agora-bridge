#!/bin/bash
# Development script for the Bullpen (Bull Herder).

# Set the path to your Agora Garden root if different
export AGORA_ROOT="${AGORA_ROOT:-$HOME/agora/garden}"

# Check for bull binary
if ! command -v bull &> /dev/null; then
    if [ -f "$HOME/go/bin/bull" ]; then
        # It's in the default Go bin location, add to PATH for this session just in case
        export PATH="$HOME/go/bin:$PATH"
    else
        echo "Error: 'bull' binary not found in PATH or ~/go/bin/."
        echo "Please run 'agora-bridge/bullpen/setup_bull.sh' to install it."
        exit 1
    fi
fi

echo "Starting Bullpen on port 5019..."
echo "Serving gardens from: $AGORA_ROOT"

# Use uv to run the Flask app directly
uv run python3 bullpen/bullpen.py
