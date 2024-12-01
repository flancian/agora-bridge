#!/usr/bin/env python3

# This initial commit is 99% code that bouncepaw hacked together and contributed.
# I'll try to get it up and running as another Agora bridge component, let's see :)
# flancian 2024-12-01

import json
import os
import requests

lost_posts = 0

def write_file(emit_dir, name, url, body):
    filename = emit_dir + name + '.myco'
    try:
        file = open(filename, 'a')
        file.write('= ')
        file.write(name)
        file.write('\n')
        file.write(url)
        file.write('\n\n')
        file.write(body)
        file.close()
    except OSError:
        print('Could not write to file ' + filename)
    except Exception as e:
        print('Weird exception', e)
        

def process(domain, emit_dir, item):
    global lost_posts
    id = int(item['url'].rsplit('/', 1)[-1])

    try:
        body = requests.get(f'https://{domain}/text/' + str(id)).text
    except Exception as e:
        print('While fetching body:', e)

    name = ''
    try:
        name = item['name']
    except Exception as e:
        print('While getting name:', e)

    try:
        write_file(emit_dir, str(id), item['bookmark-of'][0], body)
        write_file(emit_dir, name, item['bookmark-of'][0], body)

        print('Processed ' + str(id) + ': ' + item['name'])

    except Exception:
        lost_posts += 1
        print(item)

def agorize(domain, emit_dir):
    json_url = f'https://xray.p3k.app/parse?url=https%3A%2F%2F{domain}'
    json_doc = requests.get(json_url).text

    items = json.loads(json_doc)['data']['items']

    for file in os.listdir(emit_dir):
        filename = os.fsdecode(file)
        if filename == '.git':
            continue
        os.remove(emit_dir + filename)

    for item in items:
        process(domain, emit_dir, item)

#        domain                 git repo
agorize('links.flancia.org',   '/home/flancian/agora/garden/flancian-betula/')
# agorize('links.bouncepaw.com', '/home/forester/bookmarks/betulagora-bouncepaw/')
