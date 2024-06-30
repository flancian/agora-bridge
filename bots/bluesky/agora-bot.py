#!/usr/bin/env python3

import argparse
import logging
import re
import yaml

from atproto import Client

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

    followers = client.get_followers(config['user'])['followers']

    for follower in followers:
        L.info(f'trying to follow back {follower.handle}')
        client.follow(follower.did)

    return
    # dead code follows

    bot = AgoraBot()
    followers = bot.get_followers()
    # Now unused?
    watching = get_watching(mastodon)

    if args.catch_up:
        L.info(f"trying to catch up with any missed toots for user {user.acct}.")
        # the mastodon API... sigh.
        # mastodon.timeline() maxes out at 40 toots, no matter what limit we set.
        #   (this might be a limitation of botsin.space?)
        # mastodon.list_timeline() looked promising but always comes back empty with no reason.
        # so we need to iterate per-user in the end. should be OK.
        L.info(f'fetching latest toots by user {user.acct}')
        statuses = mastodon.account_statuses(user['id'], limit=40)
        for status in statuses:
            # this should handle deduping, so it's safe to always try to reply.
            bot.handle_update(status)

if __name__ == "__main__":
    main()
