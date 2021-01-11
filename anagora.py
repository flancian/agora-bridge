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

import glob
import itertools
import os
import tweepy

import config
# config.py Must export:
# - CONSUMER_SECRET
# - ACCESS_TOKEN_SECRET
# - DEBUG
DEBUG = config.DEBUG
CONSUMER_SECRET = config.CONSUMER_SECRET
ACCESS_TOKEN_SECRET = config.ACCESS_TOKEN_SECRET

auth = tweepy.OAuthHandler("pagwyePax8TSOveeGYveRZ153", CONSUMER_SECRET)
auth.set_access_token("1200715929707044865-6ZpORfGjD8rs3qBgwOofpNYj3ztS9j", ACCESS_TOKEN_SECRET)

api = tweepy.API(auth)

def main():
    tweet="In Flancia there is an Agora: anagora.org."
    if DEBUG:
        print("Would tweet:", phrase)
    else:
        api.update_status(phrase)


if __name__ == "__main__":
    main()
