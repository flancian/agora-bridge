#!/bin/bash
# Development script for the Agora Bridge API and Dashboard.

export FLASK_APP="api"
export FLASK_ENV="development"

# Use uv to run the Flask development server.
# The --host=0.0.0.0 flag makes it accessible from the network.
echo "Starting Agora Bridge API server..."
uv run flask --debug run --host=0.0.0.0 --port=5018
