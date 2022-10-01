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
import datetime
import glob
import io
import json
import logging
import os
import pickle
import random
import re
import requests
import subprocess
import time
import tweepy
import urllib
import yaml

# Bot logic globals.
# Regexes are in order of precedence.
OPT_IN_RE = re.compile(r'#(optin|agora)', re.IGNORECASE)
OPT_OUT_RE = re.compile(r'#(optout|noagora)', re.IGNORECASE)
PUSH_RE = re.compile(r'\[\[push\]\](\s(\S+))?', re.IGNORECASE)
HELP_RE = re.compile(r'\[\[help\]\]\s(\S+)', re.IGNORECASE)
WIKILINK_RE = re.compile(r'\[\[(.*?)\]\]', re.IGNORECASE)
HASHTAG_RE = re.compile(r'#(\w+)', re.IGNORECASE)
# Always matches.
DEFAULT_RE = re.compile(r'.', re.IGNORECASE)
# Unused for now.
P_HELP = 0.1
# Backoff after Twitter exceptions, of which we seem to get many.
BACKOFF = 15
BACKOFF_MAX = 600

# https://stackoverflow.com/questions/11415570/directory-path-types-with-argparse
class readable_dir(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        prospective_dir=values
        if not os.path.isdir(prospective_dir):
            raise argparse.ArgumentTypeError("readable_dir:{0} is not a valid path".format(prospective_dir))
        if os.access(prospective_dir, os.R_OK):
            setattr(namespace,self.dest,prospective_dir)
        else:
            raise argparse.ArgumentTypeError("readable_dir:{0} is not a readable dir".format(prospective_dir))

# argparse
parser = argparse.ArgumentParser(description='Agora Bot for Twitter.')
parser.add_argument('--config', dest='config', type=argparse.FileType('r'), required=True, help='The path to agora-bot.yaml, see agora-bot.yaml.example.')
parser.add_argument('--tweets', dest='tweets', type=argparse.FileType('r'), default='tweets.yaml', help='The path to a state (tweets/replies) yaml file, can be non-existent; we\'ll write there.')
# 2022-09-25: this might not actually be a good idea :) better to use sqlite3 and cut it with the yaml? we have Markdown writing for humans.
# TODO: add sqlite.
parser.add_argument('--friends', dest='friends', type=argparse.FileType('r'), default='friends.yaml', help='The path to a graph (friends) in a yaml file, can be non-existent; we\'ll write there if we can.')
parser.add_argument('--output-dir', dest='output_dir', action=readable_dir, required=False, help='The path to a directory where data will be dumped as needed. Subdirectories per-user will be created.')
parser.add_argument('--verbose', dest='verbose', type=bool, default=False, help='Whether to log more information.')
parser.add_argument('--timeline', dest='timeline', action="store_true", help='Whether to process the timeline of the bot (if not specified we will only process direct mentions.')
parser.add_argument('--follow', dest='follow', action="store_true", help='Whether to follow back (this burns Twitter API quota so it might be worth disabling at times).')
parser.add_argument('--max-age', dest='max_age', type=int, default=600, help='Threshold in age (minutes) beyond which we will not reply to tweets.')
parser.add_argument('--dry-run', dest='dry_run', action="store_true", help='Whether to refrain from posting or making changes.')
args = parser.parse_args()

# logging
logging.basicConfig()
L = logging.getLogger('agora-bot')
if args.verbose:
    L.setLevel(logging.DEBUG)
else:
    L.setLevel(logging.INFO)

def mkdir(string):
    if not os.path.isdir(string):
        print(f"Trying to create {string}.")
        output = subprocess.run(['mkdir', '-p', string], capture_output=True)
        if output.stderr:
            L.error(output.stderr)
    return os.path.abspath(string)

class AgoraBot():

    def __init__(self, config):

        # load extra state.
        # all this should be optional.
        try:
            self.tweets = yaml.safe_load(args.tweets)
        except yaml.YAMLError as e:
            L.exception("couldn't load tweets")
            self.tweets = {}
        try:
            self.friends = yaml.safe_load(args.friends)
        except yaml.YAMLError as e:
            L.exception("couldn't load friends")

        # Set up Twitter API.
        # Global, again, is a smell, but yolo.
        self.bot_user_id = config['bot_user_id']
        self.bot_username = config.get('bot_username', 'an_agora')
        self.bearer_token = config['bearer_token']
        self.consumer_key = config['consumer_key']
        self.consumer_secret = config['consumer_secret']
        self.access_token = config['access_token']
        self.access_token_secret = config['access_token_secret']
        self.since_id = config['since_id']

        auth = tweepy.OAuthHandler(self.consumer_key, self.consumer_secret)
        auth.set_access_token(self.access_token, self.access_token_secret)

        # give this another try?
        # api = tweepy.API(auth, wait_on_rate_limit=True)
        # Twitter v1 API
        self.api = tweepy.API(auth)
        # Twitter v2 API
        self.client = tweepy.Client(self.bearer_token, self.consumer_key, self.consumer_secret, self.access_token, self.access_token_secret)

    # Currently unused.
    def get_path(self, tweet, n=10):
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
            L.debug(f"{tweet.id} had parent {parent}")
            if parent == 0:
                break
            # go up
            # Untested after moving to API v2.
            tweet = self.client.get_tweet(parent).data
        L.info(f'path to root: {path}')
        return path

    # returns a bearer_header to attach to requests to the Twitter api v2 enpoints which are 
    # not yet supported by tweepy 
    def get_bearer_header(self):
        uri_token_endpoint = 'https://api.twitter.com/oauth2/token'
        key_secret = f"{self.consumer_key}:{self.consumer_secret}".encode('ascii')
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
            'oauth_consumer_key': self.consumer_key
        }
        return bearer_header

    # Returns the conversation_id of a tweet from v2 endpoint using the tweet id
    def get_conversation_id(self, tweet):
        # from https://stackoverflow.com/questions/65398427/retrieving-specific-conversations-using-tweepy
        # needed as tweepy doesn't support the 2.0 API yet
        uri = 'https://api.twitter.com/2/tweets?'

        params = {
            'ids': tweet.id,
            'tweet.fields':'conversation_id'
        }
        
        bearer_header = self.get_bearer_header()

        resp = requests.get(uri, headers=bearer_header, params=params)
        try:
            return resp.json()['data'][0]['conversation_id']
        except json.decoder.JSONDecodeError:
            L.error(f"*** Couldn't decode JSON message in get_conversation_id.")
        return False

    # Returns a conversation from the v2 enpoint  of type [<original_tweet_text>, <[replies]>]
    def get_conversation(self, conversation_id):
        # from https://stackoverflow.com/questions/65398427/retrieving-specific-conversations-using-tweepy
        # needed as tweepy doesn't support the 2.0 API yet
        uri = 'https://api.twitter.com/2/tweets/search/recent?'

        params = {'query': f'conversation_id:{conversation_id}',
            'tweet.fields': 'in_reply_to_user_id', 
            'tweet.fields': 'conversation_id',
            'tweet.fields': 'author_id'
        }
        
        bearer_header = self.get_bearer_header()
        resp = requests.get(uri, headers=bearer_header, params=params)
        try:
            return resp.json()
        except json.decoder.JSONDecodeError:
            L.error(f"*** Couldn't decode JSON message in get_conversation.")
            L.error(resp.text)

    def get_my_replies(self, tweet):
        L.debug("get_my_replies running")
        conversation_id = self.get_conversation_id(tweet)
        L.debug(f"conversation_id: {conversation_id}")
        uri = 'https://api.twitter.com/2/tweets/search/recent'
        params = {
            'query': f'conversation_id:{conversation_id} from:{self.bot_user_id}',
            'tweet.fields':'conversation_id'
        }
        bearer_header = self.get_bearer_header()

        resp = requests.get(uri, headers=bearer_header, params=params)
        L.debug(resp.text)
        # the fake tweet id we'll respond if we're not sure that we *haven't* responded yet.
        # deduplicating tweets is harder than I expected! in particular when any call might hit limits and fail, it seems.
        default = [{'id': 1}]
        try:
            return resp.json()['data']
        except json.decoder.JSONDecodeError:
            L.error(f"*** Couldn't decode JSON message in get_my_replies.")
            # hack hack
            return default
        except KeyError:
            L.error(f"*** KeyError in get_my_replies.")
            # hack hack
            L.info(f"*** get_my_replies got a KeyError (didn't find a reply?).")
            # this happens for https://twitter.com/flancian/status/1443695517800730624
            # doesn't find https://twitter.com/an_agora/status/1444756578238861321 for some reason
            # also for https://twitter.com/flancian/status/1443693643513085959
            # but they are old old, I think now that we only process newer tweets this can probably return []
            return []

        L.info(f"*** get_my_replies fell through.")
        return default

        # dead code below; this didn't work, perhaps conversation_id requires v2?
        # TODO: delete or move to API v2.
        replies = list(tweepy.Cursor(self.api.search, q=f'from:an_agora conversation_id:{conversation_id}', tweet_mode='extended').items())
        L.debug("replies: {replies}")
        return replies

    def get_replies(self, tweet, upto=100):
        # Dead code as of earlier than [[2022-09-25]]
        # from https://stackoverflow.com/questions/52307443/how-to-get-the-replies-for-a-given-tweet-with-tweepy-and-python
        # but I hope this won't be needed?
        replies = self.Paginator(self.client.search, q='to:{}'.format(tweet.id), since_id=tweet.id, tweet_mode='extended').items()
        while True:
            try:
                reply = replies.next()
                if not hasattr(reply, 'in_reply_to_status_id_str'):
                    continue
                if reply.in_reply_to_status_id == tweet.id:
                    L.debug("reply of tweet: {}".format(reply['text']))
                    L.debug("what do now? :)")

            except tweepy.RateLimitError as err:
                BACKOFF = min(BACKOFF * 2, MAX_BACKOFF)
                L.error(f"Twitter api rate limit reached, backing off {BACKOFF} seconds.".format(e))
                time.sleep(BACKOFF)
                continue

            except tweepy.errors.TweepyException as e:
                L.error("Tweepy error occured:{}".format(e))
                break

            except StopIteration:
                break

            except Exception as e:
                logger.error("Failed while fetching replies {}".format(e))
                break

    def already_replied(self, tweet, upto=1):

        if self.tweet_to_url(tweet) in self.tweets.keys():
            L.info(f"-> tweet already in handled list.")
            return True
        L.info(f"-> tweet not in handled list.")
        return False

        # dead code beyond here.

        try:
            bot_replies = self.get_my_replies(tweet)
            L.debug(f"-> bot replies: {bot_replies}.")
        except:
            L.exception(f"## already_replied failed call to get_my_replies!.")
            L.info(f"## failsafe: not replying.")
            return True

        if bot_replies:
            # add previous responses to the cache/"db"
            self.tweets[tweet_to_url(tweet)] = f"https://twitter.com/an_agora/status/{bot_replies[0]['id']}"
            with open(args.tweets.name, 'w') as OUT:
                yaml.dump(self.tweets, OUT)
            for reply in bot_replies:
                L.info(f"-> already replied!: https://twitter.com/twitter/status/{reply['id']}.")
            return True 
        return False

        # deader code beyond here.

        conversation = get_conversation(get_conversation_id(tweet))
        if not conversation:
            L.error(f"## already_replied() -> error retrieving conversation, aborting reply.")
            return True

        replies = []
        try:
            replies = conversation['data']
        except KeyError:
            # why was I defaulting this condition to false?
            L.info(f"## already_replied() -> reply pending")
            return False

        bot_replies = [reply for reply in replies if int(reply['author_id']) == self.bot_user_id]
        if bot_replies:
            n = len(bot_replies)
            bot_replies_text = [reply['text'] for reply in bot_replies]
            L.debug(f"## \n## already_replied() -> bot already replied {n} time(s).")
            L.debug(f"## {tweet.text} bot_replies: {bot_replies_text}:")
            return True

        L.info(f"## already_replied() -> reply pending")
        return False

    def tweet_to_url(self, tweet):
        try:
            return f"https://twitter.com/{self.get_username(tweet.author_id)}/status/{tweet.id}"
        except AttributeError:
            # Some tweets are essentially empty of metadata and the id doesn't resolve; weird.
            return False

    def write_tweet(self, tweet, node):

        L.debug(f"Maybe logging tweet if user has opted in.")
        if not args.output_dir:
            return False

        username = self.get_username(tweet.author_id)

        user_stream_dir = mkdir(os.path.join(args.output_dir, username + '@twitter.com'))
        user_stream_filename = os.path.join(user_stream_dir, node + '.md')

        if self.wants_writes(username):
            L.info(f"User {username} has opted in to writing, pushing (publishing) full tweet text to an Agora.")
            try:
                with open(user_stream_filename, 'a') as note:
                    # TODO: add timedate like Matrix, either move to Tweepy 4 to get some sense back or pipe through the creation date.
                    note.write(f"- [[{username}]] {self.tweet_to_url(tweet)}\n  - {tweet.text}\n")
            except:
                L.error("Couldn't log full tweet to note in user stream.")
                return
        else:
            L.info(f"User {username} has NOT opted in, skipping logging full tweet.")

    def log_tweet(self, tweet, node):
        if not args.output_dir:
            return False

        username = self.get_username(tweet.author_id)

        if ('/' in node):
            # for now, dump only to the last path fragment -- this yields the right behaviour in e.g. [[go/cat-tournament]]
            node = os.path.split(node)[-1]

        # dedup logic. we use the agora bot's stream as log as that's data under the control of the Agora (we only store a link).
        try:
            agora_stream_dir = mkdir(os.path.join(args.output_dir, self.bot_username + '@twitter.com'))
            agora_stream_filename = os.path.join(agora_stream_dir, node + '.md')

            with open(agora_stream_filename, 'r') as note:
                if self.tweet_to_url(tweet) in note.read():
                    L.info("Tweet already logged to note, skipping logging.")
                    return False
        except FileNotFoundError:
            pass

        L.info("Tweet will be logged to note.")
        # try to append the link to the tweet in the relevant node (in agora bot stream).
        try:
            with open(agora_stream_filename, 'a') as note:
                note.write(f"- [[{username}]] {self.tweet_to_url(tweet)}\n")
        except: 
            L.error("Couldn't log tweet to note in bot stream.")
            return

        # maybe write full tweet text in the user's own directory/repository (checks for opt in)
        self.write_tweet(tweet, node)

    def is_mentioned_in(self, username, node):
        if not args.output_dir:
            return False

        if ('/' in node):
            # for now, dump only to the last path fragment -- this yields the right behaviour in e.g. [[go/cat-tournament]]
            node = os.path.split(node)[-1]

        agora_stream_dir = mkdir(os.path.join(args.output_dir, self.bot_username + '@twitter.com'))
        filename = os.path.join(agora_stream_dir, node + '.md')
        L.info(f"Checking if {username} is mentioned in {node} meaning {filename}.")

        try:
            with open(filename, 'r') as note:
                if f'[[{username}]]' in note.read():
                    L.info(f"User {username} is mentioned in {node}.")
                    return True
                else:
                    L.info(f"User {username} not mentioned in {node}.")
                    return False
        except FileNotFoundError:
            return False

    def yaml_dump_tweets(self, tweets):
        with open(args.tweets.name, 'w') as out:
            yaml.dump(tweets, out)

    def yaml_dump_friends(self, friends):
        # This sounds worse than it is :)
        with open(args.friends.name, 'w') as out:
            yaml.dump(friends, out)

    def reply_to_tweet(self, tweet, reply):
        # Twitter deduplication only *mostly* works so we can't depend on it.
        # Alternatively it might be better to implement state/persistent cursors, but this is easier.
        # See ample warnings below. Hopefully it's happening really soon (tm) ;)
        L.info("-> in reply_to_tweet")
        if self.already_replied(tweet):
            L.info("-> not replying due to dedup logic")
            return False

        # if not self.is_friend(tweet.user):
        #     L.info("-> not replying because this user no longer follows us.")
        #     return False

        if args.dry_run:
            L.info("-> not replying due to dry run")
            return False

        try:
            res = self.client.create_tweet(
                text=reply,
                in_reply_to_tweet_id=tweet.id,
                )
            if res:
                # update a global and dump to disk -- really need to refactor this into a Bot class shared with Mastodon.
                # TODO: refactor. This is really needed -- will add a pointer to this in the Agora.
                L.debug(tweet.id, res)
                # self.tweets...
                self.tweets[self.tweet_to_url(tweet)] = self.tweet_to_url(res)
                # This actually writes to disk; this code is pretty bad, "update a global and then call write", what!
                # ...and this is the second time I think exactly that while dumpster diving here :)
                # I keep treating this codebase as throwaway, I should refactor and integrate with 1. [[moa]] or 2. [[mastodon]] codebase no later than [[2022-10]].
                self.yaml_dump_tweets(self.tweets)
            return res
        except tweepy.errors.TweepyException as e:
            # triggered by duplicates, for example.
            L.debug(f'! error while replying: {e}')
            return False

    def handle_wikilink(self, tweet, match=None):
        L.info(f"-> {self.tweet_to_url(tweet)}: Handling wikilinks, match: {match.group(0)}")
        L.debug(f"...in {tweet.text}")
        wikilinks = WIKILINK_RE.findall(tweet.text)

        # if tweet.retweeted:
        #     L.info(f'# Skipping retweet: {tweet.id}')
        #     return True

        lines = []
        for wikilink in wikilinks:
            path = urllib.parse.quote_plus(wikilink)
            lines.append(f'https://anagora.org/{path}')
            self.log_tweet(tweet, wikilink)

        response = '\n'.join(lines)
        L.debug(f"-> Replying '{response}' to tweet id {tweet.id}")

        if self.reply_to_tweet(tweet, response):
            L.info(f"# Replied to {tweet.id}")

    def wants_hashtags(self, user):
        # Allowlist to begin with.
        WANTS_HASHTAGS = ['codexeditor', 'ChrisAldrich']

        # Trying to infer opt in status from the Agora: does the node 'hashtags' contain mention of the user opting in?
        return user in WANTS_HASHTAGS or (
            self.is_mentioned_in(user, 'hashtags') and not self.is_mentioned_in(user, 'nohashtags')) or (
            self.is_mentioned_in(user, 'optin') and not self.is_mentioned_in(user, 'optout'))

    def wants_writes(self, user):
        # Allowlist to begin with.
        WANTS_WRITES = ['flancian']

        # Trying to infer opt in status from the Agora: does the node 'optin' contain mention of the user opting in?
        if user in WANTS_WRITES:
            return True
        if self.is_mentioned_in(user, 'optin') and not self.is_mentioned_in(user, 'optout'):
            return True
        if self.is_mentioned_in(user, 'opt in') and not self.is_mentioned_in(user, 'opt out'):
            return True
        return False

    def handle_hashtag(self, tweet, match=None):
        L.info(f"-> {self.tweet_to_url(tweet)}: Handling hashtags: {match.group(0)}")
        L.debug(f"...in {tweet.text}")
        hashtags = HASHTAG_RE.findall(tweet.text)
        username = self.get_username(tweet.author_id)
        # hashtag handling was disabled while we do [[opt in]], as people were surprised negatively by the Agora also responding to them by default.
        # now we support basic opt in, as of 2022-05-21 this is off by default.
        if not self.wants_hashtags(username):
            L.info(f"# User has not opted into hashtag handling yet: {username}")
            return False

        L.info(f"# Handling hashtags for opted-in user {username}")

        # unsure if we really want to skip this, in particular now that we're doing allowlisting?
        # if tweet.retweeted:
        #     L.info(f'# Skipping retweet: {tweet.id}')
        #     return True

        lines = []
        for hashtag in hashtags:
            path = urllib.parse.quote_plus(hashtag)
            lines.append(f'https://anagora.org/{path}')
            self.log_tweet(tweet, hashtag)

        response = '\n'.join(lines)
        L.debug(f"-> Replying '{response}' to tweet id {tweet.id}")
        L.info(f"-> Considering reply to {tweet.id}")
        if self.reply_to_tweet(tweet, response):
            L.info(f"# Replied to {tweet.id}")

    def is_friend(self, user):
        followers = self.get_followers()
        if not followers:
            L.info('*** Could not friend check due likely to a quota issue, failing OPEN.')
            return True

        L.info('*** Trying to save friends snapshot.')
        self.yaml_dump_friends(followers)

        if any([u for u in followers if u['id'] == user['id']]):
            L.info(f'## @{user} is a friend.')
            return True

        L.info(f'## @{user} is not yet a friend.')
        return False

    def handle_push(self, tweet, match=None):
        L.info(f'# Handling push: {match.group(0)}')
        self.log_tweet(tweet, 'push')
        self.reply_to_tweet(tweet, 'If you ask an Agora to push and you are a friend, the Agora will try to push for you.\n\nhttps://anagora.org/push\nhttps://anagora.org/friend')

        # Retweet if coming from a friend.
        # This should probably be closed down to 'is thought to be an [[agoran]]'.
        if not self.is_friend(tweet.author_id):
            L.info(f'## Not retweeting: not a known friend.')
            return
        L.debug(f'## Retweeting: from a friend.')

        if args.dry_run:
            L.info(f"## Retweeting friend: {tweet.text} by @{tweet.user}.")
            L.info(f'## Skipping retweet due to dry run.')
            return False
        else:
            L.info(f"## Retweeting friend: {tweet.text} by @{tweet.user}.")
            try:
                self.client.retweet(tweet.id)
                return True
            except tweepy.errors.TweepyException as e:
                L.info(f'## Skipping duplicate retweet.')
                return False

    # TODO: implement, as in actually store the opt in/opt out message in the Agora.
    def handle_opt_in(self, tweet, match=None):
        L.info(f'# Handling #optin: {match.group(0)}')

        if args.dry_run:
            L.info(f'# Skipping storing opt in due to dry run.')
            return False
        else:
            L.info(f'# This is where we try to opt in a user.')
            if self.log_tweet(tweet, 'hashtags'):
                self.reply_to_tweet(tweet, 'Opted you into #hashtag management, you can also #OptOut.')
            return True

    def handle_opt_out(self, tweet, match=None):
        L.info(f'# Handling #optout: {match.group(0)}')

        if args.dry_run:
            L.info(f'# Skipping storing opt out due to dry run.')
            return False
        else:
            L.info(f'# This is where we would opt out a user.')
            if self.log_tweet(tweet, 'nohashtags'):
                self.reply_to_tweet(tweet, 'Opted you out of #hashtag management and other advanced features by this Agora, you can also [[opt in]].')
            return True

    def handle_help(self, tweet, match=None):
        L.info(f'# Handling [[help]]: {tweet}, {match.group(0)}')
        # This is probably borked -- reply_to_tweet now only replies once because of how we do deduping.
        # TODO: fix.
        self.log_tweet(tweet, 'help')
        self.reply_to_tweet(tweet, 'If you tell the Agora about a [[wikilink]], it will try to resolve it for you and mark your resource as relevant to the entity described between double square brackets. See https://anagora.org/agora-bot for more!', upto=2)

    def handle_default(self, tweet, match=None):
        L.info(f"-> {self.tweet_to_url(tweet)}: Handling as default case, no clear intent found.") 
        L.debug(f"...in {tweet.text}")
        # L.info(f'--> No action taken.')
        # perhaps hand back a link if we have a node that seems relevant?
        # TODO: do keywords search?
        # self.reply_to_tweet(tweet, 'Would you like help?')
    
    def api_get(self, uri, params=None):
        """Generic wrapper for calling the Twitter API with a fully determined URI (no params)."""
        bearer_header = self.get_bearer_header()
        resp = requests.get(uri, headers=bearer_header, params=params)
        try:
            # hmm.
            return resp.json()['data']
        except json.decoder.JSONDecodeError:
            L.error(f"*** Couldn't decode JSON message for call to {uri}.")
            L.error(resp.text)
            return None
        except KeyError:
            L.error(f"*** No data found for call to {uri}, may be due to throttling.")
            L.error(resp.text)
            self.sleep()
            return None

    def api_post(self, uri, params=None):
        """Generic wrapper for calling the Twitter API with a fully determined URI (no params)."""
        bearer_header = self.get_bearer_header()
        resp = requests.post(uri, headers=bearer_header, params=params)
        try:
            return resp.json()
        except json.decoder.JSONDecodeError:
            L.error(f"*** Couldn't decode JSON message for call to {uri}.")
            L.error(resp.text)
            return None

    def api_delete(self, uri, params=None):
        """Generic wrapper for calling the Twitter API with a fully determined URI (no params)."""
        bearer_header = self.get_bearer_header()
        resp = requests.delete(uri, headers=bearer_header, params=params)
        try:
            return resp.json()
        except json.decoder.JSONDecodeError:
            L.error(f"*** Couldn't decode JSON message for call to {uri}.")
            L.error(resp.text)
            return None

    @cachetools.func.ttl_cache(ttl=600)
    def get_friends(self):
        friends = []
        L.info('*** get friends refreshing')
        try:
            friends = tweepy.Paginator(self.client.get_users_following, self.bot_user_id)
            return friends.flatten()
        except tweepy.errors.TooManyRequests:
            # This gets throttled a lot -- worth it not to go too hard here as it'll prevent the rest of the bot from running.
            pass
        L.debug(f'*** friends: {friends}')
        return friends

    @cachetools.func.ttl_cache(ttl=600)
    def get_followers(self):
        L.info('*** get followers refreshing')
        followers = []
        try:
            followers = tweepy.Paginator(self.client.get_users_followers, self.bot_user_id, max_results=1000)
            return followers.flatten()
        except tweepy.errors.TooManyRequests:
            # This gets throttled a lot -- worth it not to hard here as it'll prevent the rest of the bot from running.
            # TODO: read from friends.yaml!
            pass
        L.debug(f'*** followers: {followers}')
        return followers

    def unfollow(self, user_id):
        # uri = f'https://api.twitter.com/2/users/{self.bot_user_id}/following/{user_id}'
        # return self.api_delete(uri)
        return self.client.unfollow_user(user_id)

    def follow(self, user_id):
        # Twitter seems to sometimes be failing this silently sometimes and punishing us for it? Unsure.
        # Maybe it's just that the API v2 code doesn't handle error conditions well yet :)
        if args.follow:
            return self.client.follow_user(user_id)
        else:
            L.info("Not following user as --follow was not specified.")
            return False
        # For now Twitter is being really tight about following users.
        # api v2 requires an oauth2 setup for this we don't currently support:
        # {'title': 'Unsupported Authentication', 'detail': 'Authenticating with OAuth 2.0 Application-Only is forbidden for this endpoint.  Supported authentication types are [OAuth 1.0a User Context, OAuth 2.0 User Context].', 'type': 'https://api.twitter.com/2/problems/unsupported-authentication', 'status': 403}
        # uri = f'https://api.twitter.com/2/users/{self.bot_user_id}/following'
        # params = {
        #     'target_user_id': user_id
        # }
        # return self.api_post(uri, params)

    @cachetools.func.ttl_cache(ttl=600)
    def get_username(self, user_id):
        # Could get rid of this thanks to Tweepy.
        # Oh, but the memoizing is nice maybe? :) I wonder if Tweepy caches anyway.
        # API V2 Client doesn't mention it.
        return self.client.get_user(id=user_id).data.username

    def follow_followers(self):
        L.info("# Trying to follow back only followers.")
        friends = {friend for friend in self.get_friends()}
        # write list here?
        followers = {follower for follower in self.get_followers()}
        # write list here?
        L.debug(f"# friends: {friends}")
        L.debug(f"# followers: {followers}")

        for friend in friends - followers:
            L.debug(f"# Trying to unfollow {friend} as they don't follow us.")
            self.unfollow(friend.id)

        for follower in followers:
            if follower.protected:
                # Trying to follow back protected users causes trouble, as Twitter doesn't like it when we try to follow a user more than once (and they take to approve follows, sometimes never do.)
                pass
            L.debug(f"# Trying to follow {follower} as they follow us.")
            self.follow(follower.id)

    def get_mentions(self):
        mentions = tweepy.Paginator(
            self.client.get_users_mentions,
            id=self.bot_user_id,
            expansions='author_id',
            tweet_fields='author_id,created_at',
            user_fields='username',
            since_id=self.since_id
            ).flatten()
        return mentions

    def get_timeline(self):
        timeline = tweepy.Paginator(
            self.client.get_home_timeline,
            expansions='author_id',
            tweet_fields='author_id,created_at',
            user_fields='username',
            ).flatten()
        return timeline

    # TODO: probably refactor into process_mentions and process_timeline? unsure.
    def process_mentions(self):
        global BACKOFF
        # from https://realpython.com/twitter-bot-python-tweepy/
        L.info("# Retrieving mentions")
        new_since_id = self.since_id
        # only process tweets newer than n days -- works around the worst of the twitter search restrictions, as
        # for old tweets sometimes we might not see our own responses :(
        L.info(f'age: {args.max_age}')
        start_time = datetime.datetime.now () - datetime.timedelta(minutes=args.max_age)
        # explicit mentions
        try:
            mentions = list(self.get_mentions())
            L.info(f'# Processing {len(mentions)} mentions.')
            # hack
        except Exception as e:
            # Twitter gives back 429 surprisingly often for this, no way I'm hitting the stated limits?
            L.exception(f'# Twitter gave up on us while processing mentions, {e}.')
            BACKOFF = min(BACKOFF * 2, BACKOFF_MAX)
            mentions = []

        # our tweets and those from users that follow us (actually that we follow, but we try to keep that up to date).
        if args.timeline:
            try:
                timeline = list(self.get_timeline())
            except Exception as e:
                # Twitter gives back 429 surprisingly often for this, no way I'm hitting the stated limits?
                L.exception(f'# Twitter gave up on us while trying to read the timeline, {e}.')
                BACKOFF = min(BACKOFF * 2, BACKOFF_MAX)
                timeline = []
        else:
            timeline = []

        tweets = mentions + timeline
        L.info(f"# Processing {len(mentions)} tweets from our mentions.")
        L.info(f"# Processing {len(timeline)} tweets from our timeline.")
        L.info(f'# Processing {len(tweets)} tweets overall.')

        oldies = 0
        for n, tweet in enumerate(tweets):
            L.info(f'-' * 80)
            L.debug(f"# Processing tweet {n}/{len(tweets)}: https://twitter.com/{self.get_username(tweet.author_id)}/status/{tweet.id}")

            # if tweet.created_at < start_time:
            #     oldies += 1
            #     continue

            # Process commands, in order of priority
            cmds = [
                    (HELP_RE, self.handle_help),
                    #(PUSH_RE, handle_push),
                    (OPT_IN_RE, self.handle_opt_in),
                    (OPT_OUT_RE, self.handle_opt_out),
                    (WIKILINK_RE, self.handle_wikilink),
                    (HASHTAG_RE, self.handle_hashtag),
                    (DEFAULT_RE, self.handle_default),
                    ]
            for regexp, handler in cmds:
                match = regexp.search(tweet.text.lower())
                if match:
                    handler(tweet, match)
            L.debug(f'# Processed tweet: {tweet.id, tweet.text}')
            new_since_id = max(int(tweet.id), new_since_id)

        # L.info(f'-> {oldies} too old (beyond current threshold of {start_time}).')
        return new_since_id

    def sleep(self):
        L.info(f"Sleeping for {BACKOFF} seconds.")
        time.sleep(BACKOFF)

def main():
    # Load config.
    try:
        config = yaml.safe_load(args.config)
    except yaml.YAMLError as e:
        L.fatal(e)

    bot = AgoraBot(config)
    L.info('[[agora bot]] starting.')

    while True:
        if args.follow:
            try:
                bot.follow_followers()
            except tweepy.errors.TweepyException as e:
                L.info(e)
                L.error("# Twitter api rate limit reached while trying to interact with friends.".format(e))
                L.info(f"# Backing off {BACKOFF} after exception.")
                bot.sleep()
        try: 
            bot.process_mentions()
        except tweepy.errors.TweepyException as e:
            L.info(e)
            L.error("# Twitter api rate limit reached while trying to process incoming tweets.".format(e))
            L.info(f"# Backing off {BACKOFF} after exception.")
            bot.sleep()
        L.info(f'# [[agora bot]] waiting for {BACKOFF}.')
        bot.sleep()

if __name__ == "__main__":
    main()
