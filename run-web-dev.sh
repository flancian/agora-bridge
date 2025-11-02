#!/bin/bash
# Development script for the Agora Bridge web application.

export FLASK_APP=app/main.py
export FLASK_ENV="development"

# Use uv to run the Flask development server.
# The --host=0.0.0.0 flag makes it accessible from the network.
echo "Starting Agora Bridge web server..."
uv run python -m flask --debug run --host=0.0.0.0 --port=5016
