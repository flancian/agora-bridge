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
