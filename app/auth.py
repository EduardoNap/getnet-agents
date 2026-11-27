"""Who is calling, and what they may do.

Authentication: a signed token is verified into a Principal, and nothing else is trusted. The service
holds only public keys.

Authorization is a lookup, not a claim. A merchant side token names a person; the `memberships` table
says which merchants that person may act for. An operator's token carries scopes, and each endpoint
checks the one it needs.
"""
import logging
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import store
from app.config import settings
from app.tools import support_tools

logger = logging.getLogger("getnet")
_bearer = HTTPBearer(auto_error=False)


class AuthError(Exception):
    """The token cannot be trusted."""


@dataclass(frozen=True)
class Principal:
    subject: str  # the person signing in, or the operator's name. Never a merchant id.
    role: str  # merchant | operator
    scopes: frozenset[str] = frozenset()  # what an operator may do: tickets:read, tickets:write, actions:approve


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    # Caches the key set for five minutes and fetches it again when a token names a key it has not seen,
    # so a key added by the login service is picked up without a restart.
    return jwt.PyJWKClient(url, cache_jwk_set=True, lifespan=300, timeout=5)


def _signing_key(token: str):
    """The public key the token says it was signed with. Several keys are valid at once, so keys can rotate."""
    try:
        key_id = jwt.get_unverified_header(token).get("kid")
        if not key_id:
            raise AuthError("token names no key")
        if settings.auth_jwks_url:
            return _jwks_client(settings.auth_jwks_url).get_signing_key(key_id).key
        key_set = jwt.PyJWKSet.from_json(settings.auth_jwks_file.read_text())
    except OSError as exc:
        raise AuthError("no key set configured") from exc
    except jwt.PyJWTError as exc:  # a malformed token, an unreadable key set, or a key the login service does not list
        raise AuthError(str(exc)) from exc
    for key in key_set.keys:
        if key.key_id == key_id:
            return key.key
    raise AuthError("token signed with a key that is not in the key set")


def verify_token(token: str) -> Principal:
    key = _signing_key(token)
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],  # one algorithm, so a token cannot pick a weaker one
            audience=settings.auth_audience,
            issuer=settings.auth_issuer,
            options={"require": ["exp", "sub", "iss", "aud"]},
        )
    except jwt.InvalidTokenError as exc:
        raise AuthError(str(exc)) from exc
    if claims.get("role") not in ("merchant", "operator"):
        raise AuthError("token has no known role")
    return Principal(subject=claims["sub"], role=claims["role"], scopes=frozenset(str(claims.get("scope", "")).split()))


def require_principal(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Principal:
    """Authentication: 401 unless the request carries a token we can verify."""
    unauthorized = HTTPException(401, "missing or invalid token", headers={"WWW-Authenticate": "Bearer"})
    if credentials is None:
        raise unauthorized
    try:
        return verify_token(credentials.credentials)
    except AuthError as exc:
        logger.warning("token rejected: %s", exc)  # the reason stays in the log, not in the response
        raise unauthorized from exc


def require_merchant_user(principal: Principal = Depends(require_principal)) -> Principal:
    """A person who signs in for merchants. Which merchants is decided per request, by `may_act_for`."""
    if principal.role != "merchant":
        raise HTTPException(403, "not allowed")
    return principal


def _membership(principal: Principal, merchant_id: str) -> dict | None:
    """The lookup: this person's active membership of this merchant, when the merchant's account is active too."""
    if principal.role != "merchant":
        return None
    row = store.membership(principal.subject, merchant_id)
    if row and row["status"] == "active" and support_tools.account_status(row["merchant_id"]) == "active":
        return row
    return None


def may_act_for(principal: Principal, merchant_id: str) -> bool:
    return _membership(principal, merchant_id) is not None


def act_for(principal: Principal, merchant_id: str) -> str:
    """The merchant id to run the request for. It is read from the lookup; the request only chose among the person's merchants."""
    row = _membership(principal, merchant_id)
    if row is None:
        logger.warning("%s may not act for %s", principal.subject, merchant_id)
        raise HTTPException(403, "not allowed")
    return row["merchant_id"]


def require_scope(scope: str):
    """A dependency for operator endpoints: 403 unless the caller is an operator whose token carries this scope."""

    def check(principal: Principal = Depends(require_principal)) -> Principal:
        if principal.role != "operator" or scope not in principal.scopes:
            raise HTTPException(403, "not allowed")
        return principal

    return check
