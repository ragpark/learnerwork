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

The repository includes a `keys/` directory with a placeholder file so it is
created during deployment. Make sure to generate the key pair before running or
deploying the app.

3. Run the app:

```bash
python app.py
```

Visit `http://localhost:8080/launch` to initiate a sample Deep Linking session
and open the picker interface.

4. Expose with ngrok (optional for LMS testing):

```bash
ngrok http 8080
```

Set `PORT` and `HOST` environment variables if deploying to a platform like Railway. By default the app runs on `0.0.0.0:8080`.

### Testing

Run the automated tests with:

```bash
pytest
```

Set `PORT` and `HOST` environment variables if deploying to a platform like Railway. By default the app runs on `0.0.0.0:5000`.

### Testing

Run the automated tests with:

```bash
pytest
```

## Endpoints

- `/oidc/initiate`: Placeholder for OIDC login
- `/lti/launch`: Accepts LTI launches, renders content picker
- `/launch`: Generates a sample launch JWT and redirects to the picker
- `/deep_link_picker`: Submits selected artefact to LMS
- `/.well-known/jwks.json`: Publishes public key for LTI validation

## Notes

This is a starting point. Production use requires:
- OIDC state handling
- Nonce and state validation
- Audience checking
- Multi-tenant tool support
