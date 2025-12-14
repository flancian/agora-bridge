from flask import Flask

def create_app():
    app = Flask(__name__)

    from . import agora
    app.register_blueprint(agora.bp)

    return app
