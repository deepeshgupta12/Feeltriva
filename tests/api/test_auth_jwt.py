"""JWT verification path, exercised with a locally generated key (no identity provider)."""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from feeltriva_api.auth import Authenticator
from feeltriva_api.errors import ApiError
from feeltriva_api.settings import Settings

ISSUER, AUDIENCE = "https://issuer.test/", "feeltriva-api"


class _Keys:
    def __init__(self, public_key):
        self._public = public_key

    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": self._public})()


@pytest.fixture(scope="module")
def keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


@pytest.fixture
def auth(keypair):
    settings = Settings(_env_file=None, app_env="test", auth_mode="jwt", auth_issuer=ISSUER, auth_audience=AUDIENCE)
    return Authenticator(settings, jwk_client=_Keys(keypair[1]))


def _token(private, **overrides):
    claims = {
        "sub": "user-1",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": int(time.time()) + 300,
        "scope": "assessment:read assessment:write admin:everything",
        "roles": ["reviewer"],
    }
    claims.update(overrides)
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, private, algorithm="RS256")


def test_valid_token_yields_principal_with_only_known_scopes(auth, keypair):
    principal = auth.authenticate(f"Bearer {_token(keypair[0])}")
    assert principal.subject == "user-1"
    assert principal.scopes == {"assessment:read", "assessment:write"}  # unknown scope dropped
    assert principal.roles == {"reviewer"}
    with pytest.raises(ApiError) as denied:
        principal.require_scope("assessment:delete")
    assert denied.value.status == 403


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "another-api"},
        {"iss": "https://evil.test/"},
        {"exp": int(time.time()) - 10},
        {"sub": None},
        {"exp": None},
    ],
)
def test_wrong_audience_issuer_expiry_or_missing_claims_are_rejected(auth, keypair, overrides):
    with pytest.raises(ApiError) as err:
        auth.authenticate(f"Bearer {_token(keypair[0], **overrides)}")
    assert err.value.status == 401


def test_token_signed_by_another_key_or_unsigned_is_rejected(auth):
    stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(
        {"sub": "u", "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 300}, "s" * 32, algorithm="HS256"
    )
    for token in (_token(stranger), forged, "dev:someone", "garbage"):
        with pytest.raises(ApiError) as err:
            auth.authenticate(f"Bearer {token}")
        assert err.value.status == 401


def test_dev_tokens_are_not_accepted_in_jwt_mode_and_unconfigured_jwt_fails_closed(auth):
    with pytest.raises(ApiError):
        auth.authenticate("Bearer dev:someone")
    unconfigured = Authenticator(Settings(_env_file=None, app_env="test", auth_mode="jwt"))
    with pytest.raises(ApiError) as err:
        unconfigured.authenticate("Bearer anything")
    assert err.value.status == 503


def test_scopes_are_enforced_by_the_service(container, keypair):
    from feeltriva_api import schemas as sc
    from feeltriva_api.auth import Principal

    read_only = Principal("user-ro", frozenset({"assessment:read"}))
    with pytest.raises(ApiError) as err:
        container.assessments.start_session(read_only, sc.SessionCreate(consent_version="c"), "k1")
    assert (err.value.status, err.value.code) == (403, "insufficient_scope")
