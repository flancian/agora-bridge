# Gemini's Understanding of Agora Bridge (as of 2025-10-31)

This document summarizes my understanding of the `agora-bridge` project based on an initial code review.

## Project Summary

The `agora-bridge` is a collection of scripts and services that connect an Agora to the wider internet. It has two primary functions:

1.  **Content Aggregation**:
    *   `pull.py`: The main worker script. It reads a YAML configuration to find digital gardens (Git repositories, FedWikis) and pulls them into a local cache for the `agora-server`.
    *   `feed.py`: A script for pulling content from Atom/RSS feeds, currently focused on Hypothes.is.

2.  **Social Media Integration (Bots)**: The project runs bots on multiple social platforms (Mastodon, Twitter, Bluesky, Matrix). These bots act as a two-way bridge:
    *   **Listen**: They monitor posts and messages for `[[wikilinks]]` and `#hashtags`.
    *   **Reply**: They respond with links back to the relevant nodes in the Agora, making the Agora a dynamic, conversational knowledge base.
    *   **Log**: They save links to these social media conversations (and sometimes the full content, if users opt-in) as subnodes within the Agora, enriching the nodes with timely, real-world context.

The overall architecture is a consistent pattern of listening, replying, and logging, tailored to the specific APIs of each social network.

## Next Steps

Our initial projects for `agora-bridge` will be:

1.  **Create a Flask API**: Develop a new Flask application, similar in spirit to `agora-server`, but focused on providing an API for managing user repositories (gardens) and other utility functions. This application will eventually serve as a dashboard to show the status of the bridge's processes, garden health (e.g., last update status), and other metrics.
2.  **Consolidate Environment Management**: Unify the project's Python environment management. The current mix of virtual environments will be rationalized, likely by adopting `uv` consistently across all components.
3.  **Improve `pull.py`**: Enhance the main `pull.py` worker script with better error handling, logging, and performance.

## Future Work (as of 2025-11-02)

With the initial setup and environment consolidation complete, here are the recommended next steps:

1.  **Refactor Bot Scripts for Consistent Execution**:
    *   **What**: Modify the bot scripts in `bots/` so they can all be run from the project root, resolving the inconsistency where some scripts must be run from their own subdirectories.
    *   **Why**: This is the top recommendation. It will simplify the development workflow, make the project less error-prone, and remove the major inconsistency we identified and had to document in the `README.md`.

2.  **Improve the `pull.py` Worker**:
    *   **What**: Enhance the core worker with more robust error handling, better logging (perhaps integrated with the web UI), and improved performance.
    *   **Why**: As the main content aggregation engine, making `pull.py` more reliable and observable is a high-impact improvement for the whole system.

3.  **Enhance the Web Status Page**:
    *   **What**: Add more features, such as health indicators for each garden (green/red dots), status/heartbeats for running bot processes, or more detailed error messages.
    *   **Why**: This would turn the dashboard into a more powerful, at-a-glance monitoring tool for the entire bridge.
