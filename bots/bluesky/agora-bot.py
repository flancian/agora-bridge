#!/usr/bin/env python3

import argparse
import logging
import re
import yaml

# - #go https://github.com/MarshalX/atproto
from atproto import AtUri, Client, models

parser = argparse.ArgumentParser(description='Agora Bot for Bluesky (atproto).')
parser.add_argument('--config', dest='config', type=argparse.FileType('r'), required=True, help='The path to agora-bot.yaml, see agora-bot.yaml.example.')
parser.add_argument('--verbose', dest='verbose', type=bool, default=False, help='Whether to log more information.')
parser.add_argument('--output-dir', dest='output_dir', required=True, help='The path to a directory where data will be dumped as needed. If it does not exist, we will try to create it.')
parser.add_argument('--dry-run', dest='dry_run', action="store_true", help='Whether to refrain from posting or making changes.')
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
            if WIKILINK_RE.match(post.text):
                L.info(f'\nSaw wikilink at {uri}:\n{post.text}\n--\n')

    # Much more goes here :)

if __name__ == "__main__":
    main()
