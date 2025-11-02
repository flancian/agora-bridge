from flask import Flask, render_template
import yaml
import os
import subprocess
import sqlite3
from datetime import datetime

app = Flask(__name__)

def get_garden_last_updated(garden):
    """Gets the last updated time for a garden."""
    agora_path = os.path.expanduser('~/agora')
    target_path = os.path.join(agora_path, garden.get('target', ''))

    if not os.path.isdir(target_path):
        return "Directory not found"

    if garden.get('format') == 'git':
        try:
            result = subprocess.run(
                ['git', '-C', target_path, 'log', '-1', '--format=%cd', '--date=iso'],
                capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            return f"Git error: {e}"
    else:
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


@app.route('/')
def index():
    gardens = []
    error_message = None
    config_path = os.path.expanduser('~/agora/sources.yaml')

    try:
        with open(config_path, 'r') as f:
            gardens_config = yaml.safe_load(f)
            if gardens_config:
                for garden in gardens_config:
                    garden['last_updated'] = get_garden_last_updated(garden)
                    gardens.append(garden)

    except FileNotFoundError:
        error_message = f"Configuration file not found at {config_path}. Please ensure it exists. You can use 'gardens.yaml.example' as a template."
    except yaml.YAMLError as e:
        error_message = f"Error parsing YAML file at {config_path}: {e}"

    db_info = get_db_info()

    return render_template(
        'index.html',
        title='Agora Bridge Status',
        gardens=gardens,
        db_info=db_info,
        error_message=error_message
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
