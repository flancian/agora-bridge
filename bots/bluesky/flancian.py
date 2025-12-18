#!/usr/bin/env python3

from atproto import Client

client = Client(base_url='https://bsky.social')
client.login('flancia.org', 'bluesky in flancia')

post = client.send_post('Hello world! I posted this via the Bluesky API: https://docs.bsky.app/docs/get-started :)')
print(post)

