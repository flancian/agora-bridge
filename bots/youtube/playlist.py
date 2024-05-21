#!/usr/bin/env python3
# Copyright 2022 Google LLC
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

import argparse

parser = argparse.ArgumentParser()
parser.add_argument('playlist', nargs='+', help='Playlist to dump.')
args = parser.parse_args()

def dump(playlist):
    URL_BASE="https://www.youtube.com/playlist?list="
    PLAYLIST=args.playlist[0]
    from pytube import Playlist
    p = Playlist(URL_BASE + PLAYLIST)
    print(f"- a playlist.\n  - #go {URL_BASE}{PLAYLIST}")
    for idx, video in enumerate(p):
        print(f"  - #{idx} {video}?list={PLAYLIST}")

if __name__ == '__main__':
    dump(args.playlist)
