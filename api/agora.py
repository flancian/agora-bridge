from flask import Flask, render_template, Blueprint, request, jsonify, current_app
import yaml
import os
import subprocess
import sqlite3
import secrets
import string
from datetime import datetime
from .forgejo import ForgejoClient

bp = Blueprint('agora', __name__)

# The SSH public key for the agora-bridge user on the production server (thecla).
# This key is added to every hosted garden to allow the bridge to push changes (e.g. from the Bullpen editor).
AGORA_BRIDGE_DEPLOY_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIL96izEnhC5x8l9dt6DNjidNij/kDwb4ILmZxZ4des65 agora@thecla"

def get_source_last_updated(source):
    """
    Gets the last updated time for a source by constructing the path
    from the Agora root and the source's target.
    """
    agora_path = os.path.expanduser('~/agora')
    target_path = os.path.join(agora_path, source.get('target', ''))

    if not os.path.isdir(target_path):
        return f"Directory not found at: {target_path}"

    if source.get('format') == 'git' or source.get('format') == 'foam': # Treat foam as git for this purpose
        try:
            if not os.path.isdir(os.path.join(target_path, '.git')):
                return f"Not a git repository"

            result = subprocess.run(
                ['git', '-C', target_path, 'log', '-1', '--format=%cd', '--date=iso'],
                capture_output=True, text=True, check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            return f"Git error: {e.stderr.strip()}"
        except FileNotFoundError:
            return "Git command not found"
    else:
        # Fallback for non-git formats like fedwiki, logseq
        try:
            mtime = os.path.getmtime(target_path)
            return datetime.fromtimestamp(mtime).isoformat()
        except OSError as e:
            return f"File error: {e}"

def get_db_info():
    """Gets high-level information from the agora.db sqlite file."""
    db_path = os.path.expanduser('~/agora/agora.db')
    if not os.path.exists(db_path):
        return None

    db_info = {'path': db_path, 'stats': []}
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        for table_name in tables:
            table_name = table_name[0]
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            db_info['stats'].append({'table': table_name, 'rows': count})
        
        conn.close()
        return db_info
    except sqlite3.Error as e:
        db_info['error'] = f"Database error: {e}"
        return db_info


@bp.route('/')
def index():
    """Displays the main status page and a list of available API endpoints."""
    sources = []
    error_message = None
    config_path = os.path.expanduser('~/agora/sources.yaml')

    try:
        with open(config_path, 'r') as f:
            sources_config = yaml.safe_load(f)
            if sources_config:
                for source in sources_config:
                    source['last_updated'] = get_source_last_updated(source)
                    sources.append(source)
                
                # Sort sources by last_updated, putting errors last.
                sources.sort(
                    key=lambda s: (s['last_updated'][0].isdigit(), s['last_updated']),
                    reverse=True
                )

    except FileNotFoundError:
        error_message = f"Configuration file not found at {config_path}. Please ensure it exists. You can use 'gardans.yaml.example' as a template."
    except yaml.YAMLError as e:
        error_message = f"Error parsing YAML file at {config_path}: {e}"

    db_info = get_db_info()

    # Generate list of endpoints
    endpoints = []
    for rule in current_app.url_map.iter_rules():
        if rule.endpoint != 'static':
            methods = ', '.join(sorted([m for m in rule.methods if m not in ['OPTIONS', 'HEAD']]))
            
            view_func = current_app.view_functions[rule.endpoint]
            doc = view_func.__doc__
            
            description = "No description."
            params_str = ""
            
            if doc:
                lines = [line.strip() for line in doc.strip().split('\n')]
                description = lines[0]
                
                # Look for a 'Parameters:' section in the docstring
                try:
                    params_index = lines.index("Parameters:")
                    params_list = lines[params_index+1:]
                    params_str = '\n'.join(params_list)
                except ValueError:
                    params_str = "None" # No 'Parameters:' section found

            # Add path arguments to the parameters string
            path_params = [arg for arg in rule.arguments]
            if path_params:
                path_param_str = "Path:\n" + '\n'.join([f"- {p}" for p in path_params])
                if params_str != "None":
                    params_str = path_param_str + "\n\n" + params_str
                else:
                    params_str = path_param_str

            if not params_str:
                params_str = "None"

            endpoints.append({
                'path': rule.rule,
                'methods': methods,
                'description': description,
                'parameters': params_str
            })

    return render_template(
        'index.html',
        title='Agora Bridge Status',
        sources=sources,
        db_info=db_info,
        error_message=error_message,
        endpoints=endpoints
    )

@bp.route('/sources', methods=['POST'])
def add_source():
    """
    Adds a new source to the sources.yaml file.

    Parameters:
    JSON Payload:
    - url (string, required): The URL of the source repository.
    - target (string, required): The slug/name of the source.
    - type (string, required): The type of the source ('garden' or 'stoa'). Used as path prefix.
    - format (string, optional): The format of the source (e.g., 'git', 'fedwiki'). Defaults to 'git'.
    - web (string, optional): The URL template for viewing the rendered page.
    - message (string, optional): A reason for joining or message to the admins.
    """
    if not request.json or 'url' not in request.json or 'target' not in request.json or 'type' not in request.json:
        return jsonify({'error': 'Invalid request. JSON payload with "url", "target" and "type" is required.'}), 400

    source_type = request.json['type']
    if source_type not in ['garden', 'stoa']:
         return jsonify({'error': 'Invalid source type. Must be either "garden" or "stoa".'}), 400

    # We trust the client to provide the full path (e.g. garden/user) in 'target'.
    full_target = request.json['target']

    new_source = {
        'url': request.json['url'],
        'target': full_target,
        'format': request.json.get('format', 'git')
    }
    
    if 'web' in request.json:
        new_source['web'] = request.json['web']

    message_content = request.json.get('message')
    email_content = request.json.get('email')
    
    if message_content or email_content:
        # Log the message/email to a separate file for review
        try:
            log_path = os.path.expanduser('~/agora/applications.log')
            with open(log_path, 'a') as f:
                timestamp = datetime.now().isoformat()
                log_entry = f"[{timestamp}] Source: {full_target} | URL: {new_source['url']}"
                if email_content:
                    log_entry += f" | Email: {email_content}"
                if message_content:
                    log_entry += f" | Message: {message_content}"
                f.write(log_entry + "\n")
        except IOError as e:
            current_app.logger.error(f"Failed to write application log: {e}")

    config_path = os.path.expanduser('~/agora/sources.yaml')
    sources = []

    try:
        with open(config_path, 'r') as f:
            sources = yaml.safe_load(f) or []
    except FileNotFoundError:
        # If the file doesn't exist, we'll create it.
        pass
    except yaml.YAMLError as e:
        return jsonify({'error': f"Error parsing YAML file: {e}"}), 500

    # Check for duplicates
    if any(s.get('url') == new_source['url'] for s in sources):
        return jsonify({'error': f"Source with URL {new_source['url']} already exists."}), 409

    sources.append(new_source)

    try:
        with open(config_path, 'w') as f:
            yaml.dump(sources, f, default_flow_style=False)
    except IOError as e:
        return jsonify({'error': f"Could not write to config file: {e}"}), 500

    # Trigger immediate clone
    # We should do this asynchronously ideally, but for now synchronous is fine for MVP.
    message = 'Source added successfully.'
    # We clone for everything EXCEPT fedwiki (which needs a special import process)
    if new_source.get('format') != 'fedwiki':
        agora_path = os.path.expanduser('~/agora')
        target_path = os.path.join(agora_path, full_target)
        
        try:
            if not os.path.exists(target_path):
                # Ensure parent directory exists
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                subprocess.run(['git', 'clone', new_source['url'], target_path], check=True, capture_output=True, text=True)
                message = "Source added and cloned successfully."
            else:
                message = "Source added to config, but directory already exists (skipped clone)."
        except subprocess.CalledProcessError as e:
            # Warning: config was updated but clone failed.
            return jsonify({'message': 'Source added to config, but git clone failed.', 'error': e.stderr, 'source': new_source}), 202
        except Exception as e:
             return jsonify({'message': 'Source added to config, but an error occurred during cloning.', 'error': str(e), 'source': new_source}), 202

    return jsonify({'message': message, 'source': new_source}), 201

@bp.route('/provision', methods=['POST'])
def provision_garden():
    """
    Provisions a new garden (user + repo) on the configured Forgejo instance.
    
    Parameters:
    JSON Payload:
    - username (string, required): The desired username.
    - email (string, required): The user's email address.
    """
    if not request.json or 'username' not in request.json or 'email' not in request.json:
        return jsonify({'error': 'Missing username or email.'}), 400

    username = request.json['username']
    email = request.json['email']
    
    forgejo_url = os.environ.get('AGORA_FORGEJO_URL')
    forgejo_token = os.environ.get('AGORA_FORGEJO_TOKEN')
    
    if not forgejo_url or not forgejo_token:
        return jsonify({'error': 'Forgejo integration not configured on Bridge.'}), 503
        
    client = ForgejoClient(forgejo_url, forgejo_token)
    
    # 1. Generate Password
    alphabet = string.ascii_letters + string.digits
    password = ''.join(secrets.choice(alphabet) for i in range(16))
    
    # 2. Create User
    try:
        if client.check_user_exists(username):
             return jsonify({'error': f"User {username} already exists on the forge."}), 409
             
        client.create_user(username, email, password, must_change_password=True)
    except Exception as e:
        return jsonify({'error': f"Failed to create user: {str(e)}"}), 500
        
    # 3. Create Repository 'garden'
    try:
        repo_data = client.create_repo(username, 'garden', description="My Digital Garden in the Agora", private=False)
        # Use SSH URL for the bridge to clone/push, but keep HTTPS as fallback
        clone_url = repo_data.get('ssh_url') or repo_data.get('clone_url')
        web_url = repo_data.get('html_url') or repo_data.get('clone_url')
        
        # 3b. Add Deploy Key
        client.add_deploy_key(username, 'garden', 'agora-bridge-sync', AGORA_BRIDGE_DEPLOY_KEY, read_only=False)
        
    except Exception as e:
        return jsonify({'error': f"User created, but failed to create repo: {str(e)}"}), 500
        
    # 4. Add to sources.yaml (reuse internal logic if possible, or just call add_source logic)
    # Ideally we'd call add_source internally, but for now let's just return the info
    # and let the Server call /sources (or we can do it here).
    # Doing it here is atomic and nicer.
    
    # ... logic to add to sources.yaml ...
    # Reuse the add_source logic by constructing a pseudo-request? Or refactor add_source?
    # Refactoring is cleaner but let's just duplicate the minimal config write for safety/speed now.
    
    target = f"garden/{username}"
    new_source = {
        'url': clone_url,
        'target': target,
        'format': 'markdown', # Default for hosted gardens
        'web': web_url 
    }
    
    config_path = os.path.expanduser('~/agora/sources.yaml')
    try:
        # Load existing
        existing_sources = []
        try:
            with open(config_path, 'r') as f:
                existing_sources = yaml.safe_load(f) or []
        except FileNotFoundError:
            pass
            
        # Append
        # Check duplicate
        if not any(s.get('url') == new_source['url'] for s in existing_sources):
            existing_sources.append(new_source)
            with open(config_path, 'w') as f:
                yaml.dump(existing_sources, f, default_flow_style=False)
                
            # Trigger clone (it's empty but we need the folder structure)
            # The repo will have a README from auto_init
            agora_path = os.path.expanduser('~/agora')
            target_path = os.path.join(agora_path, target)
            if not os.path.exists(target_path):
                 os.makedirs(os.path.dirname(target_path), exist_ok=True)
                 env = os.environ.copy()
                 env['GIT_TERMINAL_PROMPT'] = '0'
                 subprocess.run(['git', 'clone', clone_url, target_path], check=True, env=env)

    except Exception as e:
        current_app.logger.error(f"Provisioning succeeded but failed to add to local Agora: {e}")
        # We still return success because the user account IS created.
        
    return jsonify({
        'message': 'Garden provisioned successfully.',
        'username': username,
        'password': password,
        'repo_url': clone_url
    }), 201