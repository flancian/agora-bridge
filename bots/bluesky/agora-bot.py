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
# match hashtags at start of line or preceded by whitespace
HASHTAG_RE = re.compile(r'(?:^|\s)#(\w+)', re.IGNORECASE)
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
        self.session_file = 'bsky_session.txt'
        self.login()

        self.me = self.client.resolve_handle(self.config['user'])
        self.last_reply_time = 0

    def login(self):
        # Try to load existing session
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, 'r') as f:
                    session_string = f.read().strip()
                
                # Try newer API first, then fallback
                try:
                    self.client.login(reuse_session_string=session_string)
                except TypeError:
                    self.client.login(session_string=session_string)
                    
                L.info("Successfully resumed Bluesky session.")
                return
            except Exception as e:
                L.warning(f"Could not resume Bluesky session: {e}. Logging in with password...")

        # Fallback to password login
        try:
            self.client.login(self.config['user'], self.config['password'])
            # Save session for next time
            session_string = self.client.export_session_string()
            with open(self.session_file, 'w') as f:
                f.write(session_string)
            L.info("Logged in to Bluesky with password and saved session.")
        except Exception as e:
            L.error(f"Failed to log in to Bluesky: {e}")
            raise e

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

    def prune_follows(self):
        followers = self.get_followers()
        follows = self.get_follows()
        
        # Safety check: if we somehow got 0 followers but have many follows, abort to prevent mass unfollow.
        # Assuming we should have at least 1 follower if we have > 10 follows.
        if len(followers) == 0 and len(follows) > 10:
            L.warning("Safety stop: Get 0 followers but have > 10 follows. Skipping prune to prevent accidents.")
            return

        # Map DID -> Handle for followers
        follower_dids = {f.did for f in followers}
        
        L.info(f"Checking {len(follows)} follows for prune candidates (people who don't follow us back)...")
        
        for follow in follows:
            if follow.did not in follower_dids:
                L.info(f'-> Pruning {follow.handle} (does not follow us)')
                if args.write:
                    try:
                        # For unfollowing, we need the URI of the 'follow' record.
                        if follow.viewer and follow.viewer.following:
                            self.client.delete_follow(follow.viewer.following)
                            L.info(f"Successfully unfollowed {follow.handle}")
                            # Sleep a bit to be nice to the API
                            time.sleep(1.0)
                        else:
                            L.warning(f"Could not find follow record URI for {follow.handle}, skipping.")

                    except Exception as e:
                        L.error(f"Error unfollowing {follow.handle}: {e}")
                else:
                    L.info(f"[Dry Run] Would unfollow {follow.handle}")

    def has_opted_in(self, did):
        # Check if the user has opted in to advanced features (like hashtags) via their bio.
        try:
            profile = self.client.get_profile(did)
            if profile.description and ('#agora' in profile.description.lower() or '[[agora]]' in profile.description.lower()):
                return True
        except Exception as e:
            L.warning(f"Could not fetch profile for {did}: {e}")
        return False

    def check_notifications(self):
        L.info("Checking notifications...")
        try:
            # Fetch unread notifications
            # Use lower level API if list_notifications is missing from Client
            response = self.client.app.bsky.notification.list_notifications(params={'limit': 20})
            for notif in response.notifications:
                if not notif.is_read:
                    # Mark as read immediately to avoid processing loops
                    self.client.app.bsky.notification.update_seen({'seen_at': datetime.now(timezone.utc).isoformat()})
                    
                    if notif.reason == 'mention':
                        post = notif.record
                        author = notif.author
                        L.info(f"Mentioned by {author.handle}: {post.text}")
                        
                        if 'help' in post.text.lower():
                            help_msg = (
                                "I am an Agora Bot. I bridge your knowledge to the Agora.\n"
                                "- I reply to [[wikilinks]] if you follow me.\n"
                                "- I reply to #hashtags if you verify by adding #agora to your bio."
                            )
                            # Reply to the mention
                            try:
                                root = models.create_strong_ref(notif) # actually need post view?
                                # notif.record is the record, not the view.
                                # construct reply ref manually?
                                # easier: fetch the post view.
                                # But we have the URI and CID in notif.
                                parent = models.ComAtprotoRepoStrongRef.Main(cid=notif.cid, uri=notif.uri)
                                root = parent # Simplification for single-level reply
                                
                                # Send reply
                                self.client.send_post(text=help_msg, reply_to=models.AppBskyFeedPost.ReplyRef(parent=parent, root=root))
                                L.info(f"Sent help message to {author.handle}")
                            except Exception as e:
                                L.error(f"Failed to reply to help mention: {e}")

        except Exception as e:
            L.error(f"Error checking notifications: {e}")

    def catch_up(self):
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=args.catch_up_days)

        # Iterate over items (did, handle)
        for mutual_did, handle in self.get_mutuals().items():
            L.info(f'-> Processing posts by {handle} ({mutual_did})...')
            
            opted_in = self.has_opted_in(mutual_did)
            
            try:
                # Use get_author_feed (AppView) instead of listRecords (PDS) for better federation support
                feed_response = self.client.get_author_feed(actor=mutual_did, limit=100)
            except Exception as e:
                # Handle "Could not find repo" or other 400 errors gracefully
                if 'status_code=400' in str(e) or 'Could not find repo' in str(e):
                    L.warning(f"Feed fetch failed for {handle} ({mutual_did}). Full error: {e}")
                else:
                    L.error(f"Error fetching feed for {handle} ({mutual_did}): {e}")
                continue

            for item in feed_response.feed:
                post = item.post
                record = post.record # This is the actual post data (text, createdAt)
                uri = post.uri
                
                try:
                    # indexed_at is on the post view, but createdAt is in the record. 
                    # record.created_at is the client-reported time.
                    # We can use post.indexed_at (server time) if available, or record.created_at.
                    # post.indexed_at is a string ISO timestamp.
                    timestamp_str = post.indexed_at or record.created_at
                    if not timestamp_str:
                        continue

                    post_date = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                except (ValueError, TypeError, AttributeError):
                    continue
                
                if post_date < cutoff_date:
                    # Skip old posts
                    continue

                # Check text in the record
                if not hasattr(record, 'text'):
                    continue

                wikilinks = WIKILINK_RE.findall(record.text)
                all_entities = wikilinks
                
                if opted_in:
                    hashtags = HASHTAG_RE.findall(record.text)
                    all_entities += hashtags
                
                if all_entities:
                    entities = uniq(all_entities)
                    L.info(f'\nSaw entities at {uri} ({timestamp_str}):\n{record.text}\n')
                    msg = self.build_reply(entities)
                    L.info(f'\nWould respond with:\n{msg.build_text()}\n--\n')
                    
                    # We already have the 'actual_post' object (it's 'post'), so we can pass it directly
                    # providing it matches what maybe_reply expects (models.AppBskyFeedDefs.PostView)
                    # The previous code fetched it again using get_posts, but maybe_reply calls 
                    # models.create_strong_ref(post). create_strong_ref accepts PostView.
                    try:
                        self.maybe_reply(uri, post, msg, entities)
                    except Exception as e:
                        L.error(f"Error fetching/processing post details: {e}")
            
            L.debug(f"Finished processing {mutual_did}.")

def main():
    # How much to sleep between runs, in seconds (this may go away once we're using a subscription model?).
    sleep = 60

    try:
        bot = AgoraBot()
    except Exception as e:
        L.error(f"Failed to initialize bot: {e}")
        return

    while True:
        try:
            L.info("Starting new iteration...")
            bot.check_notifications()
            bot.follow_followers()
            bot.prune_follows()
            bot.catch_up()
        except Exception as e:
            L.error(f"Error during bot iteration: {e}")
            # If it's a session error, we might want to force a re-login
            if "session" in str(e).lower() or "auth" in str(e).lower():
                L.info("Attempting to re-login due to suspected session error...")
                try:
                    bot.login()
                except Exception as login_error:
                    L.error(f"Re-login failed: {login_error}")

        L.info(f'-> Sleeping for {sleep} seconds...')
        time.sleep(sleep)

if __name__ == "__main__":
    main()
