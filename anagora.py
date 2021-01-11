#!/usr/bin/env python3

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
