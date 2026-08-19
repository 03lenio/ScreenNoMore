"""Flask app and blueprint registration"""
from flask import Flask

from backend.web.routes.util.health import health_routes

app = Flask(__name__)
app.register_blueprint(health_routes)
