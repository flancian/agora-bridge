#!/usr/bin/env python3
import getpass
from mastodon import Mastodon

print("Agora Bot Mastodon Token Generator")
print("==================================")

api_base_url = input("Enter instance URL (e.g., https://social.agor.ai): ").strip()
email = input("Enter bot email (e.g., agora@social.agor.ai): ").strip()
password = getpass.getpass("Enter bot password: ")

# Register app (if needed, but usually we just want to login)
# We'll assume the client_id/secret are valid if you have them,
# otherwise we can register a new app.

client_id = input("Enter Client ID (leave blank to register a new app): ").strip()
client_secret = input("Enter Client Secret (leave blank to register a new app): ").strip()

if not client_id or not client_secret:
    print("\nRegistering new app 'Agora Bot'...")
    client_id, client_secret = Mastodon.create_app(
        'agora-bot',
        api_base_url=api_base_url,
        to_file=None 
    )
    print(f"New Client ID: {client_id}")
    print(f"New Client Secret: {client_secret}")
    print("SAVE THESE to your agora-bot.yaml!\n")

mastodon = Mastodon(
    client_id=client_id,
    client_secret=client_secret,
    api_base_url=api_base_url
)

print(f"Logging in as {email}...")
try:
    token = mastodon.log_in(
        email,
        password,
        to_file=None 
    )
    print("\nSUCCESS! Here is your new access token:")
    print("----------------------------------------")
    print(token)
    print("----------------------------------------")
    print("Update 'access_token' in bots/mastodon/agora-bot.yaml with this value.")

except Exception as e:
    print(f"\nLogin failed: {e}")
