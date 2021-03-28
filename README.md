# Agora Bridge

A connector Agora <-> the internet with a focus on the semantic web and social platforms.

Will initially support [[mastodon]] and [[twitter]].

See https://anagora.org/node/an-agora for more.

## Install

```
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
```

## Run

The following is an example for a deployment in which both agora-bridge (this repository) and agora (https://github.com/flancian/agora) are in the home directory of the same user.

```
. venv/bin/activate
~/agora-bridge/gardens.py --config ~/agora/gardens.yaml --output-dir ~/agora/garden 
```
