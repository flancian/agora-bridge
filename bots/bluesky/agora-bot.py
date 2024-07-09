#!/usr/bin/env python3

import argparse
import logging
import re
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

def maybe_reply(client, uri, post, msg):
    L.info(f'Would reply to {post} with {msg.build_text()}')
    ref = models.create_strong_ref(post)
    if args.write:
        # client.send_post(msg, reply_to=post.reply)
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
                post2 = client.get_posts([uri]).posts[0]
                maybe_reply(client, uri, post2, msg)

    # Much more goes here :)

if __name__ == "__main__":
    main()
