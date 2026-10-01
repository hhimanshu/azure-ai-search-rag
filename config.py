"""Shared config loader for the course notebooks.

Every notebook calls `load_config()` once at the top. Keeping this in one
place means a learner fixes a missing env var in one
spot instead of four notebooks.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

REQUIRED_VARS = [
    "AZURE_SEARCH_ENDPOINT",
    "AZURE_SEARCH_INDEX_NAME",
    "AZURE_STORAGE_ACCOUNT_URL",
    "AZURE_STORAGE_CONTAINER_NAME",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
    "AZURE_OPENAI_EMBEDDING_MODEL",
]


@dataclass
class Config:
    search_endpoint: str
    search_index_name: str
    storage_account_url: str
    storage_container_name: str
    openai_endpoint: str
    openai_embedding_deployment: str
    openai_embedding_model: str
    openai_chat_deployment: str
    openai_onyourdata_deployment: str
    ai_project_endpoint: str
    ai_services_endpoint: str
    ai_services_key: str
    subscription_id: str
    resource_group: str
    storage_account_name: str


def load_config() -> Config:
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        raise RuntimeError(
            "Missing required env vars: "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill these in, or re-run infra/deploy.sh "
            "and paste its output into .env."
        )
    return Config(
        search_endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        search_index_name=os.environ["AZURE_SEARCH_INDEX_NAME"],
        storage_account_url=os.environ["AZURE_STORAGE_ACCOUNT_URL"],
        storage_container_name=os.environ["AZURE_STORAGE_CONTAINER_NAME"],
        openai_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        openai_embedding_deployment=os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
        openai_embedding_model=os.environ["AZURE_OPENAI_EMBEDDING_MODEL"],
        openai_chat_deployment=os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-5-mini"),
        openai_onyourdata_deployment=os.environ.get("AZURE_OPENAI_ONYOURDATA_DEPLOYMENT", "gpt-4.1-mini"),
        ai_project_endpoint=os.environ.get("AZURE_AI_PROJECT_ENDPOINT", ""),
        ai_services_endpoint=os.environ.get("AZURE_AI_SERVICES_ENDPOINT", ""),
        ai_services_key=os.environ.get("AZURE_AI_SERVICES_KEY", ""),
        subscription_id=os.environ.get("AZURE_SUBSCRIPTION_ID", ""),
        resource_group=os.environ.get("AZURE_RESOURCE_GROUP", ""),
        storage_account_name=os.environ["AZURE_STORAGE_ACCOUNT_URL"]
        .split("//")[1]
        .split(".")[0],
    )
