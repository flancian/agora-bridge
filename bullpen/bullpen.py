import os
import time
import subprocess
import socket
import threading
import logging
import requests
import tempfile
from flask import Flask, request, Response, abort, session, redirect, url_for
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix

# Configuration
AGORA_ROOT = os.path.expanduser("~/agora/garden")
BULL_BINARY = os.path.expanduser("~/go/bin/bull") 
PORT_RANGE_START = 6000
PORT_RANGE_END = 7000
IDLE_TIMEOUT_SECONDS = 600 # 10 minutes
ASSET_USER = '_assets'

# Auth Config
CLIENT_ID = os.environ.get('AGORA_OAUTH_CLIENT_ID')
CLIENT_SECRET = os.environ.get('AGORA_OAUTH_CLIENT_SECRET')
SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'dev_key_please_change')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("bullpen")

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.secret_key = SECRET_KEY

# OAuth Setup
oauth = OAuth(app)
if CLIENT_ID and CLIENT_SECRET:
    oauth.register(
        name='forgejo',
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        api_base_url='https://git.anagora.org/api/v1/',
        access_token_url='https://git.anagora.org/login/oauth/access_token',
        authorize_url='https://git.anagora.org/login/oauth/authorize',
        client_kwargs={'scope': 'read:user'},
    )
else:
    logger.warning("OAuth credentials not found. Auth will be disabled/broken.")


class BullInstance:
    def __init__(self, username, port, custom_path=None):
        self.username = username
        self.port = port
        self.process = None
        self.last_active = time.time()
        self.custom_path = custom_path

    def start(self):
        garden_path = self.custom_path if self.custom_path else os.path.join(AGORA_ROOT, self.username)
        
        if not os.path.isdir(garden_path):
            if self.username == ASSET_USER:
                 os.makedirs(garden_path, exist_ok=True)
            else:
                 raise FileNotFoundError(f"Garden not found for {self.username}")

        root_arg = f"-root=/@{self.username}"
        if self.username == ASSET_USER:
            root_arg = "-root=/"

        cmd = [BULL_BINARY, "-content", garden_path, "serve", f"-listen=127.0.0.1:{self.port}", root_arg]
        logger.info(f"Starting bull for {self.username} on port {self.port}: {' '.join(cmd)}")
        
        # Start detached process
        self.process = subprocess.Popen(cmd)
        
        # Wait for port to be open
        retries = 20
        while retries > 0:
            if self.is_port_open():
                return
            time.sleep(0.1)
            retries -= 1
        
        self.stop()
        raise RuntimeError(f"Bull failed to start for {self.username}")

    def stop(self):
        if self.process:
            logger.info(f"Stopping bull for {self.username} (PID {self.process.pid})")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

    def is_port_open(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', self.port)) == 0

    def touch(self):
        self.last_active = time.time()

# Global Registry
instances = {} # username -> BullInstance
instances_lock = threading.Lock()
used_ports = set()

def get_free_port():
    for port in range(PORT_RANGE_START, PORT_RANGE_END):
        if port not in used_ports:
            # Double check it's actually free on the OS
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('127.0.0.1', port)) != 0:
                    return port
    raise RuntimeError("No free ports in Bullpen!")

def get_or_create_instance(username):
    with instances_lock:
        if username in instances:
            instance = instances[username]
            if instance.process and instance.process.poll() is None:
                instance.touch()
                return instance
            else:
                # Process died, restart
                logger.warning(f"Process for {username} died, restarting...")
                instance.stop() # Cleanup
                if instance.port in used_ports: used_ports.remove(instance.port)
                del instances[username]

        # New instance
        port = get_free_port()
        used_ports.add(port)
        instance = BullInstance(username, port)
        try:
            instance.start()
            instances[username] = instance
            return instance
        except Exception as e:
            used_ports.remove(port)
            raise e

def ensure_asset_instance():
    """Ensures the special _assets instance is running."""
    with instances_lock:
        if ASSET_USER in instances:
            inst = instances[ASSET_USER]
            if inst.process and inst.process.poll() is None:
                return # Already running
            else:
                inst.stop()
                if inst.port in used_ports: used_ports.remove(inst.port)
                del instances[ASSET_USER]

        # Create temp dir for assets
        asset_dir = os.path.join(tempfile.gettempdir(), 'agora_bull_assets')
        os.makedirs(asset_dir, exist_ok=True)
        
        port = get_free_port()
        used_ports.add(port)
        instance = BullInstance(ASSET_USER, port, custom_path=asset_dir)
        try:
            instance.start()
            instances[ASSET_USER] = instance
            logger.info(f"Started asset instance on port {port}")
        except Exception as e:
            used_ports.remove(port)
            logger.error(f"Failed to start asset instance: {e}")

def reaper_loop():
    while True:
        # Ensure asset instance is alive every loop
        try:
            ensure_asset_instance()
        except Exception as e:
            logger.error(f"Error checking asset instance: {e}")

        time.sleep(60)
        now = time.time()
        with instances_lock:
            to_remove = []
            for username, instance in instances.items():
                if username == ASSET_USER:
                    continue # Never reap the asset instance

                if now - instance.last_active > IDLE_TIMEOUT_SECONDS:
                    logger.info(f"Reaping idle instance for {username}")
                    instance.stop()
                    if instance.port in used_ports: used_ports.remove(instance.port)
                    to_remove.append(username)
            
            for username in to_remove:
                del instances[username]

# Start reaper in background
reaper_thread = threading.Thread(target=reaper_loop, daemon=True)
reaper_thread.start()

# Initial asset instance start
ensure_asset_instance()

@app.route('/login')
def login():
    if not CLIENT_ID:
        return "OAuth not configured", 500
    redirect_uri = url_for('auth_callback', _external=True)
    logger.info(f"Initiating OAuth login with redirect_uri: {redirect_uri}")
    return oauth.forgejo.authorize_redirect(redirect_uri)

@app.route('/auth/callback')
def auth_callback():
    token = oauth.forgejo.authorize_access_token()
    resp = oauth.forgejo.get('user', token=token)
    user_info = resp.json()
    username = user_info.get('username') or user_info.get('login')
    
    if username:
        session['user'] = username
        return redirect(f"/@{username}/")
    return "Failed to fetch user info", 400

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

@app.route('/')
def index():
    with instances_lock:
        active_users = list(instances.keys())
    
    current_user = session.get('user')
    
    html = """
    <html>
    <head><title>Agora Bullpen</title></head>
    <body style="font-family: sans-serif; padding: 2rem;">
        <div style="float: right;">
    """
    
    if current_user:
        html += f"""
        Logged in as <strong>{current_user}</strong> | 
        <a href="https://git.anagora.org/" target="_blank">Forge 🔨</a> | 
        <a href='/logout'>Logout</a>
        """
    else:
        html += """
        <a href="https://git.anagora.org/" target="_blank">Forge 🔨</a> | 
        <a href='/login'>Login with Agora Git</a>
        """
        
    html += """
        </div>
        <h1>🐂 Agora Bullpen</h1>
        <p>The Bullpen manages active editor instances.</p>
        
        <h3>Active Instances</h3>
        <ul>
    """
    
    if active_users:
        for user in active_users:
            if user == ASSET_USER: continue
            html += f'<li><a href="/@{user}/">@{user}</a></li>'
    else:
        html += "<li><em>No active user instances.</em></li>"
        
    html += """
        </ul>
        <hr>
        <p><small>Powered by <a href="https://github.com/flancian/agora-bridge">Agora Bridge</a></small></p>
    </body>
    </html>
    """
    return html

@app.route('/_bull/<path:path>', methods=["GET"])
def proxy_bull_assets(path):
    # Always prefer the dedicated asset instance
    instance = None
    with instances_lock:
        instance = instances.get(ASSET_USER)
        # Fallback to any other instance if asset instance is dead (shouldn't happen)
        if not instance and instances:
            instance = max(instances.values(), key=lambda i: i.last_active)
    
    if not instance:
        return "No active bull instances to serve assets", 404

    target_url = f"http://127.0.0.1:{instance.port}/_bull/{path}"
    if request.query_string:
        target_url += f"?{request.query_string.decode('utf-8')}"

    logger.info(f"Proxying asset {request.method} {request.full_path} -> {target_url}")

    try:
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers={k:v for k,v in request.headers if k.lower() != 'host'},
            allow_redirects=False,
            stream=True
        )
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for (name, value) in resp.raw.headers.items()
                   if name.lower() not in excluded_headers]
        return Response(resp.content, resp.status_code, headers)
    except Exception as e:
        logger.error(f"Asset proxy error: {e}")
        return "Asset Proxy Error", 502

@app.route('/@<username>/', defaults={'path': ''}, methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@app.route('/@<username>/<path:path>', methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def proxy(username, path):
    # Auth Check
    # Allow asset user (internal) explicitly if needed, but usually it's not accessed via this route
    if username != ASSET_USER:
        if 'user' not in session:
            return redirect('/login')
        if session['user'] != username:
            html = f"""
            <html>
            <head><title>Access Denied</title></head>
            <body style="font-family: sans-serif; padding: 2rem; text-align: center;">
                <h1 style="color: red;">🚫 Access Denied</h1>
                <p>You are logged in as <strong>@{session['user']}</strong>.</p>
                <p>You do not have permission to edit <strong>@{username}</strong>'s garden.</p>
                
                <hr style="margin: 2rem 0;">
                
                <div style="display: flex; gap: 20px; justify-content: center;">
                    <a href="/@{session['user']}/" style="background: #4CAF50; color: white; padding: 10px 15px; text-decoration: none; border-radius: 4px;">Go to My Garden 🐂</a>
                    <a href="/" style="background: #2196F3; color: white; padding: 10px 15px; text-decoration: none; border-radius: 4px;">Bullpen Home 🏠</a>
                    <a href="/logout" style="background: #f44336; color: white; padding: 10px 15px; text-decoration: none; border-radius: 4px;">Logout 🚪</a>
                </div>
            </body>
            </html>
            """
            return html, 403

    # Validation
    if not username or username not in os.listdir(AGORA_ROOT):
         return "User garden not found", 404

    try:
        instance = get_or_create_instance(username)
    except Exception as e:
        logger.error(f"Failed to provision: {e}")
        return "Failed to start editor", 500

    # We must include the /@username prefix because bull is started with -root=/@username
    target_url = f"http://127.0.0.1:{instance.port}/@{username}/{path}"
    if request.query_string:
        target_url += f"?{request.query_string.decode('utf-8')}"

    logger.info(f"Proxying {request.method} {request.full_path} -> {target_url}")

    # Proxy Logic
    try:
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers={k:v for k,v in request.headers if k.lower() != 'host'},
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            stream=True # Streaming for files
        )

        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for (name, value) in resp.raw.headers.items()
                   if name.lower() not in excluded_headers]

        return Response(resp.content, resp.status_code, headers)
    except Exception as e:
        logger.error(f"Proxy error: {e}")
        return "Proxy Error", 502

if __name__ == '__main__':
    # Run locally on 5019
    app.run(host='127.0.0.1', port=5019)
