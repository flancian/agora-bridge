#!/usr/bin/env python3
# Copyright 2022 Google LLC
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
#
# [[flancian]]: I originally derived this from https://github.com/TomCasavant/RedditMaubot, but little code from that remains.
# This directory includes a MIT license (see LICENSE) because that is the original license for the above repo.

from random import choice
from typing import List, Tuple
import urllib.parse
from maubot import Plugin, MessageEvent
from mautrix.types import RelationType, TextMessageEventContent, RelatesTo, MessageType
from mautrix import errors
from maubot.handlers import command
import datetime
import os
import re

AGORA_BOT_ID="anagora@matrix.org"
AGORA_URL=f"https://anagora.org"
MATRIX_URL=f"https://develop.element.io"
AGORA_ROOT=os.path.expanduser("~/agora")
OUTPUT_DIR=f"{AGORA_ROOT}/stream/{AGORA_BOT_ID}"
THREAD = RelationType("m.thread")
# Probably should invest instead in not answering to *spurious* hashtags :)
HASHTAG_OPT_OUT_ROOMS = [
        '!zPwMsygFdoMjtdrDfo:matrix.org', # moa party 
        '!akkaZImONyQWKswVdt:matrix.org', # social coop tech chat
        '!aIpzDTRzEEUkMCcBay:matrix.org', # social coop open chat
        ]

class AgoraPlugin(Plugin):
    @command.passive("\[\[(.+?)\]\]", multiple=True)
    async def wikilink_handler(self, evt: MessageEvent, subs: List[Tuple[str, str]]) -> None:
        await evt.mark_read()
        self.log.info(f"responding to event: {evt}")
        response = ""
        wikilinks = []  # List of all wikilinks given by user
        for _, link in subs:
            if 'href=' in link or re.match('\[.+?\]\(.+?\)', link):
                # this wikilink is already anchored (resolved), skip it.
                continue
            else:
                # urlencode otherwise
                link = "https://anagora.org/{}".format(urllib.parse.quote_plus(link))

            wikilinks.append(link)

        if wikilinks:
            self.log.info(f"*** found wikilinks in message.")
            response = f"\n".join(wikilinks)
            if self.inThread(evt):
                # already in a thread, can't start one :)
                self.log.info(f"*** already in thread, can't start another one.")
                await evt.reply(response, allow_html=True)
            else:
                self.log.info(f"*** trying to start a thread with response.")
                # start a thread with our reply.
                content = TextMessageEventContent(
                        body=response, 
                        msgtype=MessageType.NOTICE,
                        relates_to=RelatesTo(rel_type=THREAD, event_id=evt.event_id))
                try:
                    await evt.respond(content, allow_html=True)  # Reply to user
                except errors.request.MUnknown: 
                    # works around: "cannot start threads from an event with a relation"
                    self.log.info(f"*** couldn't start a thread, falling back to regular response.")
                    await evt.reply(response, allow_html=True)
                # try to save a link to the message in the Agora.
                for wikilink in wikilinks:
                    self.log_evt(evt, wikilink)

    @command.passive(r'#(\S+)', multiple=True)
    async def hashtag_handler(self, evt: MessageEvent, subs: List[Tuple[str, str]]) -> None:
        if evt.room_id in HASHTAG_OPT_OUT_ROOMS:
            self.log.info(f"not handling hashtag due to opted out room: {evt.room_id}")
            return
        await evt.mark_read()
        self.log.info(f"responding to event: {evt}")
        response = ""
        hashtags = []  # List of all hashtags given by user
        for _, link in subs:
            link = "https://anagora.org/{}".format(urllib.parse.quote_plus(link))
            hashtags.append(link)

        if hashtags:
            self.log.info(f"*** found hashtags in message.")
            response = f"\n".join(hashtags)
            if self.inThread(evt):
                # already in a thread, can't start one :)
                self.log.info(f"*** already in thread, can't start another one.")
                await evt.reply(response, allow_html=True)
            else:
                self.log.info(f"*** trying to start a thread with response.")
                # start a thread with our reply.
                content = TextMessageEventContent(
                        body=response, 
                        msgtype=MessageType.NOTICE,
                        relates_to=RelatesTo(rel_type=THREAD, event_id=evt.event_id))
                try:
                    await evt.respond(content, allow_html=True)  # Reply to user
                except errors.request.MUnknown: 
                    # works around: "cannot start threads from an event with a relation"
                    self.log.info(f"*** couldn't start a thread, falling back to regular response.")
                    await evt.reply(response, allow_html=True)
                # try to save a link to the message in the Agora.
                for hashtag in hashtags:
                    self.log_evt(evt, hashtag)



    def inThread(self, evt):
        try:
            content = evt.content
            relates = content._relates_to
            if relates.rel_type==THREAD:
                self.log.info("*** event was already in thread")
                return True
            return False
        except:
            return False
        
    def log_evt(self, evt, node):

        # filesystems are move flexible than URLs, spaces are fine and preferred :)
        node = urllib.parse.unquote_plus(node)

        try:
            os.mkdir(OUTPUT_DIR)
        except FileExistsError:
            pass

        # unsure if it's OK inlining, perhaps fine in this case as each room does explicit setup?
        msg = evt.content.body

        # this was shamelessly copy/pasted and adapted from [[agora bridge]], mastodon bot.
        if ('/' in node):
            # for now, dump only to the last path fragment -- this yields the right behaviour in e.g. [[go/cat-tournament]]
            node = os.path.split(node)[-1]

        filename = os.path.join(OUTPUT_DIR, node + '.md')
        self.log.info(f"logging {evt} to file {filename} mapping to {node}.")

        # hack hack -- this should be enabled/disabled/configured in the maubot admin interface somehow?
        try:
            with open(filename, 'a') as note:
                username = evt.sender
                # /1000 needed to reduce 13 -> 10 digits
                dt = datetime.datetime.fromtimestamp(int(evt.timestamp/1000))
                link = f'[link]({MATRIX_URL}/#/room/{evt.room_id}/{evt.event_id})'
                # note.write(f"- [[{username}]] at {dt}: {link}\n  - ```{msg}```")
                note.write(f"- [[{dt}]] [[{username}]] ({link}):\n  - {msg}\n")
        except Exception as e:
            self.log.info(f"Couldn't save link to message, exception: {e}.")



