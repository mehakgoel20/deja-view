import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
RCA_DIR = BACKEND_DIR.parent

load_dotenv(BACKEND_DIR / ".env")

# The 1383-entry gold set described in DATASET_REPORT.md.
GOLD_PATH = Path(os.getenv("RCA_GOLD_PATH", RCA_DIR / "gold_incidents.json"))

DATA_DIR = BACKEND_DIR / "data"
INDEX_DIR = BACKEND_DIR / "index"
EVAL_DIR = DATA_DIR / "eval"

CLEAN_PATH = DATA_DIR / "gold_clean.json"
SPLIT_PATH = DATA_DIR / "split.json"
EMB_PATH = DATA_DIR / "embeddings.npy"
EMB_META_PATH = DATA_DIR / "embeddings_meta.json"

EMBED_MODEL = os.getenv("RCA_EMBED_MODEL", "text-embedding-3-small")
LLM_MODEL = os.getenv("RCA_LLM_MODEL", "gpt-4.1-mini")
# Point the LLM at any OpenAI-compatible server, e.g. Ollama:
#   RCA_LLM_BASE_URL=http://localhost:11434/v1  RCA_LLM_MODEL=qwen3:8b
# Unset means OpenAI. Embeddings always use OpenAI.
LLM_BASE_URL = os.getenv("RCA_LLM_BASE_URL") or None
# Sent as reasoning_effort when set. "none" turns off Qwen3's thinking, which
# is ~15x faster on a laptop. Defaults to "none" for local servers.
LLM_REASONING = os.getenv("RCA_LLM_REASONING", "none" if LLM_BASE_URL else "") or None
# LLM rerank of retrieved incidents. Off by default for local models: on an
# 8B model it doubles latency and scores candidates poorly.
RERANK = os.getenv("RCA_RERANK", "0" if LLM_BASE_URL else "1") == "1"

CATEGORIES = [
    "configuration_deployment",
    "database_issue",
    "api_latency",
    "other",
    "hardware_infra",
    "networking_dns",
    "authentication",
    "payment_processing",
    "security_incident",
    "concurrency_race_condition",
    "memory_leak",
]
SEVERITIES = ["Low", "Medium", "High", "Critical"]

TEST_FRACTION = 0.2
SPLIT_SEED = 42
