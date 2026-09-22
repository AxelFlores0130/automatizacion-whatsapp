from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


@app.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "message": "Backend de automatizacion WhatsApp funcionando"
    }), 200


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
