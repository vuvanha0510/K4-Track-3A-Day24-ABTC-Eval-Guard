"""Shared configuration for K4 / Track 3A: Eval + Guardrail Stack."""

import os
import time
from dotenv import load_dotenv

load_dotenv()

# --- API Keys ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
HF_TOKEN = os.getenv("HF_TOKEN", "")  # Optional: for HuggingFace models
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# --- Gemini qua OpenAI-compat endpoint ---
GEMINI_BASE_URL = os.getenv(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
RAGAS_CHAT_MODEL = os.getenv("RAGAS_CHAT_MODEL", "gemini-3.5-flash-lite")
RAGAS_EMBED_MODEL = os.getenv("RAGAS_EMBED_MODEL", "gemini-embedding-001")
RAGAS_RPM_LIMIT = int(os.getenv("RAGAS_RPM_LIMIT", "9"))

# --- Retry cho free tier ---
# Gemini free tier giới hạn 15 request/phút/model; batch 20 câu Phase B hoặc
# latency 20 lượt Phase C sẽ vượt trần và nhận 429 nếu không backoff.
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "6"))
LLM_RETRY_BASE_S = float(os.getenv("LLM_RETRY_BASE_S", "8"))
# Giãn cách giữa hai mẫu latency (ngoài cửa sổ đo). Gemini free tier cho
# 15 request/phút/model nên 4.5s giữ dưới trần và mẫu đo được độ trễ thật
# của guard thay vì thời gian chờ 429.
LATENCY_SAMPLE_INTERVAL_S = float(os.getenv("LATENCY_SAMPLE_INTERVAL_S", "4.5"))

# Alias env: cho phép mọi `OpenAI()` trần (phase_b, judge_binary, NeMo Guardrails)
# trỏ sang Gemini mà không phải sửa từng call site.
# langchain-openai 0.1.x chỉ đọc OPENAI_API_BASE, OpenAI SDK đọc OPENAI_BASE_URL.
LLM_API_KEY = OPENAI_API_KEY or GEMINI_API_KEY
if GEMINI_API_KEY and not OPENAI_API_KEY:
    os.environ["OPENAI_API_KEY"] = GEMINI_API_KEY
    os.environ["OPENAI_BASE_URL"] = GEMINI_BASE_URL
    os.environ["OPENAI_API_BASE"] = GEMINI_BASE_URL

# --- Qdrant (same as Day 18) ---
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "lab24_production"
NAIVE_COLLECTION = "lab24_naive"

# --- Embedding (same as Day 18) ---
EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIM = 1024

# --- Chunking (same as Day 18) ---
HIERARCHICAL_PARENT_SIZE = 2048
HIERARCHICAL_CHILD_SIZE = 256
SEMANTIC_THRESHOLD = 0.85

# --- Search (same as Day 18) ---
BM25_TOP_K = 20
DENSE_TOP_K = 20
HYBRID_TOP_K = 20
RERANK_TOP_K = 3

# --- Paths ---
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT_DIR, "data")
FIXTURES_DIR = os.path.join(ROOT_DIR, "fixtures")
ARTIFACTS_DIR = os.path.join(ROOT_DIR, "artifacts")
TEST_SET_PATH = os.path.join(FIXTURES_DIR, "test_set_50q.json")
ANSWERS_PATH = os.path.join(ARTIFACTS_DIR, "answers_50q.json")
HUMAN_LABELS_PATH = os.path.join(FIXTURES_DIR, "human_labels_10q.json")
ADVERSARIAL_SET_PATH = os.path.join(FIXTURES_DIR, "adversarial_set_20.json")
CLEAN_SET_PATH = os.path.join(FIXTURES_DIR, "clean_set_8.json")
OUTPUT_SET_PATH = os.path.join(FIXTURES_DIR, "output_set_4.json")
GUARDRAILS_CONFIG_DIR = os.path.join(ROOT_DIR, "guardrails")
PAIR_QUESTION_IDS = (1, 5, 12, 21, 41)

# --- LLM Judge ---
GENERATION_MODEL = os.getenv("GENERATION_MODEL", "gemini-3.5-flash-lite")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gemini-3.5-flash-lite")

# --- Guardrail latency budget ---
LATENCY_BUDGET_P95_MS = 500  # Full guard target; Task 12 currently measures input guards only.
PRESIDIO_LANGUAGE = "en"    # Presidio base language; custom VN recognizers added via PatternRecognizer

# --- Day 18 enrichment compatibility ---
ENRICH_CACHE_PATH = os.path.join(ARTIFACTS_DIR, "enrich_cache.json")
ENRICH_MAX_CHUNKS = int(os.getenv("ENRICH_MAX_CHUNKS", "0"))
_LLM_DISABLED = False


def disable_llm(reason: str = "") -> None:
    """Disable optional enrichment LLM calls after quota or runtime failures."""
    global _LLM_DISABLED
    _LLM_DISABLED = True


def get_llm_client():
    """Return an OpenAI-compatible client/model for optional enrichment, or (None, model)."""
    if _LLM_DISABLED or not LLM_API_KEY:
        return None, GENERATION_MODEL
    try:
        from openai import OpenAI
    except Exception:
        return None, GENERATION_MODEL
    return OpenAI(api_key=LLM_API_KEY), GENERATION_MODEL


def is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(token in text for token in ("quota", "rate limit", "429", "insufficient_quota"))


def call_llm(func, *args, **kwargs):
    """Gọi LLM kèm exponential backoff khi gặp 429/quota.

    Chỉ chờ khi thật sự bị giới hạn tần suất; lỗi khác (sai payload, auth)
    ném ngay để lỗi thật không bị che bằng vài phút retry.
    """
    delay = LLM_RETRY_BASE_S
    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            if not is_quota_error(exc) or attempt == LLM_MAX_RETRIES:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
