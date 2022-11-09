# Copyright 2022 Google LLC
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

import logging
import os
from flask import Flask
from . import agora

def create_app():

    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    config = os.environ.get('AGORA_CONFIG', 'DevelopmentConfig')
    app.config.from_object('api.config.' + config)

    # there's probably a better way to make this distinction, but this works.
    if config == 'ProductionConfig':
        logging.basicConfig(
            filename='agora.log', 
            level=logging.WARNING,
            format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s'
            )
    else:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s'
            )

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Add blueprints here.
    app.register_blueprint(agora.bp)
    app.add_url_rule('/', endpoint='index')

    return app
