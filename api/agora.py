from flask import Flask, render_template, Blueprint, request, jsonify, current_app
import yaml
import os
import subprocess
import sqlite3
from datetime import datetime

bp = Blueprint('agora', __name__)

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
    if new_source.get('format') == 'git' or new_source.get('format') == 'foam':
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