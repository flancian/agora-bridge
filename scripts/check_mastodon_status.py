#!/usr/bin/env python3
"""Helper script to verify Agora Mastodon bot status, followers, and recent replies."""

import argparse
import sys
import yaml
from mastodon import Mastodon

def main():
    parser = argparse.ArgumentParser(description="Check Mastodon bot status and recent activity.")
    parser.add_argument("--config", default="bots/mastodon/agora-bot.yaml", help="Path to config yaml.")
    parser.add_argument("--limit", type=int, default=5, help="Number of recent statuses to display.")
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    m = Mastodon(
        version_check_mode="none",
        access_token=config["access_token"],
        api_base_url=config["api_base_url"],
    )

    me = m.me()
    print(f"Logged in as: @{me.username} ({me.acct}) - {me.url}")

    followers = m.account_followers(me.id, limit=80)
    print(f"Total followers in first batch: {len(followers)}")

    print(f"\nLast {args.limit} statuses posted by @{me.username}:")
    statuses = m.account_statuses(me.id, limit=args.limit)
    for s in statuses:
        print(f"- [{s.created_at}] {s.url}")
        content_preview = s.content.replace("<p>", "").replace("</p>", "").replace("<br>", " ")
        print(f"  {content_preview[:120]}")

if __name__ == "__main__":
    main()
