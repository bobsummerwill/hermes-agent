#!/usr/bin/env python3
"""
GitHub App Installation Token Generator

Generates a short-lived installation token from GitHub App credentials.
Caches tokens in ~/.github/app-token-cache.json and refreshes automatically.

Required env vars:
  GITHUB_APP_ID                  - The App ID
  GITHUB_APP_PRIVATE_KEY_PATH    - Path to the .pem private key file
  GITHUB_APP_INSTALLATION_ID     - Installation ID (optional if only one installation)

Usage:
  python3 gh-app-token.py              # prints the token
  python3 gh-app-token.py --json       # prints JSON with token + expiry
  python3 gh-app-token.py --install-id # auto-detect and print installation IDs

Dependencies (one of, checked in order):
  1. PyJWT          - pip install pyjwt[crypto]
  2. cryptography   - pip install cryptography
  3. openssl CLI    - usually pre-installed
"""

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CACHE_PATH = Path.home() / ".github" / "app-token-cache.json"
REFRESH_MARGIN = 300  # refresh if less than 5 minutes remaining


# ---------------------------------------------------------------------------
# JWT creation — tries PyJWT, then cryptography, then openssl CLI
# ---------------------------------------------------------------------------

def _b64url(data: bytes) -> str:
    """Base64url encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _create_jwt_pyjwt(app_id: str, pem_text: str, now: int) -> str:
    """Create JWT using PyJWT (simplest — one call)."""
    import jwt  # noqa: F811
    payload = {"iat": now - 60, "exp": now + 600, "iss": app_id}
    return jwt.encode(payload, pem_text, algorithm="RS256")


def _create_jwt_cryptography(app_id: str, pem_text: str, now: int) -> str:
    """Create JWT using the cryptography library."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(json.dumps({"iat": now - 60, "exp": now + 600, "iss": app_id}, separators=(",", ":")).encode())
    unsigned = f"{header}.{payload}"

    key = serialization.load_pem_private_key(pem_text.encode(), password=None)
    sig = key.sign(unsigned.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return f"{unsigned}.{_b64url(sig)}"


def _create_jwt_openssl(app_id: str, pem_text: str, now: int) -> str:
    """Create JWT using the openssl CLI as a last resort."""
    import subprocess
    import tempfile

    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(json.dumps({"iat": now - 60, "exp": now + 600, "iss": app_id}, separators=(",", ":")).encode())
    unsigned = f"{header}.{payload}"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
        f.write(pem_text)
        pem_path = f.name
    try:
        proc = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", pem_path],
            input=unsigned.encode("ascii"),
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"openssl signing failed: {proc.stderr.decode()}")
        return f"{unsigned}.{_b64url(proc.stdout)}"
    finally:
        os.unlink(pem_path)


def create_jwt(app_id: str, pem_text: str) -> str:
    """Create a JWT for GitHub App authentication.

    Tries PyJWT → cryptography → openssl CLI, using whichever is available.
    """
    now = int(time.time())
    errors = []

    for fn in (_create_jwt_pyjwt, _create_jwt_cryptography, _create_jwt_openssl):
        try:
            return fn(app_id, pem_text, now)
        except ImportError:
            continue
        except FileNotFoundError:
            # openssl not on PATH
            continue
        except Exception as e:
            errors.append(f"{fn.__name__}: {e}")

    msg = "No JWT signing method available."
    if errors:
        msg += " Errors: " + "; ".join(errors)
    msg += " Install PyJWT (pip install pyjwt[crypto]) or ensure openssl is on PATH."
    raise RuntimeError(msg)


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

def api_request(url: str, token: str, method: str = "GET", token_type: str = "Bearer"):
    """Make a GitHub API request."""
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"{token_type} {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if method == "POST":
        req.data = b"{}"
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"GitHub API {e.code}: {body}")


# ---------------------------------------------------------------------------
# Token cache
# ---------------------------------------------------------------------------

def _load_cache() -> dict:
    """Load cached token if still valid (with REFRESH_MARGIN)."""
    if not CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text())
        if data.get("expires_at_epoch", 0) > time.time() + REFRESH_MARGIN:
            return data
    except (json.JSONDecodeError, KeyError):
        pass
    return {}


def _save_cache(token: str, expires_at: str, installation_id: str):
    """Cache the token with its expiry."""
    from datetime import datetime

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        exp_epoch = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        exp_epoch = time.time() + 3600  # fallback: 1 hour

    CACHE_PATH.write_text(json.dumps({
        "token": token,
        "expires_at": expires_at,
        "expires_at_epoch": exp_epoch,
        "installation_id": installation_id,
    }, indent=2))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_installations(app_id: str, pem_text: str) -> list:
    """List all installations for the app."""
    jwt_token = create_jwt(app_id, pem_text)
    installations = api_request("https://api.github.com/app/installations", jwt_token)
    for inst in installations:
        print(f"  {inst['id']} -> {inst['account']['login']} ({inst['account']['type']})")
    return installations


def get_installation_token(app_id: str, pem_text: str, installation_id: str = None) -> dict:
    """Get an installation token, using cache if available.

    Returns dict with keys: token, expires_at, installation_id.
    """
    # Check cache first
    cached = _load_cache()
    if cached.get("token"):
        if installation_id is None or cached.get("installation_id") == installation_id:
            return cached

    # Generate JWT
    jwt_token = create_jwt(app_id, pem_text)

    # Auto-detect installation ID if not provided
    if not installation_id:
        installations = api_request("https://api.github.com/app/installations", jwt_token)
        if not installations:
            raise RuntimeError("No installations found for this GitHub App")
        if len(installations) == 1:
            installation_id = str(installations[0]["id"])
            print(
                f"Auto-detected installation: {installation_id}"
                f" ({installations[0]['account']['login']})",
                file=sys.stderr,
            )
        else:
            print("Multiple installations found. Set GITHUB_APP_INSTALLATION_ID:", file=sys.stderr)
            for inst in installations:
                print(f"  {inst['id']} -> {inst['account']['login']}", file=sys.stderr)
            raise RuntimeError("Multiple installations — set GITHUB_APP_INSTALLATION_ID")

    # Exchange JWT for installation token
    result = api_request(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        jwt_token,
        method="POST",
    )

    token = result["token"]
    expires_at = result.get("expires_at", "")
    _save_cache(token, expires_at, installation_id)

    return {"token": token, "expires_at": expires_at, "installation_id": installation_id}


def main():
    app_id = os.environ.get("GITHUB_APP_ID")
    pem_path = os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH")
    installation_id = os.environ.get("GITHUB_APP_INSTALLATION_ID")

    if not app_id:
        print("Error: GITHUB_APP_ID not set", file=sys.stderr)
        sys.exit(1)
    if not pem_path:
        print("Error: GITHUB_APP_PRIVATE_KEY_PATH not set", file=sys.stderr)
        sys.exit(1)

    pem_path = os.path.expanduser(pem_path)
    if not os.path.isfile(pem_path):
        print(f"Error: Private key not found at {pem_path}", file=sys.stderr)
        sys.exit(1)

    with open(pem_path) as f:
        pem_text = f.read()

    if "--install-id" in sys.argv:
        print("Installations for this app:")
        list_installations(app_id, pem_text)
        return

    result = get_installation_token(app_id, pem_text, installation_id)

    if "--json" in sys.argv:
        print(json.dumps(result, indent=2))
    else:
        print(result["token"])


if __name__ == "__main__":
    main()
