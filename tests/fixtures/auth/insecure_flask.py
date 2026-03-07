"""Fixture: Flask app with auth issues."""

from flask import Flask, request, make_response
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins="*")  # AUTH-005

SECRET_KEY = "mysecretkey"  # AUTH-004

@app.route("/api/delete-user/<user_id>", methods=["DELETE"])
def delete_user(user_id):  # AUTH-002 (no auth)
    return {"deleted": user_id}

@app.route("/profile")
def user_profile():  # AUTH-001 (sensitive path)
    return {"user": "data"}

@app.route("/set-prefs", methods=["POST"])
def set_preferences():
    resp = make_response("ok")
    resp.set_cookie("session", "abc123")  # AUTH-006 (no secure flags)
    return resp

@app.route("/login", methods=["POST"])
def login():
    if request.form["password"] == stored_password:  # AUTH-007
        return "ok"
