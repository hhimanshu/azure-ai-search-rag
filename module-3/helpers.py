"""Module 3 helpers. Each function wraps one SDK class or API and names the clip that uses it."""

import math
import random
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from openai import AzureOpenAI, RateLimitError

from config import load_config

# ---- Setup: clients, deployments, and file paths ----

config = load_config()
credential = DefaultAzureCredential()
search_client = SearchClient(config.search_endpoint, config.search_index_name, credential)

token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
openai_client = AzureOpenAI(
    azure_endpoint=config.openai_endpoint,
    azure_ad_token_provider=token_provider,
    api_version="2024-10-21",
)

ONYOURDATA_DEPLOYMENT = config.openai_onyourdata_deployment  # gpt-4.1-mini
CHAT_DEPLOYMENT = config.openai_chat_deployment  # gpt-5-mini
INDEX_NAME = config.search_index_name

HERO_QUESTION = "What's the speed limit in a school zone?"

EVAL_SET = str(ROOT / "eval" / "eval_set.jsonl")
EVAL_RESULTS = str(ROOT / "eval" / "eval_results.json")

# evaluate() calls the pipeline concurrently; the semaphore keeps it under the deployment's rate limit.
CHAT_SEMAPHORE = threading.Semaphore(3)


# ---- Clip 1: the managed "on your data" call ----


def print_answer_and_citations(answer, citations):
    """Chat completion `context.citations`: prints the answer and the start of each cited passage."""
    print("Answer:")
    print(answer)
    print()
    print(f"{len(citations)} citation(s):")
    for c in citations[:5]:
        print(f"  - {c.get('title')}: {c.get('content', '')[:150].strip()}...")


# ---- Clip 2: the grounded pipeline, built by hand ----


def format_context(passages):
    """Search results: labels each retrieved passage with its state, ready for the prompt."""
    return "\n\n".join(f"[{p['state']}] {p['chunk']}" for p in passages)


def chat_completion_with_retry(**kwargs):
    """AzureOpenAI chat.completions.create: retries on rate limits, with at most 3 calls at once."""
    with CHAT_SEMAPHORE:
        for attempt in range(8):
            try:
                return openai_client.chat.completions.create(**kwargs)
            except RateLimitError:
                if attempt == 7:
                    raise
                time.sleep(min(2 ** attempt, 30) + random.random())


# ---- Clip 3: measuring the pipeline ----


def print_metrics(eval_result):
    """evaluate() result: prints each metric the run returned."""
    for name, value in sorted(eval_result["metrics"].items()):
        print(f"{name}: {value}")


def lowest_retrieval_row(rows):
    """evaluate() rows: finds and prints the lowest retrieval score, skipping rows that have none."""

    def has_score(row):
        value = row.get("outputs.retrieval.retrieval")
        return isinstance(value, (int, float)) and not math.isnan(value)

    scored = [r for r in rows if has_score(r)]
    print("Rows without a retrieval score:", len(rows) - len(scored))

    worst = sorted(
        scored,
        key=lambda r: (r["outputs.retrieval.retrieval"], -r.get("outputs.groundedness.groundedness", 0)),
    )[0]
    print("Lowest-retrieval row:")
    print(" query:", worst.get("inputs.query"))
    print(" expected state:", worst.get("inputs.state"))
    print(" retrieval score:", worst.get("outputs.retrieval.retrieval"))
    print(" groundedness score:", worst.get("outputs.groundedness.groundedness"))
    print(" answer:", worst.get("outputs.response", "")[:200])
    return worst
