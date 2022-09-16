# Agora Bridge

This repository includes a set of scripts and utilities to connect the Agora (https://anagora.org/go/agora) with the greater internet with a focus on personal knowledge graphs, the semantic web and social platforms.

Currently supports digital gardens stored on [[git]], as per https://anagora.org/agora-protocol. Support for [[mastodon]] and [[twitter]] will be worked on next.

See https://anagora.org/node/an-agora for more.

## Install

Install poetry (as per https://python-poetry.org/docs/ and https://install.python-poetry.org, this is the recommended way of installing):

```
curl -sSL  https://install.python-poetry.org | python3 -
```

Install Python dependencies:
```
poetry install
```

If you get a virtualenv-related error above, try removing virtualenv if you had installed it separately: `pip3 uninstall virtualenv`.

Then run the development server:
```
./run-dev.sh
```

## Usage

### Digital gardens

The following is an example for a deployment in which both agora-bridge (this repository) and agora (https://github.com/flancian/agora) are in the home directory of the same user.

```
. venv/bin/activate
~/agora-bridge/pull.py --config ~/agora/gardens.yaml --output-dir ~/agora/garden 
```


### Social media

Work in progress. See `bot` directory in this repository for system account code and [[agora bridge js]] in the Agora.
