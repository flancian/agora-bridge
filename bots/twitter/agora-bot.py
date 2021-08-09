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

# an [[agora bridge]], that is, a utility that takes a .yaml file describing a set of [[personal knowledge graphs]] or [[digital gardens]] and pulls them to be consumed by other bridges or an [[agora server]]. 
# -- [[flancian]]

# I am sad about all the passing about of 'api', in the next refactor I'll put everything in a class.
# I need to figure out if I should move to the streaming API somehow, but I sort of like the statelessness of this approach.
# Also this and the mastodon version need to be refactored so they share at least bot logic code.

import argparse
import base64
import cachetools.func
import glob
import logging
import os
import pickle
import random
import re
import requests
import time
import tweepy
import yaml

# Bot logic globals.
# Regexes are in order of precedence.
PUSH_RE = re.compile(r'\[\[push\]\](\s(\S+))?', re.IGNORECASE)
HELP_RE = re.compile(r'\[\[help\]\]\s(\S+)', re.IGNORECASE)
WIKILINK_RE = re.compile(r'\[\[(.*?)\]\]', re.IGNORECASE)
# Always matches.
DEFAULT_RE = re.compile(r'.', re.IGNORECASE)
# Unused for now.
P_HELP = 0.2

# argparse
parser = argparse.ArgumentParser(description='Agora Bot for Twitter.')
parser.add_argument('--config', dest='config', type=argparse.FileType('r'), required=True, help='The path to agora-bot.yaml, see agora-bot.yaml.example.')
parser.add_argument('--output-dir', dest='output_dir', type=argparse.FileType('r'), required=False, help='The path to a directory where data will be dumped as needed.')
parser.add_argument('--verbose', dest='verbose', type=bool, default=False, help='Whether to log more information.')
parser.add_argument('--dry-run', dest='dry_run', action="store_true", help='Whether to refrain from posting or making changes.')
args = parser.parse_args()

# logging
logging.basicConfig()
L = logging.getLogger('agora-bot')
if args.verbose:
    L.setLevel(logging.DEBUG)
else:
    L.setLevel(logging.INFO)

# and we're off!
def slugify(wikilink):
    # trying to keep it light here for simplicity, wdyt?
    # c.f. util.py in [[agora server]].
    slug = (
            wikilink.lower()
            .strip()
            .replace(' ', '-')
            )
    return slug

def get_path(api, tweet, n=10):
    """Gets the tweet and up to n ancestors in the thread, returns a list (path)."""
    # I'd like the whole thread, but the API seems to make it weirdly hard to get *children*? I must be doing something wrong.
    # TODO: implement.
    path = [tweet.id]
    while True:
        n-=1
        if n < 0:
            break
        parent = tweet.in_reply_to_status_id or 0
        path.append(parent)
        L.debug(f'{tweet.id} had parent {parent}')
        if parent == 0:
            break
        # go up
        tweet = api.statuses_lookup([parent])
    L.info(f'path to root: {path}')
    return path

# returns a bearer_header to attach to requests to the Twitter api v2 enpoints which are 
# not yet supported by tweepy 
def get_bearer_header():
   uri_token_endpoint = 'https://api.twitter.com/oauth2/token'
   key_secret = f"{CONSUMER_KEY}:{CONSUMER_SECRET}".encode('ascii')
   b64_encoded_key = base64.b64encode(key_secret)
   b64_encoded_key = b64_encoded_key.decode('ascii')

   auth_headers = {
       'Authorization': 'Basic {}'.format(b64_encoded_key),
       'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
       }

   auth_data = {
       'grant_type': 'client_credentials'
       }

   auth_resp = requests.post(uri_token_endpoint, headers=auth_headers, data=auth_data)
   bearer_token = auth_resp.json()['access_token']
   #bearer_token = 'AAAAAAAAAAAAAAAAAAAAAJkcMwEAAAAAASnCvzUgFZgpAukie8hA4F2CcGA%3DdD6P23cLDc3965QnWrwOoCRoWwFWQTSkUwGk4ocJY0ynb2lvj2'
   #consumer_key = 'Cls83HpCxkRqxNrwQ8LfQfP9g'

   bearer_header = {
       'Accept-Encoding': 'gzip',
       'Authorization': 'Bearer {}'.format(bearer_token),
       'oauth_consumer_key': CONSUMER_KEY
   }
   return bearer_header

# Returns the conversation_id of a tweet from v2 endpoint using the tweet id
def get_conversation_id(tweet):
   # from https://stackoverflow.com/questions/65398427/retrieving-specific-conversations-using-tweepy
   # needed as tweepy doesn't support the 2.0 API yet
   uri = 'https://api.twitter.com/2/tweets?'

   params = {
       'ids':tweet.id,
       'tweet.fields':'conversation_id'
   }
   
   bearer_header = get_bearer_header()
   resp = requests.get(uri, headers=bearer_header, params=params)
   try:
       return resp.json()['data'][0]['conversation_id']
   except json.decoder.JSONDecodeError:
       L.error(f"*** Couldn't decode JSON message in get_conversation.")
   return False

# Returns a conversation from the v2 enpoint  of type [<original_tweet_text>, <[replies]>]
def get_conversation(conversation_id):
    # from https://stackoverflow.com/questions/65398427/retrieving-specific-conversations-using-tweepy
    # needed as tweepy doesn't support the 2.0 API yet
   uri = 'https://api.twitter.com/2/tweets/search/recent?'

   params = {'query': f'conversation_id:{conversation_id}',
       'tweet.fields': 'in_reply_to_user_id', 
       'tweet.fields': 'conversation_id',
       'tweet.fields': 'author_id'
   }
   
   bearer_header = get_bearer_header()
   resp = requests.get(uri, headers=bearer_header, params=params)
   return resp.json()

def get_my_replies(api, tweet):
    conversation_id = get_conversation(tweet)
    replies = tweepy.Cursor(api.search, q=f'from:an_agora conversation_id:{conversation_id}', tweet_mode='extended').items
    L.debug(f'Got {len(replies)} replies: {replies}')

def get_replies(api, tweet, upto=100):
    # from https://stackoverflow.com/questions/52307443/how-to-get-the-replies-for-a-given-tweet-with-tweepy-and-python
    # but I hope this won't be needed?
    replies = tweepy.Cursor(api.search, q='to:{}'.format(tweet.id), since_id=tweet.id, tweet_mode='extended').items()
    while True:
        try:
            reply = replies.next()
            if not hasattr(reply, 'in_reply_to_status_id_str'):
                continue
            if reply.in_reply_to_status_id == tweet_id:
                L.debug("reply of tweet: {}".format(reply.full_text))
                L.debug("what do now? :)")

        except tweepy.RateLimitError as err:
            BACKOFF = min(BACKOFF * 2, MAX_BACKOFF)
            L.error(f"Twitter api rate limit reached, backing off {BACKOFF} seconds.".format(e))
            time.sleep(BACKOFF)
            continue

        except tweepy.TweepError as e:
            L.error("Tweepy error occured:{}".format(e))
            break

        except StopIteration:
            break

        except Exception as e:
            logger.error("Failed while fetching replies {}".format(e))
            break

def already_replied(api, tweet, upto=1):
    conversation = get_conversation(get_conversation_id(tweet))
    replies = []
    try:
        replies = conversation['data']
    except KeyError:
        L.info(f"### already_replied() -> reply pending")
        return False

    bot_replies = [reply for reply in replies if int(reply['author_id']) == BOT_USER_ID]
    if bot_replies:
        n = len(bot_replies)
        bot_replies_text = [reply['text'] for reply in bot_replies]
        L.debug(f"### \n### already_replied() -> bot already replied {n} time(s).")
        L.debug(f"### {tweet.full_text} bot_replies: {bot_replies_text}:")
        return n
    L.info(f"### already_replied() -> reply pending")
    return False

def reply_to_tweet(api, reply, tweet):
    # Twitter deduplication only *mostly* works so we can't depend on it.
    # Alternatively it might be better to implement state/persistent cursors, but this is easier.
    # TODO: move all of these to a class so we don't have to keep passing 'api' around.
    if already_replied(api, tweet):
        L.info("### not replying due to dedup logic")
        return False

    if args.dry_run:
        L.info("### not replying due to dry run")
        return False

    try:
        return api.update_status(
            status=reply,
            in_reply_to_status_id=tweet.id,
            auto_populate_reply_metadata=True
            )
    except tweepy.error.TweepError as e:
        # triggered by duplicates, for example.
        L.debug(f'### error while replying: {e}')
        return False

def handle_wikilink(api, tweet, match=None):
    L.info(f'## Handling wikilink: {match.group(0)}')
    L.debug(f'## Handling wikilink tweet: {tweet.full_text}, match: {match}')
    wikilinks = WIKILINK_RE.findall(tweet.full_text)
    lines = []
    for wikilink in wikilinks:
        slug = slugify(wikilink)
        lines.append(f'https://anagora.org/{slug}')

    response = '\n'.join(lines)
    L.debug(f'## Tweeting: "{response}" as response to tweet id {tweet.id}')
    if reply_to_tweet(api, response, tweet):
        L.info(f'## Replied to {tweet.id}')

def is_friend(api, user):
    followers = get_followers(api)
    if not followers:
        L.info('*** Could not friend check due likely to a quota issue, failing closed.')
        return False

    if any([u for u in followers if u.id == user.id]):
        L.info(f'#### @{user.screen_name} is a friend.')
        return True

    L.info(f'#### @{user.screen_name} is not yet a friend.')
    return False

def handle_push(api, tweet, match=None):
    L.info(f'## Handling [[push]]: {match.group(0)}')
    reply_to_tweet(api, 'If you ask an Agora to [[push]] and you are a [[friend]], the Agora will try to push for you.\n\nhttps://anagora.org/push\nhttps://anagora.org/friend', tweet)

    # Retweet if coming from a friend.
    if not is_friend(api, tweet.user):
        L.info(f'### Not retweeting: not a known friend.')
        return
    L.debug(f'### Retweeting: from a friend.')

    if args.dry_run:
        L.info(f'### Retweeting friend: {tweet.full_text} by @{tweet.user.screen_name}.')
        L.info(f'### Skipping retweet due to dry run.')
    else:
        L.info(f'### Retweeting friend: {tweet.full_text} by @{tweet.user.screen_name}.')
        try:
            api.retweet(tweet.id)
        except tweepy.error.TweepError as e:
            L.info(f'### Skipping duplicate retweet.')

    # Also volunteer other links?
    # handle_wikilink(api, tweet, match)

def handle_help(api, tweet, match=None):
    L.info(f'## Handling [[help]]: {tweet}, {match}')
    # This is probably borked -- reply_to_tweet now only replies once because of how we do deduping.
    # TODO: fix.
    reply_to_tweet(api, 'If you tell the Agora about a [[wikilink]], it will try to resolve it for you and mark your resource as relevant to the entity described between double square brackets. See https://anagora.org/agora-bot for more!', tweet, upto=2)
    reply_to_tweet(api, 'If you ask the Agora to [[push]], it will try to push for you.', tweet, upto=2)

def handle_default(api, tweet, match=None):
    L.info(f'## Handling default case, no clear intent present')
    # perhaps hand back a link if we have a node that seems relevant?
    # reply_to_tweet(api, 'Would you like help?', tweet)

@cachetools.func.ttl_cache(ttl=600)
def get_followers(api):
    L.info('*** get followers refreshing')
    try:
        followers = list(tweepy.Cursor(api.followers).items())
    except tweepy.error.RateLimitError:
        # This gets throttled a lot -- worth it not to hard here as it'll prevent the rest of the bot from running.
        followers = []
    return followers

def follow_followers(api):
    L.info("# Retrieving and following back followers")
    if args.dry_run:
        return False

    for follower in get_followers(): 
        if not follower.following:
            L.info(f"## Following {follower.name} back")
            follower.follow()

def process_mentions(api, since_id):
    # from https://realpython.com/twitter-bot-python-tweepy/
    L.info("## Retrieving mentions")
    new_since_id = since_id
    tweets = list(tweepy.Cursor(api.mentions_timeline, since_id=since_id, count=200, tweet_mode='extended').items())
    total = len(tweets)
    L.info(f'## Processing {total} mentions.')
    for n, tweet in enumerate(tweets):
        L.debug(f'*' * 80)
        L.info(f'## Processing tweet {n}/{total} https://twitter.com/twitter/status/{tweet.id} by @{tweet.user.screen_name}.')
        new_since_id = min(tweet.id, new_since_id)
        if not tweet.user.following and not args.dry_run:
            L.info(f'## Summoned by {{tweet.user}}, following {{tweet.user}} back', tweet.user)
            tweet.user.follow()
        # Process commands, in order of priority
        cmds = [
                (HELP_RE, handle_help),
                (PUSH_RE, handle_push),
                (WIKILINK_RE, handle_wikilink),
                (DEFAULT_RE, handle_default),
                ]
        for regexp, handler in cmds:
            match = regexp.search(tweet.full_text.lower())
            if match:
                handler(api, tweet, match)
                break
        L.debug(f'## Processed tweet: {tweet.id, tweet.full_text}')
        L.debug(f'*' * 80)
    return new_since_id

#class AgoraBot(tweepy.StreamListener):
#    """main class for [[agora bot]] for [[twitter]]."""
#    # this follows https://docs.tweepy.org/en/stable/streaming_how_to.html
#
#    def on_status(self, status):
#        L.info('received status: ', status.text)
#
#    def __init__(self, mastodon):
#        StreamListener.__init__(self)
#        self.mastodon = mastodon
#        L.info('[[agora bot]] started!')
#
#    def send_toot(self, msg, in_reply_to_id=None):
#        L.info('sending toot.')
#        status = self.mastodon.status_post(msg, in_reply_to_id=in_reply_to_id)
#
#    def handle_wikilink(self, status, match=None):
#        L.info(f'seen wikilink: {status}, {match}')
#        wikilinks = WIKILINK_RE.findall(status.content)
#        lines = []
#        for wikilink in wikilinks:
#            slug = slugify(wikilink)
#            lines.append(f'https://anagora.org/{slug}')
#        self.send_toot('\n'.join(lines), status)
#
#    def handle_push(self, status, match=None):
#        L.info(f'seen push: {status}, {match}')
#        self.send_toot('If you ask the Agora to [[push]], it will try to push for you.', status)
#
#    def handle_mention(self, status):
#        """Handle toots mentioning the [[agora bot]], which may contain commands"""
#        L.info('Got a mention!')
#        # Process commands, in order of priority
#        cmds = [(PUSH_RE, self.handle_push),
#                (WIKILINK_RE, self.handle_wikilink)]
#        for regexp, handler in cmds:
#            match = regexp.search(status.content)
#            if match:
#                handler(status, match)
#                return
#
#    def on_notification(self, notification):
#        self.last_read_notification = notification.id
#        if notification.type == 'mention':
#            self.handle_mention(notification.status)
#        else:
#            L.info(f'received unhandled notification type: {notification.type}')

def main():
    # Globals are a smell. This should all be in a class. See also bot logic globals up top.
    # API globals
    global BACKOFF 
    global BACKOFF_MAX
    global BOT_USER_ID 
    global CONSUMER_KEY
    global CONSUMER_SECRET
    global ACCESS_TOKEN
    global ACCESS_TOKEN_SECRET

    # Load config.
    try:
        config = yaml.safe_load(args.config)
    except yaml.YAMLError as e:
        L.fatal(e)

    # Set up Twitter API.
    # Global, again, is a smell, but yolo.
    BACKOFF = 60
    BACKOFF_MAX = 600
    BOT_USER_ID = config['bot_user_id']
    CONSUMER_KEY = config['consumer_key']
    CONSUMER_SECRET = config['consumer_secret']
    ACCESS_TOKEN = config['access_token']
    ACCESS_TOKEN_SECRET = config['access_token_secret']

    auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
    auth.set_access_token(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)

    api = tweepy.API(auth)
    since_id = 1
    L.info('[[agora bot]] starting.')
    # api.update_status('[[agora bot]] v0.9 for Twitter starting, please wait.')

    while True: 
        since_id = process_mentions(api, since_id)
        follow_followers(api)
        try: 
            pass
        except tweepy.error.TweepError as e:
            L.info(e)
            L.error("# Twitter api rate limit reached".format(e))
            BACKOFF = min(BACKOFF * 2, BACKOFF_MAX)
            L.info(f"# Backing off {BACKOFF} after exception.")
        L.info('# [[agora bot]] waiting.')
        time.sleep(BACKOFF)

if __name__ == "__main__":
    main()
