import importlib
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt
import pytest
import werkzeug

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "0"

KID = "sample-key-id"

@pytest.fixture(scope="session", autouse=True)
def generate_keys(tmp_path_factory):
    keys_dir = Path("keys")
    keys_dir.mkdir(exist_ok=True)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    (keys_dir / "private.key").write_bytes(priv_bytes)
    (keys_dir / "public.key").write_bytes(pub_bytes)

    yield

@pytest.fixture()
def client():
    # Import app after keys exist
    app = importlib.import_module("app").app
    app.config.update({"TESTING": True})
    with app.test_client() as client:
        yield client

def create_launch_jwt():
    private_key = Path("keys/private.key").read_text()
    payload = {
        "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiDeepLinkingRequest",
        "https://purl.imsglobal.org/spec/lti/claim/version": "1.3.0",
        "https://purl.imsglobal.org/spec/lti/claim/deep_linking_settings": {
            "deep_link_return_url": "http://example.com/return"
        },
        "iss": "test",
        "aud": "client",
        "exp": int(time.time()) + 60,
    }
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": KID})

def test_oidc_initiate(client):
    resp = client.get("/oidc/initiate")
    assert resp.status_code == 200
    assert b"OIDC flow not fully implemented" in resp.data

def test_launch_missing_token(client):
    resp = client.post("/lti/launch")
    assert resp.status_code == 400


def test_launch_with_valid_token(client):
    token = create_launch_jwt()
    resp = client.post("/lti/launch", data={"id_token": token})
    assert resp.status_code == 200
    assert b"Deep Link Picker" in resp.data

def test_deep_link_picker(client):
    resp = client.post(
        "/deep_link_picker",
        data={
            "deep_link_return_url": "http://example.com/return",
            "content_url": "https://example.com/content/1",
            "title": "Example",
        },
    )
    assert resp.status_code == 200
    assert b"Return to LMS" in resp.data

def test_jwks(client):
    resp = client.get("/.well-known/jwks.json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "keys" in data and len(data["keys"]) == 1
