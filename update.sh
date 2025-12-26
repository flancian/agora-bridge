#!/bin/bash
# Updates the Agora Bridge and restarts services.

echo "Updating Agora Bridge..."
git pull

# Install python dependencies if they changed
echo "Syncing dependencies..."
uv pip install -e .

# Restart services
echo "Restarting services..."
systemctl --user restart agora-bridge.service
systemctl --user restart agora-bridge-api.service
systemctl --user restart agora-bullpen.service
systemctl --user restart agora-pusher.service

echo "Done."