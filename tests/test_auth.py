"""Identity and authorization.

The token says who the person is. A lookup says which merchants that person may act for, and the
request body only chooses among those. Operators carry scopes, and each endpoint checks the one it needs.
"""
import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import auth, devtokens, store
from app.config import settings
from app.main import app
from app.tools import support_tools
from tests.conftest import auth_header

client = TestClient(app)
BODY = {"message": "When will the money from yesterday's sales be deposited?", "user_id": "cliente1988"}


def claims(**changes) -> dict:
    base = {
        "sub": "joao.silva",
        "role": "merchant",
        "iss": settings.auth_issuer,
        "aud": settings.auth_audience,
        "exp": int(time.time()) + 600,
    }
    return {**base, **changes}


def b64(data: dict | bytes) -> str:
    raw = data if isinstance(data, bytes) else json.dumps(data).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def signed_with_another_key() -> str:
    """A stranger's key, presented under the id of one of ours."""
    stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return jwt.encode(claims(), stranger, algorithm="RS256", headers={"kid": devtokens.key_ids()[-1]})


def unsigned() -> str:
    return f"{b64({'alg': 'none', 'typ': 'JWT', 'kid': devtokens.key_ids()[-1]})}.{b64(claims())}."


def signed_with_the_public_key_as_a_secret() -> str:
    """The classic confusion attack: HS256, using the server's public key as the shared secret."""
    kid = devtokens.key_ids()[-1]
    public_pem = devtokens.private_key(kid).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    signing_input = f"{b64({'alg': 'HS256', 'typ': 'JWT', 'kid': kid})}.{b64(claims())}"
    signature = hmac.new(public_pem, signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{b64(signature)}"


def ours(kid: str | None = None, **changes) -> str:
    kid = kid or devtokens.key_ids()[-1]
    return jwt.encode(claims(**changes), devtokens.private_key(kid), algorithm="RS256", headers={"kid": kid})


def with_an_unknown_key_id() -> str:
    key = devtokens.private_key(devtokens.key_ids()[-1])
    return jwt.encode(claims(), key, algorithm="RS256", headers={"kid": "retired-key"})


def without_a_key_id() -> str:
    return jwt.encode(claims(), devtokens.private_key(devtokens.key_ids()[-1]), algorithm="RS256")


def test_no_token_is_rejected(fake_llm):
    assert client.post("/chat", json=BODY).status_code == 401
    assert fake_llm.seen_messages == []


@pytest.mark.parametrize(
    "token",
    [
        lambda: "not-a-token",
        lambda: devtokens.issue_token("joao.silva", ttl_minutes=-1),  # expired
        signed_with_another_key,
        unsigned,
        signed_with_the_public_key_as_a_secret,
        lambda: ours(aud="another-service"),
        lambda: ours(iss="someone-else"),
        lambda: ours(role="admin"),
        without_a_key_id,
        with_an_unknown_key_id,
    ],
    ids=["malformed", "expired", "other-key", "unsigned", "key-confusion", "wrong-audience", "wrong-issuer", "unknown-role",
         "no-key-id", "unknown-key-id"],
)
def test_a_token_that_cannot_be_trusted_is_rejected(fake_llm, token):
    reply = client.post("/chat", json=BODY, headers={"Authorization": f"Bearer {token()}"})
    assert reply.status_code == 401
    assert fake_llm.seen_messages == []


# --- which merchants a person may act for ---------------------------------------------------


def test_a_person_cannot_act_for_a_merchant_they_do_not_belong_to(fake_llm):
    """The finding from the review: the caller used to choose user_id freely."""
    reply = client.post("/chat", json={**BODY, "user_id": "maria_2020"}, headers=auth_header("cliente1988"))
    assert reply.status_code == 403
    assert fake_llm.seen_messages == []  # nothing ran, so no tool could read anyone's data


def test_a_person_with_two_merchants_reaches_each_one_and_no_third(fake_llm):
    fake_llm.route = "support"
    fake_llm.tools_to_call = [("get_settlement_schedule", {})]
    joao = {"Authorization": f"Bearer {devtokens.issue_token('joao.silva')}"}
    accounts = {}
    for merchant in ("cliente1988", "mercado_lima"):
        reply = client.post("/chat", json={**BODY, "user_id": merchant}, headers=joao)
        assert reply.status_code == 200
        accounts[merchant] = fake_llm.tool_outputs[-1]["bank_account"]
    assert accounts["cliente1988"] != accounts["mercado_lima"]  # each request read the merchant it named
    assert client.post("/chat", json={**BODY, "user_id": "bistro_nonna"}, headers=joao).status_code == 403


def test_the_merchant_id_itself_is_not_a_login(fake_llm):
    """Version 2 treated the token subject as the merchant. Now it is looked up, and a merchant id is nobody."""
    token = {"Authorization": f"Bearer {devtokens.issue_token('cliente1988')}"}
    assert client.post("/chat", json=BODY, headers=token).status_code == 403


def test_an_inactive_membership_is_refused(fake_llm):
    pedro = {"Authorization": f"Bearer {devtokens.issue_token('pedro.lima')}"}  # left the company: inactive in users.json
    assert client.post("/chat", json=BODY, headers=pedro).status_code == 403

    store.set_membership("joao.silva", "cliente1988", "inactive")  # access is withdrawn: the next request is refused
    assert client.post("/chat", json=BODY, headers=auth_header("cliente1988")).status_code == 403
    assert fake_llm.seen_messages == []


def test_an_unknown_person_or_a_blocked_merchant_is_refused(fake_llm, monkeypatch):
    unknown = client.post("/chat", json={**BODY, "user_id": "nobody"}, headers=auth_header("nobody"))
    assert unknown.status_code == 403

    monkeypatch.setattr(support_tools, "account_status", lambda user_id: "blocked")
    assert client.post("/chat", json=BODY, headers=auth_header("cliente1988")).status_code == 403


def test_the_tools_read_the_merchant_the_lookup_returned(fake_llm):
    fake_llm.route = "support"
    fake_llm.tools_to_call = [("get_settlement_schedule", {})]
    reply = client.post("/chat", json={**BODY, "user_id": "maria_2020"}, headers=auth_header("maria_2020"))
    assert reply.status_code == 200
    assert fake_llm.tool_outputs[0]["bank_account"] == "Santander ****9988"  # maria's


def test_a_chat_request_records_which_person_acted_for_the_merchant(fake_llm):
    client.post("/chat", json=BODY, headers=auth_header("cliente1988"))
    entry = store.audit_entries("cliente1988")[0]
    assert (entry["actor"], entry["action"]) == ("joao.silva", "chat")


def test_a_person_reads_conversations_of_their_merchants_only(fake_llm):
    conversation_id = client.post("/chat", json=BODY, headers=auth_header("cliente1988")).json()["conversation_id"]
    assert client.get(f"/conversations/{conversation_id}", headers=auth_header("cliente1988")).status_code == 200
    # Someone else's and one that does not exist look the same, so ids cannot be probed.
    assert client.get(f"/conversations/{conversation_id}", headers=auth_header("maria_2020")).status_code == 404
    assert client.get("/conversations/no-such-id", headers=auth_header("maria_2020")).status_code == 404


# --- key rotation -------------------------------------------------------------------------


def test_two_keys_are_valid_at_once_so_a_key_can_be_rotated(fake_llm):
    older, newer = devtokens.key_ids()
    for kid in (older, newer):
        reply = client.post("/chat", json=BODY, headers={"Authorization": f"Bearer {ours(kid=kid)}"})
        assert reply.status_code == 200


def test_a_token_signed_with_a_removed_key_is_rejected(fake_llm):
    older, newer = devtokens.key_ids()
    old_token, new_token = ours(kid=older), ours(kid=newer)

    devtokens.rotate()  # a new key is added and the oldest is removed
    assert devtokens.key_ids()[0] == newer and len(devtokens.key_ids()) == 2
    assert client.post("/chat", json=BODY, headers={"Authorization": f"Bearer {old_token}"}).status_code == 401
    assert client.post("/chat", json=BODY, headers={"Authorization": f"Bearer {new_token}"}).status_code == 200  # no downtime
    assert client.post("/chat", json=BODY, headers=auth_header("cliente1988")).status_code == 200  # signed with the newest


def test_keys_come_from_the_login_services_url_when_one_is_set(monkeypatch):
    """Production: no key file. The key set is fetched from the identity provider and cached."""
    import dataclasses
    import io

    fetched = []

    def fake_open(_opener, request, *args, **kwargs):  # stands in for the HTTPS request to the login service
        fetched.append(request.full_url)
        return io.BytesIO(settings.auth_jwks_file.read_bytes())

    devtokens.ensure_keys()
    monkeypatch.setattr("urllib.request.OpenerDirector.open", fake_open)
    monkeypatch.setattr(auth, "settings", dataclasses.replace(settings, auth_jwks_url="https://login.example/jwks.json"))
    auth._jwks_client.cache_clear()

    assert auth.verify_token(ours()).subject == "joao.silva"
    assert auth.verify_token(ours()).subject == "joao.silva"
    assert fetched == ["https://login.example/jwks.json"]  # fetched once, then served from the cache
    auth._jwks_client.cache_clear()


# --- operators and scopes -------------------------------------------------------------------


def test_a_token_carries_the_operators_scopes():
    principal = auth.verify_token(devtokens.issue_token("ana", "operator", scopes=["tickets:read"]))
    assert (principal.subject, principal.role, principal.scopes) == ("ana", "operator", frozenset({"tickets:read"}))
    assert auth.verify_token(devtokens.issue_token("joao.silva")).scopes == frozenset()


def open_ticket(fake_llm) -> str:
    fake_llm.route = "escalation"
    return client.post("/chat", json=BODY, headers=auth_header("cliente1988")).json()["handoff"]["ticket_id"]


def test_an_operator_who_may_only_read_cannot_claim_or_reply(fake_llm):
    ticket_id = open_ticket(fake_llm)
    reader = auth_header("rita", "operator", scopes=["tickets:read"])
    assert client.get("/tickets", headers=reader).status_code == 200
    assert client.get(f"/tickets/{ticket_id}", headers=reader).status_code == 200
    assert client.post(f"/tickets/{ticket_id}/claim", headers=reader).status_code == 403
    assert client.post(f"/tickets/{ticket_id}/reply", json={"message": "Done."}, headers=reader).status_code == 403
    assert store.get_ticket(ticket_id)["status"] == "open"  # nothing changed


def test_approving_an_action_needs_its_own_scope(fake_llm):
    fake_llm.route = "support"
    fake_llm.tools_to_call = [("request_terminal_replacement", {"terminal_id": "GS-48213", "reason": "It will not turn on."})]
    client.post("/chat", json={**BODY, "message": "Please replace my Get Smart."}, headers=auth_header("cliente1988"))
    ticket_id = store.list_tickets("open")[0]["ticket_id"]

    agent = auth_header("bruno", "operator", scopes=["tickets:read", "tickets:write"])  # answers tickets, cannot approve
    assert client.post(f"/tickets/{ticket_id}/claim", headers=agent).status_code == 200
    assert client.post(f"/tickets/{ticket_id}/approve", headers=agent).status_code == 403
    assert client.post(f"/tickets/{ticket_id}/reject", json={"message": "No."}, headers=agent).status_code == 403
    assert store.action_for_ticket(ticket_id)["status"] == "pending"

    supervisor = auth_header("bruno", "operator", scopes=["tickets:read", "tickets:write", "actions:approve"])
    assert client.post(f"/tickets/{ticket_id}/approve", headers=supervisor).status_code == 200


# --- every endpoint, every kind of caller ----------------------------------------------------

ENDPOINTS = [  # (method, path, body, the scope an operator needs; None for merchant endpoints)
    ("POST", "/chat", BODY, None),
    ("GET", "/conversations/{conversation}", None, None),
    ("GET", "/tickets", None, "tickets:read"),
    ("GET", "/tickets/{ticket}", None, "tickets:read"),
    ("POST", "/tickets/{ticket}/claim", None, "tickets:write"),
    ("POST", "/tickets/{ticket}/release", None, "tickets:write"),
    ("POST", "/tickets/{ticket}/reply", {"message": "Done."}, "tickets:write"),
    ("POST", "/tickets/{ticket}/approve", None, "actions:approve"),
    ("POST", "/tickets/{ticket}/reject", {"message": "No."}, "actions:approve"),
]
ALL_SCOPES = ["tickets:read", "tickets:write", "actions:approve"]


def test_every_endpoint_is_listed_here():
    """A new endpoint must be added to the table, so it cannot ship without these checks."""
    served = {(method, route.path) for route in app.routes for method in getattr(route, "methods", ()) if route.path.startswith(("/chat", "/conversations", "/tickets"))}
    listed = {(method, path.replace("{conversation}", "{conversation_id}").replace("{ticket}", "{ticket_id}")) for method, path, _, _ in ENDPOINTS}
    assert {pair for pair in served if pair[0] in ("GET", "POST")} == listed


@pytest.mark.parametrize("method, path, body, scope", ENDPOINTS, ids=[f"{m} {p}" for m, p, _, _ in ENDPOINTS])
def test_who_may_call_each_endpoint(fake_llm, method, path, body, scope):
    fake_llm.route = "escalation"
    started = client.post("/chat", json=BODY, headers=auth_header("cliente1988")).json()
    url = path.format(conversation=started["conversation_id"], ticket=started["handoff"]["ticket_id"])

    def status(headers: dict | None) -> int:
        return client.request(method, url, json=body, headers=headers).status_code

    assert status(None) == 401
    assert status({"Authorization": "Bearer not-a-token"}) == 401
    if scope is None:  # a merchant endpoint
        assert status(auth_header("ana", "operator")) == 403  # operators do not speak as merchants
        outsider = status(auth_header("maria_2020"))  # a person of another merchant
        assert outsider == (404 if "conversations" in path else 403)
        assert status(auth_header("cliente1988")) == 200
    else:  # an operator endpoint
        assert status(auth_header("cliente1988")) == 403  # a merchant's person
        others = [s for s in ALL_SCOPES if s != scope]
        assert status(auth_header("ana", "operator", scopes=others)) == 403  # every scope but the one needed
        assert status(auth_header("ana", "operator", scopes=[])) == 403
        assert status(auth_header("ana", "operator", scopes=[scope])) != 403  # allowed; the ticket's own rules apply next
