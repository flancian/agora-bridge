#!/usr/bin/env python3

import argparse
import logging
import os
import re
import time
import subprocess
import urllib
import yaml

# #go https://github.com/MarshalX/atproto
from atproto import Client, client_utils, models

parser = argparse.ArgumentParser(description='Agora Bot for Bluesky (atproto).')
parser.add_argument('--config', dest='config', type=argparse.FileType('r'), required=True, help='The path to agora-bot.yaml, see agora-bot.yaml.example.')
parser.add_argument('--verbose', dest='verbose', type=bool, default=False, help='Whether to log more information.')
parser.add_argument('--output-dir', dest='output_dir', required=True, help='The path to a directory where data will be dumped as needed. If it does not exist, we will try to create it.')
parser.add_argument('--write', dest='write', action="store_true", help='Whether to actually post (default, when this is off, is dry run.')
args = parser.parse_args()

WIKILINK_RE = re.compile(r'\[\[(.*?)\]\]', re.IGNORECASE)
# thou shall not use regexes to parse html, except when yolo
HASHTAG_RE = re.compile(r'#<span>(\w+)</span>', re.IGNORECASE)
# https://github.com/bluesky-social/atproto/discussions/2523
URI_RE = re.compile(r'at://(.*?)/app.bsky.feed.post/(.*)', re.IGNORECASE)

logging.basicConfig()
L = logging.getLogger('agora-bot')
if args.verbose:
    L.setLevel(logging.DEBUG)
else:
    L.setLevel(logging.INFO)

def uniq(l):
    # also orders, because actually it works better.
    # return list(OrderedDict.fromkeys(l))
    # only works for hashable items
    return sorted(list(set(l)), key=str.casefold)

def mkdir(string):
    if not os.path.isdir(string):
        print(f"Trying to create {string}.")
        output = subprocess.run(['mkdir', '-p', string], capture_output=True)
        if output.stderr:
            L.error(output.stderr)
    return os.path.abspath(string)



class AgoraBot(object):

    def __init__(self):
        try:
            self.config = yaml.safe_load(args.config)
        except yaml.YAMLError as e:
            L.error(e)

        self.client = Client(base_url='https://bsky.social')
        self.client.login(self.config['user'], self.config['password'])

        self.me = self.client.resolve_handle(self.config['user'])

    def build_reply(self, entities):
        # always at-mention at least the original author.
        text_builder = client_utils.TextBuilder()
        for entity in entities:
            path = urllib.parse.quote_plus(entity)
            url = f'https://anagora.org/{path}'
            text_builder.link(url, url)
            text_builder.text('\n')
        return text_builder

    def post_uri_to_url(self, uri):
        base = 'https://bsky.app'
        match = URI_RE.search(uri)
        profile = match.group(1)
        rkey = match.group(2)
        return f'{base}/profile/{profile}/post/{rkey}'

    def log_post(self, uri, post, entities):
        url = self.post_uri_to_url(uri)

        if not args.output_dir:
            return False

        if not args.write:
            L.info(f'Here we would log a link to {url} in nodes {entities}.')

        for node in entities:
            if ('/' in node):
                # for now, dump only to the last path fragment -- this yields the right behaviour in e.g. [[go/cat-tournament]]
                node = os.path.split(node)[-1]

            # TODO: update username after refactoring.
            bot_stream_dir = mkdir(os.path.join(args.output_dir, self.config['user']))
            bot_stream_filename = os.path.join(bot_stream_dir, node + '.md')

            # dedup logic.
            try:
                with open(bot_stream_filename, 'r') as note:
                    note = note.read()
                    L.info(f"In note: {note}.")
                    if note and url in note:
                        L.info("Post already logged to note.")
                        return False
                    else:
                        if args.write:
                            L.info("Post will be logged to note.")
            except FileNotFoundError:
                pass

            # try to append.
            try:
                if args.write:
                    with open(bot_stream_filename, 'a') as note:
                        note.write(f"- [[{post.indexed_at}]] @[[{post.author.handle}]]: {url}\n")
            except:
                L.error("Couldn't log post to note.")
                return False

        return True
        
    def maybe_reply(self, uri, post, msg, entities):
        L.info(f'Would reply to {post} with {msg.build_text()}')
        ref = models.create_strong_ref(post)
        if args.write:
            # Only actually write if we haven't written before (from the PoV of the current agora).
            # log_post should return false if we have already written a link to node previously.
            if self.log_post(uri, post, entities):
                self.client.send_post(msg, reply_to=models.AppBskyFeedPost.ReplyRef(parent=ref, root=ref))
        else:
            L.info(f'Skipping replying due to dry_run. Pass --write to actually write.')

    def get_followers(self):
        return self.client.get_followers(self.config['user'])['followers']

    def get_follows(self):
        return self.client.get_follows(self.config['user'])['follows']

    def get_mutuals(self):
        # Note we'll return a set of DIDs (type hints to the rescue? eventually... :))
        mutuals = set()
        follows = self.get_follows()
        followers = self.get_followers()
        for follower in followers: 
            if follower.did in [f.did for f in follows]:
                # Ahoy matey!
                mutuals.add(follower.did)

        # This is no longer needed but remains an example of working with cursors.
        #    cursor = ''
        #    # This work but it is quite inefficient to check for mutualness as some accounts follow *a lot* of people.
        #    while True:
        #        L.info(f'Processing following list for {follower.handle} with cursor {cursor}')
        #        follows = self.client.get_follows(follower.did, limit=100, cursor=cursor)
        #        for following in follows:
        #            if following[0] == 'follows':
        #                for follow in following[1]:
        #                    # L.info(f'{follow.did}')
        #                    if follow.did == self.me.did:
        #                        # Ahoy matey!
        #                        L.info(f'{follower.handle} follows us!')
        #                        mutuals.add(follower.did)
        #        cursor = follows.cursor
        #        if not cursor:
        #           break 

        return mutuals

    def follow_followers(self):
        for follower in self.get_followers():
            if follower.did in self.get_mutuals():
                L.info(f'-> We already follow {follower.handle}')
            else:
                L.info(f'-> Trying to follow back {follower.handle}')
                self.client.follow(follower.did)

    def catch_up(self):
        for mutual_did in self.get_mutuals():
            L.info(f'-> Processing posts by {mutual_did}...')
            posts = self.client.app.bsky.feed.post.list(mutual_did, limit=100)
            for uri, post in posts.records.items():
                wikilinks = WIKILINK_RE.findall(post.text)
                if wikilinks:
                    entities = uniq(wikilinks)
                    L.info(f'\nSaw wikilinks at {uri}:\n{post.text}\n')
                    msg = self.build_reply(entities)
                    L.info(f'\nWould respond with:\n{msg.build_text()}\n--\n')
                    # atproto somehow needs this kind of post and not the... other?
                    actual_post = self.client.get_posts([uri]).posts[0]
                    self.maybe_reply(uri, actual_post, msg, entities)

def main():
    # How much to sleep between runs, in seconds (this may go away once we're using a subscription model?).
    sleep = 60

    bot = AgoraBot()

    while True:
        bot.follow_followers()
        bot.catch_up()

        L.info(f'-> Sleeping for {sleep} seconds...')
        time.sleep(sleep)

    # Much more goes here I guess :)

if __name__ == "__main__":
    main()
