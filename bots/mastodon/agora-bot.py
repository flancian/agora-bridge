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
import subprocess
import random
import re
import time
import urllib
import yaml

from collections import OrderedDict
from datetime import datetime
from mastodon import Mastodon, StreamListener, MastodonAPIError, MastodonNetworkError

# [[2022-11-17]]: changing approaches, bots should write by calling an Agora API; direct writing to disk was a hack.
# common.py should have the methods to write resources to a node in any case.
# (maybe direct writing to disk can remain as an option, as it's very simple and convenient if people are running local agoras?).
# [[2025-03-23]]: drive by while I'm passing by here fixing a different thing -- I think I'm coming to terms with the fact that a lot of hacks I intend to fix will be permanent :) not saying that this is one, but if it is, so be it. Future Agoras will learn from our mistakes ;)
from . import common

WIKILINK_RE = re.compile(r'\[\[(.*?)\]\]', re.IGNORECASE)
# thou shall not use regexes to parse html, except when yolo
HASHTAG_RE = re.compile(r'#<span>(\w+)</span>', re.IGNORECASE)
PUSH_RE = re.compile(r'\[\[push\]\]', re.IGNORECASE)
# Buggy, do not enable without revamping build_reply()
P_HELP = 0.0

parser = argparse.ArgumentParser(description='Agora Bot for Mastodon (ActivityPub).')
parser.add_argument('--config', dest='config', type=argparse.FileType('r'), required=True, help='The path to agora-bot.yaml, see agora-bot.yaml.example.')
parser.add_argument('--verbose', dest='verbose', type=bool, default=False, help='Whether to log more information.')
parser.add_argument('--output-dir', dest='output_dir', required=True, help='The path to a directory where data will be dumped as needed. If it does not exist, we will try to create it.')
parser.add_argument('--dry-run', dest='dry_run', action="store_true", help='Whether to refrain from posting or making changes.')
parser.add_argument('--catch-up', dest='catch_up', action="store_true", help='Whether to run code to catch up on missed toots (e.g. because we were down for a bit, or because this is a new bot instance.')
args = parser.parse_args()

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

class AgoraBot(StreamListener):
    """main class for [[agora bot]] for [[mastodon]]."""
    # this follows https://mastodonpy.readthedocs.io/en/latest/#streaming and https://github.com/ClearlyClaire/delibird/blob/master/main.py

    def __init__(self, mastodon, bot_username):
        StreamListener.__init__(self)
        self.mastodon = mastodon
        self.bot_username = bot_username
        L.info(f'[[agora bot]] for {bot_username} started!')

    def send_toot(self, msg, in_reply_to_id=None):
        L.info('sending toot.')
        try:
            status = self.mastodon.status_post(msg, in_reply_to_id=in_reply_to_id)
        except MastodonAPIError as e:
            L.error(f"Could not send toot: {e}")

    def boost_toot(self, id):
        L.info('boosting toot.')
        status = self.mastodon.status_reblog(id)

    def build_reply(self, status, entities):
        # These could be made a lot more user friendly just by making the Agora bot return *anything* beyond just links and mentions!
        # At least some greeting...?
        if random.random() < P_HELP:
            self.send_toot('If an Agora hears about a [[wikilink]] or #hashtag, it will try to resolve them for you and link your resources in the [[nodes]] or #nodes you mention.', status.id)
        lines = []

        # always at-mention at least the original author.
        mentions = f"@{status['account']['acct']} "
        if status.mentions:
            # Some time in the past I wrote: if other people are mentioned in the thread, only at mention them if they also follow us.
            # [[2025-03-23]]: honestly, as I'm rereading this code while on a long flight, I'm not sure this was a great idea.
            # I see no strong reason to make an information-integrator and information-spreader like Agora bot less effective by dropping people from threads.
            # see https://social.coop/@flancian/108153868738763998 for initial reasoning -- but as I'm standing here I'm leaning towards disabling this.
            #
            # followers = [x['acct'] for x in self.get_followers()]
            for mention in status.mentions:
                # if mention['acct'] in followers:
                mentions += f"@{mention['acct']} "

        lines.append(mentions)

        for entity in entities:
            path = urllib.parse.quote_plus(entity)
            lines.append(f'https://anagora.org/{path}')

        msg = '\n'.join(lines)
        return msg

    def log_toot(self, toot, nodes):
        if not args.output_dir:
            # note this actually means that if output_dir is not set up this bot won't respond to messages,
            # as the caller currently thinks False -> do not post (to prevent duplicates).
            return False

        for node in nodes:
            if ('/' in node):
                # for now, dump only to the last path fragment -- this yields the right behaviour in e.g. [[go/cat-tournament]]
                node = os.path.split(node)[-1]

            bot_stream_dir = common.mkdir(os.path.join(args.output_dir, self.bot_username))
            bot_stream_filename = os.path.join(bot_stream_dir, node + '.md')

            # dedup logic.
            try:
                with open(bot_stream_filename, 'r') as note:
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
                with open(bot_stream_filename, 'a') as note:
                    url = toot.url or toot.uri
                    # Now also adding creation datetime of the toot to align with other bots.
                    note.write(f"- [[{toot.created_at}]] [[{toot.account.acct}]] {url}\n")
            except: 
                L.error("Couldn't log toot to note.")
                return False
        return True

    def write_toot(self, toot, nodes):
        L.debug(f"Maybe logging toot if user has opted in.")
        if not args.output_dir:
            return False

        # toot.account.acct is flancian@social.coop, .username is actually just flancian
        username = toot.account.acct

        if not self.wants_writes(username):
            L.info(f"User {username} has NOT opted in, skipping logging full post.")
            return False
        L.info(f"User {username} has opted in to writing, pushing (publishing) full post text to an Agora.")

        user_stream_dir = common.mkdir(os.path.join(args.output_dir, username))

        for node in nodes:
            user_stream_filename = os.path.join(user_stream_dir, node + '.md')
            try:
                with open(user_stream_filename, 'a') as note:
                    url = toot.url or toot.uri
                    note.write(f"- [[{toot.created_at}]] @[[{username}]] (<a href='{url}'>link</a>):\n  - {toot.content}\n")
            except:
                L.error("Couldn't log full post to note in user stream.")
                return

    def is_mentioned_in(self, username, node):
        # TODO: fix this.
        if not args.output_dir:
            return False

        if ('/' in node):
            # for now, dump only to the last path fragment -- this yields the right behaviour in e.g. [[go/cat-tournament]]
            node = os.path.split(node)[-1]

        agora_stream_dir = common.mkdir(os.path.join(args.output_dir, self.bot_username))
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

    def wants_writes(self, user):
        # Allowlist to begin testing? :)
        WANTS_WRITES = ['@flancian@social.coop']

        if user in WANTS_WRITES:
            return True
        # Trying to infer opt in status from the Agora: does the node 'push' contain a mention of the user?
        if self.is_mentioned_in(user, 'push') and not self.is_mentioned_in(user, 'no push'):
            return True
        # Same for [[opt in]]
        if self.is_mentioned_in(user, 'opt in') and not self.is_mentioned_in(user, 'opt out'):
            return True
        return False

    def maybe_reply(self, status, msg, entities):

        if args.dry_run:
            L.info(f"-> not replying due to dry run, message would be: {msg}")
            return False

        # we use the log as a database :)
        if self.log_toot(status, entities):
            self.send_toot(msg, status.id)
            # maybe write the full message to disk if the user seems to have opted in.
            # one user -> one directory, as that allows us to easily transfer history to users.
            # [[digital self determination]]
            self.write_toot(status, entities)
        else:
            L.info("-> not replying due to failed or redundant logging, skipping to avoid duplicates.")

    def get_followers(self):
        # First batching method, we will probably need more of these :)
        batch = self.mastodon.account_followers(self.mastodon.me().id, limit=80)
        followers = []
        while batch:
            followers += batch
            batch = self.mastodon.fetch_next(batch)
        return followers

    def get_statuses(self, user):
        # Added on [[2025-03-23]] to work around weird Mastodon bug with sorting, and it seems generally useful so...
        batch = self.mastodon.account_statuses(user['id'], limit=40)
        posts = []
        while batch:
            posts += batch
            batch = self.mastodon.fetch_next(batch)
        return posts

    def is_following(self, user):
        following_accounts = [f['acct'] for f in self.get_followers()]
        if user not in following_accounts:
            L.info(f"account {user} not in followers: {following_accounts}.")
            return False
        return True

    def handle_wikilink(self, status, match=None):
        L.info(f'handling at least one wikilink: {status.content}, {match}')

        if status['reblog']:
            L.info(f'Not handling boost.')
            return True

        # We want to only reply to accounts that follow us.
        user = status['account']['acct']
        if not self.is_following(user):
            return True

        wikilinks = WIKILINK_RE.findall(status.content)
        entities = uniq(wikilinks)
        msg = self.build_reply(status, entities)
        self.maybe_reply(status, msg, entities)

    def handle_hashtag(self, status, match=None):
        L.info(f'handling at least one hashtag: {status.content}, {match}')
        user = status['account']['acct']

        # Update (2023-07-19): We want to only reply hashtag posts to accounts that opted in.
        if not self.is_mentioned_in(user, 'opt in'):
            return True

        # We want to only reply to accounts that follow us.
        user = status['account']['acct']
        if not self.is_following(user):
            return True

        # These users have opted out of hashtag handling.
        if 'bmann' in user or self.is_mentioned_in(user, 'opt out'):
            L.info(f'Opting out user {user} from hashtag handling.')
            return True 
        if status['reblog'] and not self.is_mentioned_in(user, 'opt in'):
            L.info(f'Not handling boost from non-opted-in user.')
            return True
        hashtags = HASHTAG_RE.findall(status.content)
        entities = uniq(hashtags)
        msg = self.build_reply(status, entities)
        self.maybe_reply(status, msg, entities)

    def handle_push(self, status, match=None):
        L.info(f'seen push: {status}, {match}')
        # This has a bug as of [[2022-08-13]], likely having to do with us not logging pushes to disk as with other triggers.
        return False
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

    def handle_follow(self, notification):
        """Try to handle live follows of [[agora bot]]."""
        L.info('Got a follow!')
        mastodon.account_follow(notification.account)

    def handle_unfollow(self, notification):
        """Try to handle live unfollows of [[agora bot]]."""
        L.info('Got an unfollow!')
        mastodon.account_follow(notification.account)

    def on_notification(self, notification):
        # we get this for explicit mentions.
        self.last_read_notification = notification.id
        if notification.type == 'mention':
            self.handle_mention(notification.status)
        elif notification.type == 'follow':
            self.handle_follow(notification.status)
        elif notification.type == 'unfollow':
            self.handle_unfollow(notification.status)
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

    # Set up Mastodon API.
    mastodon = Mastodon(
        version_check_mode="none",
        access_token = config['access_token'],
        api_base_url = config['api_base_url'],
    )

    bot_username = f"{config['user']}@{config['instance']}"

    bot = AgoraBot(mastodon, bot_username)
    followers = bot.get_followers()
    # Now unused?
    # watching = get_watching(mastodon)

    # try to clean up one old list to account for the one we'll create next.
    lists = mastodon.lists()
    try:
        for l in lists[:-5]:
            L.info(f"trying to clean up an old list: {l}, {l['id']}.")
            mastodon.list_delete(l['id'])
            L.info(f"clean up succeeded.")
    except:
        L.info("couldn't clean up list.")

    # try:
    #     mastodon.list_accounts_add(watching, followers)
    # except MastodonAPIError as e:
    #     print("error when trying to add accounts to watching")
    #     print(f"watching: {watching}")
    #     print(e)

    # why do we have both? hmm.
    # TODO(flancian): look in commit history or try disabling one.
    # it would be nice to get rid of lists if we can.

    # as of 2025-01 and with the move to GoToSocial (social.agor.ai), streaming seems broken.
    # suspecting GTS, for now we go back to polling/catching up.
    # given that we know own the instance, I am fine bumping throttling limits and just going with this for now.

    # # TODO: re-add?
    # L.info('trying to stream user.')
    # mastodon.stream_user(bot, run_async=True, reconnect_async=True)
    # mastodon.stream_user(bot)
    # L.info('now streaming.')

    # We used to do lists -- maybe worth trying again with GTS?
    # L.info('trying to stream list.')
    # mastodon.stream_list(id=watching.id, listener=bot, run_async=True, reconnect_async=True)
    while True:
        L.info('[[agora mastodon bot]] is alive, trying to catch up with new friends and lost posts.')

        # YOLO -- working around a potential bug after the move to GoToSocial :)
        followers = bot.get_followers()
        L.info(f'Followers count: {len(followers)}')
        for user in followers:
            # Check relationship status to avoid redundant follow attempts.
            # This is not perfectly efficient (N+1 queries) but acceptable for current scale.
            # A better approach would be to batch check relationships if the library/API supports it easily.
            try:
                relationships = mastodon.account_relationships([user.id])
                if relationships and not relationships[0].following:
                    L.info(f'Trying to follow back {user.acct}')
                    mastodon.account_follow(user.id)
            except MastodonAPIError as e:
                L.warning(f"Error checking relationship or following {user.acct}: {e}")
                pass

            if args.catch_up:
                L.info(f"trying to catch up with any missed toots for user {user.acct}.")
                # the mastodon API... sigh.
                # mastodon.timeline() maxes out at 40 toots, no matter what limit we set.
                #   (this might be a limitation of botsin.space?)
                # mastodon.list_timeline() looked promising but always comes back empty with no reason.
                # so we need to iterate per-user in the end. should be OK.
                L.info(f'fetching latest toots by user {user.acct}')
                # as of [[2025-03-23]], I'm here trying to figure out why suddenly the Agora bot is not seeing new toots.
                # maybe the ordering of toots is implementation-dependent and we're supposed to iterate/sort client side?
                # looking into Mastodon.py, there's not much to this method beyond a wrapper that calls __api_request to /<id>/statuses...
                for status in bot.get_statuses(user):
                    # this should handle deduping, so it's safe to always try to reply.
                    bot.handle_update(status)

        L.info('Sleeping...')
        time.sleep(30)
     
if __name__ == "__main__":
    main()
