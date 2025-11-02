> [!IMPORTANT]
> **Branch Renaming Notice (Effective 2025-09-15)**
>
> Agora projects will migrate their default branch from `master` to `main` on or after **September, 2025**, to align with modern Git standards.
>
> Agora Server (https://github.com/flancian/agora-server) and Agora Bridge (https://github.com/flancian/agora-bridge) were already migrated. The Agora root (https://github.com/flancian/agora) and other repositories will now migrate.
>
> If you are in a master branch after the time of migration and you see no changes, please migrate to main as per the following instructions. While GitHub will automatically redirect web links, this change requires this one-time update for any local clones.
>
> Please run the following commands to update your local repository:
>
> ```bash
> # Switch to your local master branch
> git checkout master
>
> # Rename it to main
> git branch -m master main
>
> # Fetch the latest changes from the remote
> git fetch
>
> # Point your new main branch to the remote main branch
> git branch -u origin/main main
>
> # (Optional) Clean up old remote tracking branch
> git remote prune origin
> ```
>
> Thank you for your understanding as we keep the Agora aligned with current best practices!

# Agora Bridge

This repository includes a set of scripts and utilities to connect the Agora (https://anagora.org/go/agora) with the greater internet with a focus on personal knowledge graphs, the semantic web and social platforms.

Currently supports digital gardens stored on [[git]], as per https://anagora.org/agora-protocol. Support for [[mastodon]] and [[twitter]] will be worked on next.

See https://anagora.org/node/an-agora for more.

## Install

First, [[install uv]] if you haven't already (we migrated to uv from poetry, please excuse any confusion due to outdated docs/files).
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Next, create a virtual environment and install the required Python dependencies:
```bash
uv venv
uv pip install -r requirements.txt
```

## Usage

The Agora Bridge consists of several components that can be run for development.

### Garden Puller (Worker)

This script continuously pulls updates from the digital gardens configured in `~/agora/sources.yaml`.
```bash
./run-dev.sh
```

### Web Status Dashboard

This runs a Flask web server that shows the status of the bridge and the configured gardens.
```bash
./run-web-dev.sh
```

### Manual Pulling

The following is an example for a deployment in which both agora-bridge (this repository) and agora (https://github.com/flancian/agora) are in the home directory of the same user.
```bash
uv run pull.py --config ~/agora/sources.yaml --output-dir ~/agora/garden 
```

### Social Media Bots

Work is always in progress :) 

See the `bots` directory in this repository for system account code for supported platforms (some broken due to interop issues momentarily.) or read more about [[agora bridge]] in the Agora: https://anagora.org/agora-bridge.
