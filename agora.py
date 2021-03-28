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
import os
import yaml


def dir_path(string):
    if os.path.isdir(string):
        return string
    else:
        raise NotADirectoryError(string)

parser = argparse.ArgumentParser(description='Agora Bridge')
parser.add_argument('--config', dest='config', type=argparse.FileType('r'), required=True, help='The path to a YAML file describing the digital gardens to consume.')
parser.add_argument('--output-dir', dest='output_dir', type=dir_path, required=True, help='The path to a directory where the digital gardens will be stored (one subdirectory per user).')
args = parser.parse_args()

def main():
    try:
        config = yaml.safe_load(args.config)
        breakpoint()
        print(config)
    except yaml.YAMLError as e:
        print(e)
        print('lol')


if __name__ == "__main__":
    main()
