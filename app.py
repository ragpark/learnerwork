from flask import Flask, request, redirect, render_template, jsonify
import jwt
import datetime
from pathlib import Path
import os

app = Flask(__name__)

# Load RSA keys
PRIVATE_KEY_PATH = Path("keys/private.key")
PUBLIC_KEY_PATH = Path("keys/public.key")

if not PRIVATE_KEY_PATH.exists() or not PUBLIC_KEY_PATH.exists():
    raise FileNotFoundError(
        "Key files not found. Generate them in the 'keys/' directory as described in the README."
    )

PRIVATE_KEY = PRIVATE_KEY_PATH.read_text()
PUBLIC_KEY = PUBLIC_KEY_PATH.read_text()
KID = "sample-key-id"

def create_launch_jwt():
    now = datetime.datetime.utcnow()
    payload = {
        "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiDeepLinkingRequest",
        "https://purl.imsglobal.org/spec/lti/claim/version": "1.3.0",
        "https://purl.imsglobal.org/spec/lti/claim/deep_linking_settings": {
            "deep_link_return_url": "http://example.com/return"
        },
        "iss": "test",
        "aud": "client",
        "exp": now + datetime.timedelta(minutes=5),
    }
    return jwt.encode(payload, PRIVATE_KEY, algorithm="RS256", headers={"kid": KID})


@app.route("/launch")
def launch_page():
    token = create_launch_jwt()
    return render_template("launch.html", token=token)

@app.route("/oidc/initiate")
def oidc_initiate():
    # Redirect user back to the LMS authorization URL
    return "OIDC flow not fully implemented - placeholder"

@app.route("/lti/launch", methods=["POST"])
def lti_launch():
    id_token = request.form.get("id_token")
    if not id_token:
        return "Missing id_token", 400

    try:
        decoded = jwt.decode(id_token, PUBLIC_KEY, algorithms=["RS256"], options={"verify_aud": False})
        if decoded["https://purl.imsglobal.org/spec/lti/claim/message_type"] == "LtiDeepLinkingRequest":
            return render_template("deep_link_picker.html", data=decoded)
    except Exception as e:
        return f"Launch failed: {str(e)}", 400

    return "Unsupported LTI message type", 400

@app.route("/deep_link_picker", methods=["POST"])
def deep_link_picker():
    # Construct a Deep Linking response JWT
    deep_link_return_url = request.form.get("deep_link_return_url")
    content_url = request.form.get("content_url")
    title = request.form.get("title")

    now = datetime.datetime.utcnow()
    jwt_headers = {"kid": KID}
    jwt_payload = {
        "iss": "https://your-lti-tool.example.com",
        "aud": "your-lms-client-id",
        "iat": now,
        "exp": now + datetime.timedelta(minutes=5),
        "nonce": "unused",
        "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiDeepLinkingResponse",
        "https://purl.imsglobal.org/spec/lti/claim/version": "1.3.0",
        "https://purl.imsglobal.org/spec/lti-dl/claim/content_items": [
            {
                "type": "ltiResourceLink",
                "title": title,
                "url": content_url,
                "presentation": {
                    "documentTarget": "iframe"
                }
            }
        ]
    }

    id_token = jwt.encode(jwt_payload, PRIVATE_KEY, algorithm="RS256", headers=jwt_headers)
    return render_template("return_form.html", url=deep_link_return_url, token=id_token)

@app.route("/.well-known/jwks.json")
def jwks():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric import rsa
    import base64
    import json

    key = serialization.load_pem_public_key(PUBLIC_KEY.encode(), backend=default_backend())
    numbers = key.public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": KID,
        "use": "sig",
        "alg": "RS256",
        "n": base64.urlsafe_b64encode(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, 'big')).rstrip(b'=').decode(),
        "e": base64.urlsafe_b64encode(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, 'big')).rstrip(b'=').decode(),
    }
    return jsonify({"keys": [jwk]})

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "0.0.0.0")
    app.run(debug=True, host=host, port=port)
