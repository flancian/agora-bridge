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

## The Agora Protocol

The Agora Protocol is not a formal network protocol, but rather a set of core principles that guide the project's design:

-   **Decentralization**: The filesystem is the ultimate source of truth. The server is a lens, not a silo.
-   **Nodes are Concepts, Subnodes are Utterances**: A key distinction where abstract topics (`[[Calculus]]`) are composed of concrete contributions (`@flancian/calculus.md`).
-   **Composition over Centralization**: Nodes are built by pulling and combining content from other, more specialized nodes.
-   **Everything Has a Place (No 404s)**: Every possible query resolves to a node, turning dead ends into invitations to contribute.

## Development Setup

This project uses `uv` for environment and package management. All dependencies are defined in `pyproject.toml`.

**1. Install `uv`**

If you don't have it, install it with the official script:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**2. Create the Virtual Environment**
```bash
uv venv
```

**3. Install Dependencies**

To install all core and optional (bots) dependencies for development, run:
```bash
uv pip install -r requirements.txt
```
> **How does this work?** The `requirements.txt` file contains a single line, `-e .[all]`, which tells `uv` to install the project in editable mode (`-e .`) and to include all the optional dependency groups defined in `pyproject.toml` (`[all]`).

If you only need to work on a specific component, you can install its dependencies directly. For example, to install only the core bridge and the Mastodon bot:
```bash
uv pip install -e .[mastodon]
```

## Running the Bridge

This project currently has two conventions for running scripts. Please check below to see where to run each command.

### Running from the Project Root

The main worker, the web application, and other root-level scripts should be run from the root of the `agora-bridge` project.

**Garden Puller (Worker):**
```bash
# from /home/flancian/agora-bridge/
./run-dev.sh
```

**Web Status Dashboard:**
```bash
# from /home/flancian/agora-bridge/
./run-web-dev.sh
```

### Running the Bots

The easiest way to run the bots is to use the provided wrapper scripts from the project root. These scripts ensure the bots are run with the correct paths to their configurations.

**Example (Mastodon Bot):**
Before running for the first time, you'll need to set up your configuration:
```bash
cp bots/mastodon/agora-bot.yaml.example bots/mastodon/agora-bot.yaml
# ...then edit bots/mastodon/agora-bot.yaml with your credentials...
```

Then, you can run the bot with:
```bash
# from /home/flancian/agora-bridge/
./run-mastodon-bot.sh --catch-up
```
Any arguments you add (like `--catch-up` or `--dry-run`) are passed directly to the bot script. The same pattern applies to the Bluesky bot (`./run-bluesky-bot.sh`).

### Social Media Bots

Work is always in progress :) 

See the `bots` directory in this repository for system account code for supported platforms (some broken due to interop issues momentarily.) or read more about [[agora bridge]] in the Agora: https://anagora.org/agora-bridge.
