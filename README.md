# LTI 1.3 Deep Linking Tool (Python Proof of Concept)

This project is a minimal Python Flask app that acts as an LTI 1.3 Tool supporting Deep Linking launches from an LMS.

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Generate RSA keypair (place in `keys/`):

```bash
openssl genrsa -out keys/private.key 2048
openssl rsa -in keys/private.key -pubout -out keys/public.key
```

3. Run the app:

```bash
python app.py
```

4. Expose with ngrok (optional for LMS testing):

```bash
ngrok http 5000
```

## Endpoints

- `/oidc/initiate`: Placeholder for OIDC login
- `/lti/launch`: Accepts LTI launches, renders content picker
- `/deep_link_picker`: Submits selected artefact to LMS
- `/.well-known/jwks.json`: Publishes public key for LTI validation

## Notes

This is a starting point. Production use requires:
- OIDC state handling
- Nonce and state validation
- Audience checking
- Multi-tenant tool support
