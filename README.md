# Agora Bridge

This repository includes a set of scripts and utilities to connect the Agora (https://anagora.org/go/agora) with the greater internet with a focus on personal knowledge graphs, the semantic web and social platforms.

Currently supports digital gardens stored on [[git]], as per https://anagora.org/agora-protocol. Support for [[mastodon]] and [[twitter]] will be worked on next.

See https://anagora.org/node/an-agora for more.

## Install

[[Install uv]] (we migrated to uv from poetry, please excuse any confusion due to outdated docs/files).

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then run the development server:
```
./run-dev.sh
```

## Usage

### Digital gardens

The following is an example for a deployment in which both agora-bridge (this repository) and agora (https://github.com/flancian/agora) are in the home directory of the same user.

```
uv run pull.py --config ~/agora/gardens.yaml --output-dir ~/agora/garden 
```

### Social media

Work is always in progress :) 

See the `bot` directory in this repository for system account code for supported platforms (some broken due to interop issues momentarily.) or read more about [[agora bridge]] in the Agora: https://anagora.org/agora-bridge.
