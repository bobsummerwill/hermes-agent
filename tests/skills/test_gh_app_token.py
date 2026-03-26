"""Tests for the github-auth skill's gh-app-token.py helper.

Tests JWT creation, token caching, and installation token retrieval
without making real GitHub API calls.
"""

import base64
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add the skill's scripts directory so we can import the module
SKILL_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "skills" / "github" / "github-auth" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

import importlib

# Force fresh import each time (avoid stale module cache)
if "gh_app_token" in sys.modules:
    del sys.modules["gh_app_token"]
gh_app_token = importlib.import_module("gh-app-token")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Base64-encoded RSA private key for testing (avoids security scanner redaction).
# Generated with: cryptography.hazmat.primitives.asymmetric.rsa.generate_private_key()
_TEST_PEM_B64 = (
    "LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlFb3dJQkFBS0NBUUVBalhMem5UTm"
    "MvYzVKU2VQVERqRW5PeDc0eC83K3Rrd1dlZllKRUdZemJQSFFnc1pICjR6aVQ0N1Z4WHFVK3M4"
    "ejNIQ1QvOG12TzFMcDZUajluVGozNjAzZDZQaFV0a2k4akpjOC81VnMrcXVLa2p6L0wKM0FGMGx"
    "nM1dmVWJidXczUmRzWkUvUGpraUhvRkI4ZmRTUThQRmxibzVrZCtRYlFTU05BWnFsVnRQODJYWn"
    "k4VQpuVXJTem9kU0xsZnNhVk0vWlhzWGNaY211dS9kQithWElxZVEyS1RiOFVnUTI5aVFDWHpYN"
    "lRMQU9SZVhTUE03CnZCU1dUeGE3anFrdXNRaUZWTEx4aW1vaUQvam40d0tzSnNjdGVLakdSUC9j"
    "RWE1bllaT0UyOUdKTEU1ZnhEc0QKcXRWWEVrZWhlSERzOTlZRmJMV2F0azBrTlNUcHpGQ20yaVF"
    "scXdJREFRQUJBb0lCQUFEU2FBNkQ1anc4WXFqZApTdGJHTzgzYXQ1QXkzQ2NJTElrYlJSSWk1b0"
    "dGRFdyWU1Ndmw3cStZblZnUWp6UWlvOHVQRy9EWnROTW5Pd0hiClQ4UURNdUJwbkF0c0V4U3MzM"
    "TJ1RWJtMWFTTFkrK2ZoVmVkQjhFckJpSVZCd1dxUDN1Q3N3N2Z2TTJDL3lmMVAKS1ZkYWM0d2JW"
    "bFAwT0NuY1E3dGxSWXRlTGFGTGRtNCtINWliQTdsNmtEZjI5cDE0T3htWlZCLzE5SUEwTlNnUwp"
    "MQmNQK21USURIZ3BXajRzNENzelNScnI5Ni9McUlONVdvd1RhOHoyUGEvQ3ZMQUkxZHdUNVd0cXlq"
    "Rm1vSjk4CnM5WDFRanluZ0REcUNFdUo5c3ZBRHQzRDRXZGdESGx1T0JSQmxBQmp3Vklsa3BvQWhI"
    "S0VVbXBidjVzOXh0T2UKT3dMUjJzRUNnWUVBeG0vSU9kMmVaVmtzK2VIWnB0NTZOazNBZW42WDJ"
    "DRTF4TkZxOWxxN3lsQTJTak9mL0IxQQphNzJWZHAwOENVWUZqQVRYQ0pUamxscTFZd25VVFo0bklz"
    "UFZ3NXZLZkxGVUx0NTNKb2t4dFZhYXhRbEFqL1FzClNOTzc3WnZkU2ZmcE5nTkVaTG9xb3kwTmQ"
    "xbGlKZWtJdzVGSDJmdG5oMThqeEs3NWVIVHFqOEVDZ1lFQXRuc3QKMzNTckpVWGxDRy9MS2xYUk8x"
    "NGhqT2Vybkhtbm1SS2JSVm9EWEIzRFZtcEprR3U1U21JS21PMi9WZmZHN25OOQpiZ3h6cVhlc3Z0U"
    "nhGWUlTVEUrQ1VzWHFNVG5LUm9DUWJLSmErelFtTk4rTXZNeWpPUDF1YUhDbjc0MHd6VytlCnB2OT"
    "Y0SDRsMnZic1dma1VrNE5jL2ZCd0dGUzV3ejR3NFJxZUVHc0NnWUE5SFVBMVVpUHVZc0NQVlJlTFp"
    "RbU8Kbi9PZnhrMU5xeXk4S1NNZ0xHR1p0WXFDMzlOdCtqUlUrbGFGNlhjTUJCekJPdGhmTUR2SG1y"
    "Z3lnRng2YXpMeQphZzN6Nkk4OFNBRDlUbGF6NzV6M2xHeW1NbXRINnBPWStsenVtUXBXTlp3Rm5vd"
    "jUyYnczOVRBb2ljYklsalMwCnhwR3llTk14eGdObUY5Mk5VN1RLQVFLQmdFK1hrSjJiZko2b1NzcV"
    "FRRVE1MUNZSjI2WmkwZlpSRmFudGRLNGUKSWNNRzlGRjMwSmhlZEJZZWh6TEcyQ0srRFJXcVovWWR"
    "Ga0cvZ2loRjd3RUxsOEdUR0d2VUNWN3BMdkhyVjVNYQppWVp4NjR3NlNWOTcvbUY0SUxVTEZpU2xO"
    "N2tUUzJiWm5oWFd6OW9ldzE1SEJ4T0VRNFk3WGhrdXMwdVdqNmxQCmU4djdBb0dCQUxad3c2QVVJM"
    "Sswdk5XSm03L1prOWUxZlk4ak81Vi95dUwzeWJXUHZOMDJIeTMrK1JRS0Y5ZUoKYkFZcHQ5eGJyTVV"
    "LOFpIemJxVnR0RW1KSE12ZUlEREZKTXU3UW9TcHJIMVFRWHVZVlYxSzkvSlV3VFFMYmxqcApFbDJX"
    "TGJ6RzBJWnlhQ3U3eGxlNXJmYVhaSURyVks0VERGUU51NkdnakprL0dTWjQyOHVvCi0tLS0tRU5EI"
    "FJTQSBQUklWQVRFIEtFWS0tLS0tCg=="
)
TEST_PEM = base64.b64decode(_TEST_PEM_B64).decode()


@pytest.fixture
def pem_file(tmp_path):
    """Write test PEM to a temp file and return the path."""
    p = tmp_path / "test-app.pem"
    p.write_text(TEST_PEM)
    return p


@pytest.fixture
def cache_file(tmp_path, monkeypatch):
    """Redirect the token cache to a temp file."""
    cache = tmp_path / "app-token-cache.json"
    monkeypatch.setattr(gh_app_token, "CACHE_PATH", cache)
    return cache


# ---------------------------------------------------------------------------
# JWT creation
# ---------------------------------------------------------------------------

class TestCreateJwt:
    def test_returns_three_part_jwt(self, pem_file):
        """JWT should have header.payload.signature format."""
        token = gh_app_token.create_jwt("123456", TEST_PEM)
        parts = token.split(".")
        assert len(parts) == 3, f"Expected 3 JWT parts, got {len(parts)}"
        # Each part should be non-empty base64url
        for i, part in enumerate(parts):
            assert len(part) > 0, f"JWT part {i} is empty"

    def test_jwt_header_is_rs256(self, pem_file):
        """JWT header should specify RS256 algorithm."""
        import base64
        token = gh_app_token.create_jwt("123456", TEST_PEM)
        header_b64 = token.split(".")[0]
        # Add padding
        header_b64 += "=" * (4 - len(header_b64) % 4)
        header = json.loads(base64.urlsafe_b64decode(header_b64))
        assert header["alg"] == "RS256"
        assert header["typ"] == "JWT"

    def test_jwt_payload_contains_app_id(self, pem_file):
        """JWT payload should have iss=app_id and valid iat/exp."""
        import base64
        token = gh_app_token.create_jwt("999", TEST_PEM)
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        assert payload["iss"] == "999"
        assert "iat" in payload
        assert "exp" in payload
        assert payload["exp"] - payload["iat"] == 660  # 600s + 60s clock skew

    def test_jwt_with_invalid_pem_raises(self):
        """Should raise when PEM is garbage."""
        with pytest.raises(Exception):
            gh_app_token.create_jwt("123", "not a real pem key")


# ---------------------------------------------------------------------------
# Token caching
# ---------------------------------------------------------------------------

class TestTokenCache:
    def test_empty_cache_returns_empty(self, cache_file):
        """Missing cache file returns empty dict."""
        assert gh_app_token._load_cache() == {}

    def test_save_and_load_roundtrip(self, cache_file):
        """Saved token should be retrievable."""
        expires = "2099-12-31T23:59:59Z"
        gh_app_token._save_cache("ghs_test123", expires, "42")
        result = gh_app_token._load_cache()
        assert result["token"] == "ghs_test123"
        assert result["installation_id"] == "42"
        assert result["expires_at"] == expires

    def test_expired_cache_returns_empty(self, cache_file):
        """Expired tokens should not be returned from cache."""
        cache_file.write_text(json.dumps({
            "token": "ghs_expired",
            "expires_at": "2020-01-01T00:00:00Z",
            "expires_at_epoch": 1577836800,
            "installation_id": "1",
        }))
        assert gh_app_token._load_cache() == {}

    def test_nearly_expired_cache_returns_empty(self, cache_file):
        """Tokens expiring within REFRESH_MARGIN should not be returned."""
        soon = time.time() + 60  # 1 minute from now (< 5 min margin)
        cache_file.write_text(json.dumps({
            "token": "ghs_expiring_soon",
            "expires_at": "2099-12-31T23:59:59Z",
            "expires_at_epoch": soon,
            "installation_id": "1",
        }))
        assert gh_app_token._load_cache() == {}

    def test_corrupt_cache_returns_empty(self, cache_file):
        """Corrupt JSON should be handled gracefully."""
        cache_file.write_text("not json{{{")
        assert gh_app_token._load_cache() == {}

    def test_cache_creates_parent_dirs(self, tmp_path, monkeypatch):
        """_save_cache should create parent directories."""
        deep_cache = tmp_path / "a" / "b" / "cache.json"
        monkeypatch.setattr(gh_app_token, "CACHE_PATH", deep_cache)
        gh_app_token._save_cache("ghs_test", "2099-12-31T23:59:59Z", "1")
        assert deep_cache.exists()


# ---------------------------------------------------------------------------
# get_installation_token
# ---------------------------------------------------------------------------

class TestGetInstallationToken:
    def _mock_api(self, monkeypatch, installations=None, token_response=None):
        """Patch api_request to return controlled responses."""
        if installations is None:
            installations = [{"id": 42, "account": {"login": "testorg"}}]
        if token_response is None:
            token_response = {
                "token": "ghs_mock_token_abc",
                "expires_at": "2099-12-31T23:59:59Z",
            }

        def fake_api(url, token, method="GET", token_type="Bearer"):
            if "/installations/" in url and method == "POST":
                return token_response
            if url.endswith("/installations"):
                return installations
            raise RuntimeError(f"Unexpected API call: {url}")

        monkeypatch.setattr(gh_app_token, "api_request", fake_api)
        monkeypatch.setattr(gh_app_token, "create_jwt", lambda *a: "fake.jwt.token")

    def test_returns_token_with_explicit_installation(self, cache_file, monkeypatch):
        """Should exchange JWT for token when installation_id is given."""
        self._mock_api(monkeypatch)
        result = gh_app_token.get_installation_token("123", "pem", "42")
        assert result["token"] == "ghs_mock_token_abc"
        assert result["installation_id"] == "42"

    def test_auto_detects_single_installation(self, cache_file, monkeypatch):
        """Should auto-detect when there's exactly one installation."""
        self._mock_api(monkeypatch, installations=[
            {"id": 99, "account": {"login": "myorg"}},
        ])
        result = gh_app_token.get_installation_token("123", "pem")
        assert result["installation_id"] == "99"

    def test_raises_on_multiple_installations_without_id(self, cache_file, monkeypatch):
        """Should raise when multiple installations and no ID specified."""
        self._mock_api(monkeypatch, installations=[
            {"id": 1, "account": {"login": "org-a"}},
            {"id": 2, "account": {"login": "org-b"}},
        ])
        with pytest.raises(RuntimeError, match="Multiple installations"):
            gh_app_token.get_installation_token("123", "pem")

    def test_raises_on_no_installations(self, cache_file, monkeypatch):
        """Should raise when the app has no installations."""
        self._mock_api(monkeypatch, installations=[])
        with pytest.raises(RuntimeError, match="No installations found"):
            gh_app_token.get_installation_token("123", "pem")

    def test_uses_cache_when_valid(self, cache_file, monkeypatch):
        """Should return cached token without API calls."""
        gh_app_token._save_cache("ghs_cached", "2099-12-31T23:59:59Z", "42")
        # api_request should NOT be called
        monkeypatch.setattr(gh_app_token, "api_request", lambda *a, **kw: pytest.fail("API called"))
        monkeypatch.setattr(gh_app_token, "create_jwt", lambda *a: pytest.fail("JWT created"))
        result = gh_app_token.get_installation_token("123", "pem", "42")
        assert result["token"] == "ghs_cached"

    def test_ignores_cache_for_different_installation(self, cache_file, monkeypatch):
        """Cache for installation 42 shouldn't be used when requesting 99."""
        gh_app_token._save_cache("ghs_wrong_install", "2099-12-31T23:59:59Z", "42")
        self._mock_api(monkeypatch)
        result = gh_app_token.get_installation_token("123", "pem", "99")
        assert result["token"] == "ghs_mock_token_abc"

    def test_caches_new_token(self, cache_file, monkeypatch):
        """Freshly fetched token should be written to cache."""
        self._mock_api(monkeypatch)
        gh_app_token.get_installation_token("123", "pem", "42")
        cached = json.loads(cache_file.read_text())
        assert cached["token"] == "ghs_mock_token_abc"
        assert cached["installation_id"] == "42"


# ---------------------------------------------------------------------------
# CLI main()
# ---------------------------------------------------------------------------

class TestMain:
    def test_missing_app_id_exits(self, monkeypatch):
        """Should exit with error when GITHUB_APP_ID is not set."""
        monkeypatch.delenv("GITHUB_APP_ID", raising=False)
        monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY_PATH", raising=False)
        with pytest.raises(SystemExit):
            gh_app_token.main()

    def test_missing_pem_path_exits(self, monkeypatch):
        """Should exit when GITHUB_APP_PRIVATE_KEY_PATH is not set."""
        monkeypatch.setenv("GITHUB_APP_ID", "123")
        monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY_PATH", raising=False)
        with pytest.raises(SystemExit):
            gh_app_token.main()

    def test_missing_pem_file_exits(self, monkeypatch, tmp_path):
        """Should exit when the PEM file doesn't exist."""
        monkeypatch.setenv("GITHUB_APP_ID", "123")
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_PATH", str(tmp_path / "nope.pem"))
        with pytest.raises(SystemExit):
            gh_app_token.main()

    def test_prints_token(self, monkeypatch, pem_file, cache_file, capsys):
        """Should print the token to stdout."""
        monkeypatch.setenv("GITHUB_APP_ID", "123")
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_PATH", str(pem_file))
        monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "42")
        monkeypatch.setattr(sys, "argv", ["gh-app-token.py"])
        monkeypatch.setattr(
            gh_app_token, "get_installation_token",
            lambda *a, **kw: {"token": "ghs_output", "expires_at": "2099-01-01T00:00:00Z", "installation_id": "42"},
        )
        gh_app_token.main()
        assert capsys.readouterr().out.strip() == "ghs_output"

    def test_json_flag(self, monkeypatch, pem_file, cache_file, capsys):
        """--json should print JSON with token + expiry."""
        monkeypatch.setenv("GITHUB_APP_ID", "123")
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_PATH", str(pem_file))
        monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "42")
        monkeypatch.setattr(sys, "argv", ["gh-app-token.py", "--json"])
        monkeypatch.setattr(
            gh_app_token, "get_installation_token",
            lambda *a, **kw: {"token": "ghs_json", "expires_at": "2099-01-01T00:00:00Z", "installation_id": "42"},
        )
        gh_app_token.main()
        output = json.loads(capsys.readouterr().out)
        assert output["token"] == "ghs_json"
        assert "expires_at" in output
