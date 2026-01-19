#!/usr/bin/env python3
# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# an [[agora bridge]], that is, a utility that takes a .yaml file describing a set of [[personal knowledge graphs]] or [[digital gardens]] and pulls them to be consumed by other bridges or an [[agora server]]. [[flancian]]

import argparse
import glob
import logging
import os
import time
import yaml
import sqlite3
from multiprocessing import Pool, JoinableQueue, Process
import subprocess
this_path = os.getcwd()

# for git commands, in seconds.
TIMEOUT="60"

class StatusTracker:
    def __init__(self, db_path):
        self.db_path = db_path
        self._setup_db()

    def _setup_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS garden_status (
                    target TEXT PRIMARY KEY,
                    url TEXT,
                    last_attempt TEXT,
                    last_success TEXT,
                    last_error TEXT,
                    status TEXT
                )
            ''')

    def update(self, target, url=None, success=True, error=None):
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        try:
            with sqlite3.connect(self.db_path) as conn:
                if success:
                    conn.execute('''
                        INSERT INTO garden_status (target, url, last_attempt, last_success, last_error, status)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(target) DO UPDATE SET
                            last_attempt=excluded.last_attempt,
                            last_success=excluded.last_attempt,
                            last_error=NULL,
                            status='OK'
                    ''', (target, url, now, now, None, 'OK'))
                else:
                    conn.execute('''
                        INSERT INTO garden_status (target, url, last_attempt, last_error, status)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(target) DO UPDATE SET
                            last_attempt=excluded.last_attempt,
                            last_error=excluded.last_error,
                            status='ERROR'
                    ''', (target, url, now, error, 'ERROR'))
        except Exception as e:
            L.error(f"TRACKER: FAILED to update {target}: {e}")

def dir_path(string):
    if not os.path.isdir(string):
        print(f"Trying to create {string}.")
        output = subprocess.run(['mkdir', '-p', string], capture_output=True)
        if output.stderr:
            L.error(output.stderr)
    return os.path.abspath(string)

parser = argparse.ArgumentParser(description='Agora Bridge')
parser.add_argument('--config', dest='config', type=argparse.FileType('r'), required=True, help='The path to a YAML file describing the digital gardens to consume.')
parser.add_argument('--output-dir', dest='output_dir', type=dir_path, required=True, help='The path to a directory where the digital gardens will be stored (one subdirectory per user).')
parser.add_argument('--verbose', dest='verbose', type=bool, default=False, help='Whether to log more information.')
parser.add_argument('--reset', dest='reset', type=bool, default=False, help='Whether to git reset --hard whenever a pull fails.')
parser.add_argument('--reset_only', dest='reset_only', type=bool, default=False, help='Whether do reset --hard instead of pulling.')
parser.add_argument('--delay', dest='delay', type=float, default=0.1, help='Delay between pulls.')
args = parser.parse_args()

logging.basicConfig()
L = logging.getLogger('pull')
if args.verbose:
    L.setLevel(logging.DEBUG)
else:
    L.setLevel(logging.INFO)

Q = JoinableQueue()
WORKERS = 6

def git_clone(tracker, target, url, path):

    if os.path.exists(path):
        L.info(f"{path} exists, won't clone to it.")
        # Even if it exists, we mark it as a "success" for the clone step
        # as it's ready for the pull step.
        tracker.update(target, url=url, success=True)
        return

    L.info(f"Running git clone {url} to path {path}")

    try:
        output = subprocess.run(['timeout', TIMEOUT, 'git', 'clone', url, path], capture_output=True)
        if output.returncode == 0:
            tracker.update(target, url=url, success=True)
        else:
            error_msg = output.stderr.decode('utf-8', errors='replace') if output.stderr else "Unknown error"
            tracker.update(target, url=url, success=False, error=error_msg)
            L.error(f'Error while cloning {url}: {error_msg}')
    except Exception as e:
        tracker.update(target, url=url, success=False, error=str(e))
        L.error(f'Exception while cloning {url}: {e}')

def git_reset(path):
    L.info(f'Trying to git reset --hard')
    subprocess.run(['timeout', TIMEOUT, 'git', 'fetch', 'origin'])
    # Get default branch
    try:
        res = subprocess.run(['git', 'symbolic-ref', '--short', 'HEAD'], capture_output=True)
        branch = res.stdout.strip().decode("utf-8") if res.stdout else "main"
        output = subprocess.run(['timeout', TIMEOUT, 'git', 'reset', '--hard', f'origin/{branch}'], capture_output=True)
        L.info(f'output: {output.stdout}')
        if output.stderr:
            L.error(output.stderr)
    except Exception as e:
        L.error(f"Reset failed: {e}")


def git_pull(tracker, target, url, path):

    if not os.path.exists(path):
        L.warning(f"{path} doesn't exist, couldn't pull to it.")
        return 42

    try:
        os.chdir(path)
    except FileNotFoundError:
        L.error(f"Couldn't pull in {path} due to the directory being missing, clone must be run first")
        return

    if args.reset_only:
        git_reset(path)
        return

    L.info(f"Running git pull in path {path}")
    try:
        output = subprocess.run(['timeout', TIMEOUT, 'git', 'pull'], capture_output=True)
        if output.returncode == 0:
            tracker.update(target, url=url, success=True)
            L.info(output.stdout.decode('utf-8', errors='replace'))
        else:
            error_msg = output.stderr.decode('utf-8', errors='replace') if output.stderr else "Unknown error"
            tracker.update(target, url=url, success=False, error=error_msg)
            L.error(f'{path}: {error_msg}')
            if args.reset:
                git_reset(path)
    except Exception as e:
        tracker.update(target, url=url, success=False, error=str(e))
        L.error(f"Pull exception: {e}")

def fedwiki_import(tracker, target, url, path):
    os.chdir(this_path)
    try:
        output = subprocess.run([f"{this_path}/fedwiki.sh", url, path], capture_output=True)
        if output.returncode == 0:
            tracker.update(target, url=url, success=True)
        else:
            error_msg = output.stderr.decode('utf-8', errors='replace') if output.stderr else "Unknown error"
            tracker.update(target, url=url, success=False, error=error_msg)
    except Exception as e:
        tracker.update(target, url=url, success=False, error=str(e))

def worker(db_path):
    tracker = StatusTracker(db_path)
    while True:
        try:
            L.debug("Queue size: {}".format(Q.qsize()))
            task = Q.get(block=True, timeout=60)
            # task is (func, *args)
            func = task[0]
            args_for_func = task[1:]
            func(tracker, *args_for_func)
            Q.task_done()
            # if this is a pull, schedule the same task for another run later.
            if func == git_pull or func == fedwiki_import:
                Q.put(task)
            time.sleep(args.delay)
        except Exception as e:
            L.error(f"Worker exception: {e}")
            # Continue the loop
            continue

def main():

    try:
        config = yaml.safe_load(args.config)
    except yaml.YAMLError as e:
        L.error(e)

    db_path = os.path.join(args.output_dir, 'bridge.db')
    # Initialize the tracker here to create the DB file before workers start
    tracker = StatusTracker(db_path)

    for item in config:
        target = item['target']
        url = item['url']
        path = os.path.join(args.output_dir, target)
        if item.get('format') == "fedwiki":
            Q.put((fedwiki_import, target, url, path))
            continue
        
        # Default to git for all other formats (markdown, obsidian, foam, etc.)
        # schedule one 'clone' run for every garden, in case this is a new garden (or agora).
        Q.put((git_clone, target, url, path))
        # pull it once, it will be queued again later from the worker.
        Q.put((git_pull, target, url, path))

    processes = []
    for i in range(WORKERS):
        worker_process = Process(target=worker, args=(db_path,), daemon=True, name='worker_process_{}'.format(i))
        processes.append(worker_process)

    L.info(f"Starting {WORKERS} workers to execute work items. Status tracked in {db_path}")
    for process in processes:
        process.start()
    Q.join()

if __name__ == "__main__":
    main()
