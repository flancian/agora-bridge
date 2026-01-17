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

## Hosted Gardens

We have integrated with **Forgejo** (`git.anagora.org`) to offer hosted digital gardens for users who don't have their own infrastructure.

**Workflow:**
1.  User selects "Host me" in the Agora Server UI.
2.  Server requests provisioning from the Bridge (`POST /provision`).
3.  Bridge uses the Forgejo API (via `api/forgejo.py`) to create a user/repo on `git.anagora.org`.
4.  Bridge adds the new repo to `sources.yaml` and starts tracking it.

**Configuration:**
To enable this, the Bridge needs the following environment variables:
*   `AGORA_FORGEJO_URL`: The API URL (e.g., `https://git.anagora.org/api/v1`).
*   `AGORA_FORGEJO_TOKEN`: An admin access token with `sudo` scope.

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

## Core Processes & Workers

An Agora Bridge is composed of several long-running processes or workers. The following scripts, located in the project root, are the canonical way to run them.

It is recommended to run each of these in a separate terminal or using a process manager like `systemd` or `supervisor` in production.

### 1. Pull Worker

This is the main content aggregation engine. It reads your garden configurations (e.g., `~/agora/sources.yaml`) and pulls updates from them into the Agora.

-   **Run in Development:**
    ```bash
    ./run-dev.sh
    ```
-   **Run in Production:**
    ```bash
    ./run-prod.sh
    ```

### 2. API Dashboard

This runs a Flask web application that provides a status dashboard, showing the health of configured gardens and the state of the Agora database.

-   **Run in Development:**
    ```bash
    ./run-api-dev.sh
    ```
-   **Run in Production:**
    ```bash
    # (A production script for the API will be added in the future)
    ```

### 3. Social Media Bots

These bots listen for activity on social platforms, reply to mentions of `[[wikilinks]]`, and log conversations back into the Agora. Before running a bot for the first time, you must copy its `.yaml.example` configuration file to `.yaml` and fill in your credentials.

**Mastodon Bot**
-   **Config:** `bots/mastodon/agora-bot.yaml`
-   **Run in Development:** `./run-mastodon-bot-dev.sh`
-   **Run in Production:** `./run-mastodon-bot-prod.sh`

**Bluesky Bot**
-   **Config:** `bots/bluesky/agora-bot.yaml`
-   **Run in Development:** `./run-bluesky-bot-dev.sh`
-   **Run in Production:** `./run-bluesky-bot-prod.sh`

**Twitter Bot**
-   **Config:** `bots/twitter/agora-bot.yaml`
-   **Run in Development:** `./run-twitter-bot-dev.sh`
-   **Run in Production:** `./run-twitter-bot-prod.sh`

### 4. Feed Puller

The `feed.py` script pulls content from Atom/RSS feeds, currently focused on Hypothes.is annotations.

-   **Run Manually:**
    ```bash
    uv run python feed.py
    ```

### Social Media Bots

Work is always in progress :) 

See the `bots` directory in this repository for system account code for supported platforms (some broken due to interop issues momentarily.) or read more about [[agora bridge]] in the Agora: https://anagora.org/agora-bridge.
