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
from multiprocessing import Pool, JoinableQueue, Process
import subprocess
this_path = os.getcwd()

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
parser.add_argument('--delay', dest='delay', type=float, default=0.1, help='Delay between pulls.')
args = parser.parse_args()

logging.basicConfig()
L = logging.getLogger('pull')
if args.verbose:
    L.setLevel(logging.DEBUG)
else:
    L.setLevel(logging.INFO)

Q = JoinableQueue()
WORKERS = 2

def git_clone(url, path):

    if os.path.exists(path):
        L.info(f"{path} exists, won't clone to it.")
        return 42

    L.info(f"Running git clone {url} to path {path}")

    try:
        process = subprocess.run(['timeout', '10', 'git', 'clone', url, path], timeout=20)
    except subprocess.TimeoutExpired as e:
        L.warning(f"Couldn't clone repo {url}, skipping.")

    # L.info(output)
    # if output.stderr:
    #     L.error(f'{url}: {output.stderr}')

def git_pull(path):

    if not os.path.exists(path):
        L.warning(f"{path} doesn't exist, couldn't pull to it.")
        return 42

    try:
        os.chdir(path)
    except FileNotFoundError:
        L.error(f"Couldn't pull in {path} due to the directory being missing, clone must be run first")

    L.info(f"Running git pull in path {path}")
    try:
        # output = subprocess.run(['git', 'pull'], capture_output=True, timeout=10)
        process = subprocess.run(['timeout', '10', 'git', 'pull'], timeout=20)
    except subprocess.TimeoutExpired as e:
        L.warning(f"Couldn't pull repo in path {path}, skipping.")

    #L.info(output.stdout)
    #if output.stderr:
    #    L.error(f'{path}: {output.stderr}')

def fedwiki_import(url, path):
    os.chdir(this_path)
    output = subprocess.run([f"{this_path}/fedwiki.sh", url, path], capture_output=True)
    L.info(output.stdout)

def worker():
    while True:
        L.debug("Queue size: {}".format(Q.qsize()))
        task = Q.get(block=True, timeout=60)
        task[0](*task[1:])
        Q.task_done()
        # if this is a pull, schedule the same task for another run later.
        if task[0] == git_pull or task[0] == fedwiki_import:
            Q.put(task)
        time.sleep(args.delay)

def main():

    try:
        config = yaml.safe_load(args.config)
    except yaml.YAMLError as e:
        L.error(e)

    for item in config:
        path = os.path.join(args.output_dir, item['target'])
        if item['format'] == "fedwiki":
            Q.put((fedwiki_import, item['url'], path))
            continue
        # schedule one 'clone' run for every garden, in case this is a new garden (or agora).
        Q.put((git_clone, item['url'], path))
        # pull it once, it will be queued again later from the worker.
        Q.put((git_pull, path))

    processes = []
    for i in range(WORKERS):
        worker_process = Process(target=worker, daemon=True, name='worker_process_{}'.format(i))
        processes.append(worker_process)

    L.info(f"Starting {WORKERS} workers to execute work items.")
    for process in processes:
        process.start()
    Q.join()

if __name__ == "__main__":
    main()
