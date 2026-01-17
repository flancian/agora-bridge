# The Agora Bullpen 🐂

The **Bullpen** is a multi-tenant proxy manager that enables the [Agora](https://anagora.org) to offer a web-based editing experience for hosted digital gardens.

It leverages [**bull**](https://github.com/gokrazy/bull), a lightweight Gemini/Web editor/server, to provide a clean, Markdown-native editing interface. The Bullpen manages these `bull` instances on demand, authenticating users via the Agora's Forgejo instance.

## Architecture

The Bullpen (`bullpen.py`) sits between the user (via Nginx) and the individual editor instances.

1.  **Incoming Request:** Users visit `edit.anagora.org`.
2.  **Authentication:** Users are authenticated via **Forgejo OAuth2**. If not logged in, `bullpen.py` redirects the user to `git.anagora.org` (Forgejo). This is fully implemented and is the primary security layer.
3.  **Provisioning:** Once authenticated (e.g., as user `flancian`), the Bullpen checks if a `bull` process is already running for that user.
    *   If **yes**: It proxies the request to the existing process.
    *   If **no**: It spawns a new `bull` process on a free port (range 6000-7000), rooted at the user's garden directory (e.g., `~/agora/garden/flancian`), and then proxies the request.
4.  **Proxying:** All subsequent requests (GET, POST, etc.) are proxied transparently to the user's dedicated `bull` instance.
5.  **Reaping:** A background thread monitors activity and shuts down idle `bull` instances after 10 minutes to save resources.

## Prerequisites

*   **Python 3.10+** (managed via `uv` is recommended).
*   **Go 1.21+** (to build `bull`).
*   **Forgejo Application:** You need to register an OAuth2 application on your Forgejo instance (`git.anagora.org`).
    *   **Callback URL:** `https://edit.anagora.org/auth/callback`

## Installation

### 1. Install Bull

Use the helper script to download and build the `bull` binary:

```bash
cd agora-bridge/bullpen
./setup_bull.sh
```

This will install the binary to `~/go/bin/bull`.

### 2. Configure Environment

Create a `.env` file or set the following environment variables:

```bash
export AGORA_OAUTH_CLIENT_ID="your-forgejo-client-id"
export AGORA_OAUTH_CLIENT_SECRET="your-forgejo-client-secret"
export FLASK_SECRET_KEY="a-secure-random-string"
```

You may also need to adjust `AGORA_ROOT` in `bullpen.py` if your garden is not at `~/agora/garden`.

## Running the Service

You can run the Bullpen directly with `uv` (or `python`):

```bash
# From agora-bridge directory
uv run bullpen/bullpen.py
```

### Systemd Service (Recommended)

Create `~/.config/systemd/user/agora-bullpen.service`:

```ini
[Unit]
Description=Agora Bullpen (Multi-tenant Editor Proxy)
After=network.target

[Service]
WorkingDirectory=%h/agora-bridge
Environment="AGORA_OAUTH_CLIENT_ID=..."
Environment="AGORA_OAUTH_CLIENT_SECRET=..."
Environment="FLASK_SECRET_KEY=..."
ExecStart=%h/.local/bin/uv run bullpen/bullpen.py
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

Enable and start:
```bash
systemctl --user enable --now agora-bullpen
```

## Nginx Configuration

The Bullpen runs on `localhost:5019`. Use Nginx to expose it to the world (e.g., at `edit.anagora.org`).

```nginx
server {
    server_name edit.anagora.org;
    listen 80;
    # listen 443 ssl; # Ensure you configure SSL (Certbot recommended)

    location / {
        proxy_pass http://127.0.0.1:5019;
        
        # Standard Headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (if needed by Bull)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## User Experience

1.  **Sign Up:** A user joins the Agora via the "Join" flow, which provisions a repo on `git.anagora.org` and a folder in `~/agora/garden/`.
2.  **Edit:** The user navigates to `edit.anagora.org`.
3.  **Login:** They log in with their Forgejo credentials.
4.  **Editor:** They see a file list of their garden. Clicking a file opens the `bull` editor. Changes are saved directly to the disk.
5.  **Sync:** The Agora's `pull.py` loop (or a git hook) commits and pushes these changes back to the remote repo, keeping everything in sync.
