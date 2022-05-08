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
import time
import urllib
import yaml

from collections import OrderedDict
from datetime import datetime
from mastodon import Mastodon, StreamListener, MastodonAPIError, MastodonNetworkError

WIKILINK_RE = re.compile(r'\[\[(.*?)\]\]', re.IGNORECASE)
# thou shall not use regexes to parse html, except when yolo
HASHTAG_RE = re.compile(r'#<span>(\S*)</span>', re.IGNORECASE)
PUSH_RE = re.compile(r'\[\[push\]\]', re.IGNORECASE)
P_HELP = 0.1

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

parser = argparse.ArgumentParser(description='Agora Bot for Mastodon (ActivityPub).')
parser.add_argument('--config', dest='config', type=argparse.FileType('r'), required=True, help='The path to agora-bot.yaml, see agora-bot.yaml.example.')
# parser.add_argument('--output-dir', dest='output_dir', type=dir_path, required=True, help='The path to a directory where data will be dumped as needed.')
parser.add_argument('--verbose', dest='verbose', type=bool, default=False, help='Whether to log more information.')
parser.add_argument('--output-dir', dest='output_dir', action=readable_dir, required=True, help='The path to a directory where data will be dumped as needed.')
parser.add_argument('--dry-run', dest='dry_run', action="store_true", help='Whether to refrain from posting or making changes.')
parser.add_argument('--catch-up', dest='catch_up', action="store_true", help='Whether to run code to catch up on missed toots (e.g. because we were down for a bit, or because this is a new bot instance.')
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
    # argh, this should really really be centralized/factored out, but the fact that we have two different repos makes this a bit harder than I'd like (without introducing cross-repo dependencies).
    slug = (
            wikilink.lower()
            .strip()
            .replace(',', ' ')
            .replace("'", ' ')
            .replace(';', ' ')
            .replace(':', ' ')
            .replace('  ', '-')
            .replace(' ', '-')
            )
    return slug

def uniq(l):
    # also orders, because actually it works better.
    # return list(OrderedDict.fromkeys(l))
    # only works for hashable items
    return sorted(list(set(l)), key=str.casefold)

def log_toot(toot, nodes):
    if not args.output_dir:
        # note this actually means that if output_dir is not set up this bot won't respond to messages,
        # as the caller currently thinks False -> do not post (to prevent duplicates).
        return False

    for node in nodes:
        if ('/' in node):
            # for now, dump only to the last path fragment -- this yields the right behaviour in e.g. [[go/cat-tournament]]
            node = os.path.split(node)[-1]

        filename = os.path.join(args.output_dir, node + '.md')

        # dedup logic.
        try:
            with open(filename, 'r') as note:
                note = note.read()
                L.info(f"Note: {note}.")
                # why both? it has been lost to the mists of time, or maybe the commit log :)
                # perhaps uri is what's set in pleroma?
                if note and (toot.url or toot.uri) in note:
                    L.info("Toot already logged to note.")
                    return False
                else:
                    L.info("Toot will be logged to note.")
        except FileNotFoundError:
            pass

        # try to append.
        try:
            with open(filename, 'a') as note:
                if toot.url:
                    note.write(f"- [[{toot.account.username}]] {toot.url}\n")
                else:
                    note.write(f"- [[{toot.account.username}]] {toot.uri}\n")
        except: 
            L.error("Couldn't log toot to note.")
            return False
    return True

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

    def build_reply(self, status, entities):
        if random.random() < P_HELP:
            self.send_toot('If an Agora hears about a [[wikilink]] or #hashtag, it will try to resolve them for you and link your resources in the [[nodes]] or #nodes you mention.', status.id)
        lines = []

        # always at-mention at least the original author.
        mentions = f"@{status['account']['acct']} "
        if status.mentions:
            # if other people are mentioned in the thread, only at mention them if they also follow us.
            # see https://social.coop/@flancian/108153868738763998 for reasoning.
            followers = [x['acct'] for x in self.mastodon.account_followers(self.mastodon.me().id)]
            for mention in status.mentions:
                if mention['acct'] in followers:
                    mentions += f"@{mention['acct']} "

        lines.append(mentions)

        for entity in entities:
            # slug = slugify(wikilink)
            path = urllib.parse.quote_plus(entity)
            lines.append(f'https://anagora.org/{path}')

        msg = '\n'.join(lines)
        return msg

    def maybe_reply(self, status, msg, entities):

        if args.dry_run:
            L.info(f"-> not replying due to dry run, message would be: {msg}")
            return False

        # we use the log as a database :)
        if log_toot(status, entities):
            self.send_toot(msg, status.id)
        else:
            L.info("-> not replying due to failed or redundant logging, skipping to avoid duplicates.")

    def handle_wikilink(self, status, match=None):
        L.info(f'handling at least one wikilink: {status.content}, {match}')
        wikilinks = WIKILINK_RE.findall(status.content)
        entities = uniq(wikilinks)
        msg = self.build_reply(status, entities)
        self.maybe_reply(status, msg, entities)

    def handle_hashtag(self, status, match=None):
        L.info(f'handling at least one hashtag: {status.content}, {match}')
        user = status['account']['acct']
        if 'bmann' in user:
            L.info(f'Opting out user {user} from hashtag handling.')
            return True 
        hashtags = HASHTAG_RE.findall(status.content)
        entities = uniq(hashtags)
        msg = self.build_reply(status, entities)
        self.maybe_reply(status, msg, entities)

    def handle_push(self, status, match=None):
        L.info(f'seen push: {status}, {match}')
        if args.dry_run:
            L.info("-> not replying due to dry run")
            return False
        self.send_toot('If you ask an Agora to push and you are a friend, the Agora will try to push with you.', status.id)
        self.boost_toot(status.id)

    def handle_mention(self, status):
        """Handle toots mentioning the [[agora bot]], which may contain commands"""
        L.info('Got a mention!')
        # Process commands, in order of priority
        cmds = [(PUSH_RE, self.handle_push),
                (WIKILINK_RE, self.handle_wikilink),
                (HASHTAG_RE, self.handle_hashtag)]
        for regexp, handler in cmds:
            match = regexp.search(status.content)
            if match:
                handler(status, match)
                return

    def handle_update(self, status):
        """Handle toots with [[patterns]] by people that follow us."""
        # Process commands, in order of priority
        cmds = [(PUSH_RE, self.handle_push),
                (WIKILINK_RE, self.handle_wikilink),
                (HASHTAG_RE, self.handle_hashtag)]
        for regexp, handler in cmds:
            match = regexp.search(status.content)
            if match:
                L.info(f'Got a status with a pattern! {status.url}')
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
    now = datetime.now()
    watching = mastodon.list_create(f'{now}')
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

    # try to clean up one old list to account for the one we'll create next.
    lists = mastodon.lists()
    try:
        l = lists[0]
        L.info(f"trying to clean up an old list: {l}, {l['id']}.")
        mastodon.list_delete(l['id'])
        L.info(f"clean up succeeded.")
    except:
        L.info("couldn't clean up list.")
        L.error(f"list: {l['id']})")

    try:
        mastodon.list_accounts_add(watching, followers)
    except MastodonAPIError as e:
        print("error when trying to add accounts to watching")
        print(f"watching: {watching}")
        print(e)

    for user in followers:
        L.info(f'following back {user.acct}')
        try:
            mastodon.account_follow(user.id)
        except MastodonAPIError:
            pass

        if args.catch_up:
            L.info("trying to catch up with any missed toots for user.")
            # the mastodon API... sigh.
            # mastodon.timeline() maxes out at 40 toots, no matter what limit we set.
            #   (this might be a limitation of botsin.space?)
            # mastodon.list_timeline() looked promising but always comes back empty with no reason.
            # so we need to iterate per-user in the end. should be OK.
            L.info(f'fetching latest toots by user {user.acct}')
            statuses = mastodon.account_statuses(user['id'])
            for status in statuses:
                # this should handle deduping, so it's safe to always try to reply.
                bot.handle_update(status)

    # why do we have both? hmm.
    # TODO(flancian): look in commit history or try disabling one.
    # it would be nice to get rid of lists if we can.
    L.info('trying to stream user.')
    mastodon.stream_user(bot, run_async=True, reconnect_async=True)
    L.info('trying to stream list.')
    mastodon.stream_list(id=watching.id, listener=bot, run_async=True, reconnect_async=True)
    L.info('now streaming.')
    while True:
        time.sleep(3600 * 24)
        L.info('[[agora mastodon bot]] is still alive.')

if __name__ == "__main__":
    main()
