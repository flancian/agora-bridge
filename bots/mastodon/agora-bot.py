#!/usr/bin/env python3
# Copyright 2021 Google LLC
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

# an [[agora bridge]], that is, a utility that takes a .yaml file describing a set of [[personal knowledge graphs]] or [[digital gardens]] and pulls them to be consumed by other bridges or an [[agora server]]. [[flancian]]

import argparse
import glob
import logging
import os

from . import config
from mastodon import Mastodon

parser = argparse.ArgumentParser(description='Agora Bot for Mastodon (ActivityPub).')
parser.add_argument('--config', dest='config', type=argparse.FileType('r'), required=True, help='The path to agora-bot.yaml, see agora-bot.yaml.example.')
# parser.add_argument('--output-dir', dest='output_dir', type=dir_path, required=True, help='The path to a directory where data will be dumped as needed.')
parser.add_argument('--verbose', dest='verbose', type=bool, default=False, help='Whether to log more information.')
args = parser.parse_args()

logging.basicConfig()
L = logging.getLogger('agora-bot')
if args.verbose:
    L.setLevel(logging.DEBUG)
else:
    L.setLevel(logging.INFO)

def main():
    try:
        config = yaml.safe_load(args.config)
    except yaml.YAMLError as e:
        L.error(e)

    # Set up Mastodon
    mastodon = Mastodon(
	access_token = config['access_token'],
	api_base_url = config['api_base_url'],
    )

    print(config)
    print("items:"
    for item in config:
	print(item)

    mastodon.status_post("[[agora bot]] v0.9 initializing, please wait.")

if __name__ == "__main__":
    main()
