# Copyright 2020 Google LLC
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

import collections
import datetime
from distutils.command.config import config
import json
import jsons
import re
import time
from urllib.parse import parse_qs
from flask import (Blueprint, Response, current_app, jsonify, redirect,
                   render_template, request, url_for, g, send_file)

bp = Blueprint('agora', __name__)

# The [[agora]] is a [[distributed knowledge graph]].
# See https://anagora.org, https://anagora.org/go/agora for a description.
@bp.route('/status')
def status():
    return render_template(
            'status.html', 
            config=current_app.config,
            )

@bp.route('/')
def index():
    return redirect(url_for('.status'))

@bp.route('/sources.json')
def sources():
    """Returns all sources (repositories) known to this Agora Bridge."""
    sources = ['placeholder']
    return jsonify(jsons.dump(sources))

