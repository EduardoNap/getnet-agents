"""Runtime settings, read once from environment variables."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# List prices in USD per million tokens (input, output, cache read), used for the cost estimate in each response.

PRICES_PER_MTOK = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}
CACHE_WRITE_FACTOR = 1.25
STATE = Path(os.getenv("STATE_DIR", ROOT / "data" / "state"))  # database and demo keys; a volume in Docker


@dataclass(frozen=True)
class Settings:
    model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    router_model: str = os.getenv("ROUTER_MODEL") or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    verifier_model: str = os.getenv("VERIFIER_MODEL") or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    verifier_enabled: bool = os.getenv("VERIFIER", "on") != "off"
    agent_effort: str = os.getenv("AGENT_EFFORT", "medium")  # set explicitly: the default differs between models
    # The API key as a file, the way Docker and Kubernetes mount a secret. Unset: the SDK reads ANTHROPIC_API_KEY.
    anthropic_api_key_file: str = os.getenv("ANTHROPIC_API_KEY_FILE", "")
    data_dir: Path = ROOT / "data"
    chroma_dir: Path = Path(os.getenv("CHROMA_DIR", ROOT / "data" / "chroma"))
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    max_message_chars: int = 2000
    judge_model: str = os.getenv("JUDGE_MODEL", "claude-opus-5-5")  # grades answers in evals/, never writes them

    database_path: Path = Path(os.getenv("DATABASE_PATH", STATE / "app.db"))
    # The public keys that verify tokens: the login service's key set URL in production, a local file in the demo.
    auth_jwks_url: str = os.getenv("AUTH_JWKS_URL", "")
    auth_jwks_file: Path = Path(os.getenv("AUTH_JWKS_FILE", STATE / "keys" / "jwks.json"))
    auth_issuer: str = os.getenv("AUTH_ISSUER", "getnet-demo-idp")
    auth_audience: str = os.getenv("AUTH_AUDIENCE", "getnet-agents")

    max_specialist_runs: int = int(os.getenv("MAX_SPECIALIST_RUNS", "3"))  # per message, enforced in the router
    max_request_cost_usd: float = float(os.getenv("MAX_REQUEST_COST_USD", "0.50"))  # no new specialist run after this
    history_window: int = 6  # messages sent to the model verbatim
    summarize_after: int = 12  # messages outside the summary before it is rewritten
    sla_minutes_high: int = 30  # a fraud or complaint ticket is overdue after this
    sla_minutes_normal: int = 240
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))


settings = Settings()
