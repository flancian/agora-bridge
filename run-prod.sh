#!/bin/bash
# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

echo "If this doesn't work, install poetry and run 'poetry install' as per README.md first."
# This shouldn't be needed but it is when running as a systemd service for some reason.
export PATH=$HOME/.local/bin:${PATH}

# Clean up lock files.
./clean.sh

# Try to push as well as pull to update social media activity upstream if we have access :)
./push.sh &

# Pull for the greater good! :)
poetry run ./pull.py --config ~/agora/sources.yaml --output-dir ~/agora --reset True
