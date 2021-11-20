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

# an [[agora bridge]], that is, a utility that takes a .yaml file describing a set of [[personal knowledge graphs]] or [[digital gardens]] and pulls them to be consumed by other bridges or an [[agora server]]. [[flancian]]

import argparse
import glob
import logging
import os
import random
import re
import yaml

from mastodon import Mastodon, StreamListener, MastodonAPIError

WIKILINK_RE = re.compile(r'\[\[(.*?)\]\]', re.IGNORECASE)
PUSH_RE = re.compile(r'\[\[push\]\]', re.IGNORECASE)
P_HELP = 0.0

parser = argparse.ArgumentParser(description='Agora Bot for Mastodon (ActivityPub).')
parser.add_argument('--config', dest='config', type=argparse.FileType('r'), required=True, help='The path to agora-bot.yaml, see agora-bot.yaml.example.')
# parser.add_argument('--output-dir', dest='output_dir', type=dir_path, required=True, help='The path to a directory where data will be dumped as needed.')
parser.add_argument('--verbose', dest='verbose', type=bool, default=False, help='Whether to log more information.')
args = parser.parse_args()

logging.basicConfig()
L = logging.getLogger('agora-bot')
if args.verbose:
    L.setLevel(logging.DEBUG)
else:
    L.setLevel(logging.INFO)

def slugify(wikilink):
    # trying to keep it light here for simplicity, wdyt?
    # c.f. util.py in [[agora server]].
    slug = (
            wikilink.lower()
            .strip()
            .replace(',', ' ')
            .replace(';', ' ')
            .replace(':', ' ')
            .replace('  ', '-')
            .replace(' ', '-')
            )
    return slug

class AgoraBot(StreamListener):
    """main class for [[agora bot]] for [[mastodon]]."""
    # this follows https://mastodonpy.readthedocs.io/en/latest/#streaming and https://github.com/ClearlyClaire/delibird/blob/master/main.py

    def __init__(self, mastodon):
        StreamListener.__init__(self)
        self.mastodon = mastodon
        L.info('[[agora bot]] started!')

    def send_toot(self, msg, in_reply_to_id=None):
        L.info('sending toot.')
        status = self.mastodon.status_post(msg, in_reply_to_id=in_reply_to_id)

    def boost_toot(self, id):
        L.info('boosting toot.')
        status = self.mastodon.status_reblog(id)

    def handle_wikilink(self, status, match=None):
        L.info(f'seen wikilink: {status}, {match}')
        if random.random() < P_HELP:
            self.send_toot('If you tell the Agora about a [[wikilink]], it will try to resolve it for you and mark your resource as relevant to the entity described between double square brackets.', status.id)
        wikilinks = WIKILINK_RE.findall(status.content)
        lines = []
        for wikilink in wikilinks:
            slug = slugify(wikilink)
            lines.append(f'https://anagora.org/{slug}')
        self.send_toot('\n'.join(lines), status.id)

    def handle_push(self, status, match=None):
        L.info(f'seen push: {status}, {match}')
        self.send_toot('If you ask the Agora to [[push]] and you are a friend, it will try to push with you.', status.id)
        self.boost_toot(status.id)

    def handle_mention(self, status):
        """Handle toots mentioning the [[agora bot]], which may contain commands"""
        L.info('Got a mention!')
        # Process commands, in order of priority
        cmds = [(PUSH_RE, self.handle_push),
                (WIKILINK_RE, self.handle_wikilink)]
        for regexp, handler in cmds:
            match = regexp.search(status.content)
            if match:
                handler(status, match)
                return

    def handle_update(self, status):
        """Handle toots with [[patterns]] by people that follow us."""
        # Process commands, in order of priority
        cmds = [(PUSH_RE, self.handle_push),
                (WIKILINK_RE, self.handle_wikilink)]
        for regexp, handler in cmds:
            match = regexp.search(status.content)
            if match:
                L.info('Got a status with a pattern!')
                handler(status, match)
                return

    def on_notification(self, notification):
        # we get this for explicit mentions.
        self.last_read_notification = notification.id
        if notification.type == 'mention':
            self.handle_mention(notification.status)
        else:
            L.info(f'received unhandled notification type: {notification.type}')

    def on_update(self, status):
        # we get this on all activity on our watching list.
        self.handle_update(status)

def get_watching(mastodon):
    lists = mastodon.lists()
    for l in lists:
        if l.title == 'watching':
            return l
    watching = mastodon.list_create('watching')
    return watching

def main():
    try:
        config = yaml.safe_load(args.config)
    except yaml.YAMLError as e:
        L.error(e)

    # Set up Mastodon
    mastodon = Mastodon(
	access_token = config['access_token'],
	api_base_url = config['api_base_url'],
    )
    
    bot = AgoraBot(mastodon)
    followers = mastodon.account_followers(mastodon.me().id)
    watching = get_watching(mastodon)
    try:
        mastodon.list_accounts_add(watching, followers)
    except MastodonAPIError:
        pass
    for user in followers:
        L.info(f'following back {user.acct}')
        try:
            mastodon.account_follow(user.id)
        except MastodonAPIError:
            pass
    #mastodon.stream_user(bot, run_async=True)
    L.info('[[agora bot]] starting streaming.')
    # why are the parameters flipped for this call?
    mastodon.stream_list(watching, bot)

    # mastodon.status_post("[[agora bot]] v0.9 initializing, please wait.")

if __name__ == "__main__":
    main()
