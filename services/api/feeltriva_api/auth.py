from __future__ import annotations

import re
from dataclasses import dataclass, field

import jwt

from .errors import ApiError
from .settings import Settings

ASSESSMENT_SCOPES = frozenset(
    {"assessment:read", "assessment:write", "assessment:export", "assessment:delete", "knowledge:read"}
)
_DEV_TOKEN = re.compile(r"^(dev|dev-reviewer):([A-Za-z0-9_.@-]{1,128})$")


@dataclass(frozen=True)
class Principal:
    subject: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    roles: frozenset[str] = field(default_factory=frozenset)

    def require_scope(self, scope: str) -> None:
        if scope not in self.scopes:
            raise ApiError(403, "insufficient_scope", f"This action requires the {scope} permission.")

    def require_role(self, role: str) -> None:
        if role not in self.roles:
            raise ApiError(403, "forbidden", "You do not have access to this resource.")


def _unauthenticated() -> ApiError:
    return ApiError(401, "unauthenticated", "Authentication is required.")


class Authenticator:
    """Turns a bearer token into a Principal. The subject always comes from the verified
    token, never from a request body or a model-produced argument."""

    def __init__(self, settings: Settings, jwk_client: jwt.PyJWKClient | None = None) -> None:
        self._settings = settings
        self._jwks = jwk_client
        if settings.auth_mode == "jwt" and jwk_client is None and settings.auth_jwks_url:
            self._jwks = jwt.PyJWKClient(settings.auth_jwks_url)

    def authenticate(self, authorization: str | None) -> Principal:
        if not authorization or not authorization.startswith("Bearer "):
            raise _unauthenticated()
        token = authorization[len("Bearer ") :].strip()
        if self._settings.auth_mode == "mock":
            if not self._settings.is_local:  # defence in depth; Settings already refuses this
                raise _unauthenticated()
            match = _DEV_TOKEN.match(token)
            if not match:
                raise _unauthenticated()
            kind, name = match.groups()
            roles = frozenset({"reviewer"}) if kind == "dev-reviewer" else frozenset()
            return Principal(f"{kind}:{name}", ASSESSMENT_SCOPES, roles)
        if self._jwks is None:
            raise ApiError(503, "auth_not_configured", "Authentication is not configured.", retryable=False)
        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256", "ES256"],
                audience=self._settings.auth_audience,
                issuer=self._settings.auth_issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise _unauthenticated() from exc
        scope_claim = claims.get("scope", "")
        scopes = frozenset(scope_claim.split()) if isinstance(scope_claim, str) else frozenset()
        roles_claim = claims.get("roles", [])
        roles = (
            frozenset(r for r in roles_claim if isinstance(r, str)) if isinstance(roles_claim, list) else frozenset()
        )
        return Principal(str(claims["sub"]), scopes & ASSESSMENT_SCOPES, roles)
