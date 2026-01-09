#!/usr/bin/env python3

import argparse
import logging
import os
import re
import time
import subprocess
import urllib
import yaml
from datetime import datetime, timedelta, timezone

# #go https://github.com/MarshalX/atproto
from atproto import Client, client_utils, models

parser = argparse.ArgumentParser(description='Agora Bot for Bluesky (atproto).')
parser.add_argument('--config', dest='config', type=argparse.FileType('r'), required=True, help='The path to agora-bot.yaml, see agora-bot.yaml.example.')
parser.add_argument('--verbose', dest='verbose', type=bool, default=False, help='Whether to log more information.')
parser.add_argument('--output-dir', dest='output_dir', required=True, help='The path to a directory where data will be dumped as needed. If it does not exist, we will try to create it.')
parser.add_argument('--write', dest='write', action="store_true", help='Whether to actually post (default, when this is off, is dry run.')
parser.add_argument('--catch-up-days', dest='catch_up_days', type=int, default=180, help='Max age in days for posts to process.')
parser.add_argument('--reply-interval', dest='reply_interval', type=float, default=10.0, help='Minimum seconds between replies.')
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
        self.last_reply_time = 0

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

    def log_post(self, uri, post, entities, check_only=False):
        url = self.post_uri_to_url(uri)

        if not args.output_dir:
            return False

        if not args.write and not check_only:
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
                    L.debug(f"In note: {note}.")
                    if note and url in note:
                        L.info("Post already logged to note.")
                        return False
                    else:
                        if args.write:
                            L.debug("Post will be logged to note.")
            except FileNotFoundError:
                pass

            if check_only:
                continue

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
        
        # Check if already processed
        if not self.log_post(uri, post, entities, check_only=True):
             L.info("Skipping reply (already logged).")
             return

        ref = models.create_strong_ref(post)
        if args.write:
            # Throttle
            now = time.time()
            elapsed = now - self.last_reply_time
            if elapsed < args.reply_interval:
                sleep_time = args.reply_interval - elapsed
                L.info(f"Throttling reply, sleeping for {sleep_time:.2f}s...")
                time.sleep(sleep_time)

            try:
                self.client.send_post(msg, reply_to=models.AppBskyFeedPost.ReplyRef(parent=ref, root=ref))
                self.last_reply_time = time.time()
                # Log to disk after success
                self.log_post(uri, post, entities)
            except Exception as e:
                L.error(f"Error sending Bluesky post: {e}")
        else:
            L.info(f'Skipping replying due to dry_run. Pass --write to actually write.')

    def get_followers(self):
        L.info("Fetching followers...")
        followers = []
        cursor = None
        page_count = 0
        while True:
            try:
                page_count += 1
                response = self.client.get_followers(self.config['user'], cursor=cursor)
                followers.extend(response.followers)
                L.debug(f"Fetched followers page {page_count}, total so far: {len(followers)}")
                if not response.cursor:
                    break
                cursor = response.cursor
                # Sleep briefly to avoid timeouts/rate limits during heavy pagination
                time.sleep(0.1)
            except Exception as e:
                L.error(f"Error fetching followers page: {e}")
                break
        L.info(f"Finished fetching {len(followers)} followers.")
        return followers

    def get_follows(self):
        L.info("Fetching follows...")
        follows = []
        cursor = None
        page_count = 0
        while True:
            try:
                page_count += 1
                response = self.client.get_follows(self.config['user'], cursor=cursor)
                follows.extend(response.follows)
                L.debug(f"Fetched follows page {page_count}, total so far: {len(follows)}")
                if not response.cursor:
                    break
                cursor = response.cursor
                # Sleep briefly to avoid timeouts/rate limits during heavy pagination
                time.sleep(0.1)
            except Exception as e:
                L.error(f"Error fetching follows page: {e}")
                break
        L.info(f"Finished fetching {len(follows)} follows.")
        return follows

    def get_mutuals(self):
        # Return a dict of {did: handle} for mutuals
        mutuals = {}
        follows = self.get_follows()
        followers = self.get_followers()
        
        # Optimization: Map DID -> Handle for people we follow
        following_map = {f.did: f.handle for f in follows}
        
        for follower in followers: 
            if follower.did in following_map:
                # Ahoy matey!
                mutuals[follower.did] = follower.handle

        return mutuals

    def follow_followers(self):
        followers = self.get_followers()
        mutuals = self.get_mutuals()
        
        L.info(f"Checking {len(followers)} followers for follow-back candidates...")
        
        for follower in followers:
            if follower.did in mutuals:
                L.info(f'-> We already follow {follower.handle}')
            else:
                L.info(f'-> Trying to follow back {follower.handle}')
                try:
                    self.client.follow(follower.did)
                    # Add to local mutuals (best effort)
                    mutuals[follower.did] = follower.handle
                except Exception as e:
                    L.error(f"Error following {follower.handle}: {e}")

    def catch_up(self):
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=args.catch_up_days)

        # Iterate over items (did, handle)
        for mutual_did, handle in self.get_mutuals().items():
            L.info(f'-> Processing posts by {handle} ({mutual_did})...')
            try:
                posts = self.client.app.bsky.feed.post.list(repo=mutual_did, limit=100)
            except Exception as e:
                # Handle "Could not find repo" or other 400 errors gracefully
                # The exception string usually contains the status code
                if 'status_code=400' in str(e) or 'Could not find repo' in str(e):
                    L.warning(f"Could not find repo for {handle} ({mutual_did}). Likely deleted/suspended. Skipping.")
                else:
                    L.error(f"Error fetching posts for {handle} ({mutual_did}): {e}")
                continue

            for uri, post in posts.records.items():
                try:
                    # Some records might not have 'indexed_at' or 'text'
                    if not hasattr(post, 'indexed_at') or not hasattr(post, 'text'):
                        continue

                    # indexed_at is typically ISO 8601 like "2023-10-26T12:00:00.000Z"
                    # We handle the Z manually for compatibility.
                    post_date = datetime.fromisoformat(post.indexed_at.replace('Z', '+00:00'))
                except (ValueError, TypeError, AttributeError):
                    continue
                
                if post_date < cutoff_date:
                    # Skip old posts
                    continue

                wikilinks = WIKILINK_RE.findall(post.text)
                if wikilinks:
                    entities = uniq(wikilinks)
                    L.info(f'\nSaw wikilinks at {uri} ({post.indexed_at}):\n{post.text}\n')
                    msg = self.build_reply(entities)
                    L.info(f'\nWould respond with:\n{msg.build_text()}\n--\n')
                    # atproto somehow needs this kind of post and not the... other?
                    try:
                        actual_post = self.client.get_posts([uri]).posts[0]
                        self.maybe_reply(uri, actual_post, msg, entities)
                    except Exception as e:
                        L.error(f"Error fetching/processing post details: {e}")
            
            L.debug(f"Finished processing {mutual_did}.")

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
