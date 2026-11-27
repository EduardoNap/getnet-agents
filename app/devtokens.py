"""Token issuer. It stands in for the identity provider, and the service imports nothing from it.

    python -m app.devtokens joao.silva                      # a person who may act for cliente1988 and mercado_lima
    python -m app.devtokens ana --role operator             # an operator with every scope
    python -m app.devtokens rita --role operator --scopes tickets:read
    python -m app.devtokens --rotate                        # add a new signing key and retire the oldest

Two key pairs exist at any time and the newest signs. The public halves are published as a key set
(`jwks.json`), which is what the service reads. In production there is no private key anywhere near
this service: the key set comes from the login service's URL (`AUTH_JWKS_URL`).
"""
import argparse
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import settings

PRIVATE_KEYS_FILE = settings.auth_jwks_file.with_name("private.json")  # [{"kid", "pem"}], oldest first
OPERATOR_SCOPES = ["tickets:read", "tickets:write", "actions:approve"]
KEYS_KEPT = 2


def _new_key() -> dict:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return {"kid": uuid.uuid4().hex[:12], "pem": pem.decode()}


def _write(path, text: str, private: bool = False) -> None:
    """Written beside the file and then moved into place, so the service never reads half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(text)
    if private:
        temporary.chmod(0o600)
    os.replace(temporary, path)


def _save(keys: list[dict]) -> None:
    published = []
    for entry in keys:
        public = serialization.load_pem_private_key(entry["pem"].encode(), password=None).public_key()
        published.append(jwt.algorithms.RSAAlgorithm.to_jwk(public, as_dict=True) | {"kid": entry["kid"], "use": "sig", "alg": "RS256"})
    _write(PRIVATE_KEYS_FILE, json.dumps(keys), private=True)
    _write(settings.auth_jwks_file, json.dumps({"keys": published}, indent=2))


def _keys() -> list[dict]:
    if not (PRIVATE_KEYS_FILE.exists() and settings.auth_jwks_file.exists()):
        _save([_new_key() for _ in range(KEYS_KEPT)])
    return json.loads(PRIVATE_KEYS_FILE.read_text())


def ensure_keys() -> None:
    _keys()


def key_ids() -> list[str]:
    """The ids of the keys currently valid, oldest first. The last one signs."""
    return [entry["kid"] for entry in _keys()]


def private_key(kid: str):
    pem = next(entry["pem"] for entry in _keys() if entry["kid"] == kid)
    return serialization.load_pem_private_key(pem.encode(), password=None)


def rotate() -> str:
    """Add a new signing key and retire the oldest. Tokens signed with the key that stays keep working."""
    keys = (_keys() + [_new_key()])[-KEYS_KEPT:]
    _save(keys)
    return keys[-1]["kid"]


def issue_token(subject: str, role: str = "merchant", ttl_minutes: int = 60, scopes: list[str] | None = None) -> str:
    kid = key_ids()[-1]
    now = datetime.now(timezone.utc)
    if scopes is None:
        scopes = OPERATOR_SCOPES if role == "operator" else []
    claims = {
        "sub": subject,
        "role": role,
        "scope": " ".join(scopes),
        "iss": settings.auth_issuer,
        "aud": settings.auth_audience,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(claims, private_key(kid), algorithm="RS256", headers={"kid": kid})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Issue a demo token, or rotate the demo signing keys.")
    parser.add_argument("subject", nargs="?", help="the person signing in (for example joao.silva) or the operator's name")
    parser.add_argument("--role", choices=["merchant", "operator"], default="merchant")
    parser.add_argument("--scopes", nargs="*", help=f"an operator's scopes; default: {' '.join(OPERATOR_SCOPES)}")
    parser.add_argument("--ttl-minutes", type=int, default=60)
    parser.add_argument("--rotate", action="store_true", help="add a new signing key and retire the oldest")
    args = parser.parse_args()
    if args.rotate:
        print(f"now signing with key {rotate()}; valid keys: {', '.join(key_ids())}")
    elif not args.subject:
        parser.error("give a subject, or --rotate")
    else:
        print(issue_token(args.subject, args.role, args.ttl_minutes, args.scopes))
