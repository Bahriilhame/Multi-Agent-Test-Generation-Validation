from flask import Flask, jsonify, request

app = Flask(__name__)


@app.post("/multiply")
def multiply():
    payload = request.get_json(silent=True) or {}
    try:
        left, right = payload["left"], payload["right"]
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            raise ValueError
    except (KeyError, ValueError, TypeError):
        return jsonify(error="left and right must be numbers"), 400
    return jsonify(result=left * right)
