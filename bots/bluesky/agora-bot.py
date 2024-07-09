#!/usr/bin/env python3

import argparse
import logging
import os
import re
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

def build_reply(entities):
    lines = []
    # always at-mention at least the original author.
    text_builder = client_utils.TextBuilder()
    for entity in entities:
        path = urllib.parse.quote_plus(entity)
        url = f'https://anagora.org/{path}'
        text_builder.link(url, url)
        text_builder.text('\n')
    return text_builder

def post_uri_to_url(uri):
    base = 'https://bsky.app'
    match = URI_RE.search(uri)
    profile = match.group(1)
    rkey = match.group(2)
    return f'{base}/profile/{profile}/post/{rkey}'

def log_post(uri, post, entities):
    url = post_uri_to_url(uri)

    if not args.output_dir:
        return False

    for node in entities:
        if not args.write:
            L.info(f'Here we would log a link to {url} in node {node}.')
        else:
            if ('/' in node):
                # for now, dump only to the last path fragment -- this yields the right behaviour in e.g. [[go/cat-tournament]]
                node = os.path.split(node)[-1]

            # username
            # TODO: update username.
            bot_stream_dir = mkdir(os.path.join(args.output_dir, 'anagora.bsky.social'))
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
                        L.info("Post will be logged to note.")
            except FileNotFoundError:
                pass

            # try to append.
            try:
                with open(bot_stream_filename, 'a') as note:
                    note.write(f"- [[{post.author.handle}]]: {url}\n")
            except: 
                L.error("Couldn't log post to note.")
                return False

    return True
    
def maybe_reply(client, uri, post, msg, entities):
    L.info(f'Would reply to {post} with {msg.build_text()}')
    ref = models.create_strong_ref(post)
    if log_post(uri, post, entities) and args.write:
        client.send_post(msg, reply_to=models.AppBskyFeedPost.ReplyRef(parent=ref, root=ref))
    else:
        L.info(f'Skipping replying due to dry_run. Pass --write to actually write.')


def main():
    try:
        config = yaml.safe_load(args.config)
    except yaml.YAMLError as e:
        L.error(e)

    client = Client(base_url='https://bsky.social')
    client.login(config['user'], config['password'])

    # post = client.send_post('Hello world! This is the first programmatic post of the Agora of Flancia in Bluesky :)')
    # print(post)

    me = client.resolve_handle(config['user'])
    followers = client.get_followers(config['user'])['followers']

    # Try to get mutuals
    mutuals = set()
    for follower in followers:
        L.info(f'trying to follow back {follower.handle}')
        client.follow(follower.did)

        # L.info(f"trying to catch up with any missed posts for user {follower.handle}.")
        for following in client.get_follows(follower.did, limit=100):
            # ?
            if following[0] == 'follows':
                for follow in following[1]:
                    # L.info(f'{follow.did}')
                    if follow.did == me.did:
                        # Ahoy matey!
                        L.info(f'{follow.did} follows us!')
                        mutuals.add(follower.did)

    L.info(f'-> Found mutuals: {mutuals}')

    for mutual_did in mutuals:
        L.info(f'Processing posts for {mutual_did}...')
        posts = client.app.bsky.feed.post.list(mutual_did, limit=100)
        for uri, post in posts.records.items():
            wikilinks = WIKILINK_RE.findall(post.text)
            if wikilinks:
                entities = uniq(wikilinks)
                L.info(f'\nSaw wikilinks at {uri}:\n{post.text}\n')
                msg = build_reply(entities)
                L.info(f'\nWould respond with:\n{msg.build_text()}\n--\n')
                # atproto somehow needs this kind of post and not the... other?
                post2 = client.get_posts([uri]).posts[0]
                maybe_reply(client, uri, post2, msg, entities)

    # Much more goes here :)

if __name__ == "__main__":
    main()
