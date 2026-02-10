from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from loguru import logger


@dataclass
class DropboxConfig:
    """Configuration for Dropbox integration."""

    app_key: str = ""
    app_secret: str = ""
    refresh_token: str = ""
    remote_shared_folder: str = "/qlib_shared"  # Scanner uploads here
    remote_rdagent_folder: str = "/qlib_shared/rdagent_outputs"  # We upload here
    local_download_dir: str = "data/shared_import"  # Where we download scanner data
    local_factors_dir: str = "data/factors"  # Where we store discovered factors


@dataclass
class LLMConfig:
    """Configuration for LLM providers (Volcengine + AIHUBMIX).

    Chat inference uses Volcengine (火山引擎) with ``glm-4.7``.
    Embeddings use AIHUBMIX with ``text-embedding-3-small`` because
    Volcengine does not support embedding endpoints.
    """

    chat_model: str = "volcengine/glm-4.7"
    embedding_model: str = "aihubmix/text-embedding-3-small"
    volcengine_api_key: str = ""
    volcengine_base_url: str = "https://ark.cn-beijing.volces.com/api/coding/v3"
    aihubmix_api_key: str = ""
    aihubmix_base_url: str = "https://aihubmix.com/v1"
    litellm_config_path: str = "litellm_config.yaml"
    max_concurrent_requests: int = 3
    request_timeout: int = 120


@dataclass
class RDAgentConfig:
    """Configuration for Microsoft RD-Agent Qlib scenario."""

    rdagent_source: str = ""  # Path to cloned RD-Agent repo (empty = use pip installed)
    conda_env_name: str = "rdagent4qlib"
    workspace_dir: str = "workspace"
    qlib_data_path: str = "data/qlib"  # Qlib binary data (extracted from scanner's zip)
    max_iterations: int = 10  # Max RD-Agent evolution iterations
    scenario: str = "qlib"  # RD-Agent scenario type


@dataclass
class AppConfig:
    """Main application configuration."""

    dropbox: DropboxConfig = field(default_factory=DropboxConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    rdagent: RDAgentConfig = field(default_factory=RDAgentConfig)
    log_level: str = "INFO"


def _mask_secret(value: str) -> str:
    """Mask API keys/secrets for logging (show first 4 chars + ***)."""
    if not value or len(value) <= 4:
        return "***"
    return f"{value[:4]}***"


def load_config() -> AppConfig:
    """Load configuration from environment variables and .env file.

    Environment variable mapping (all optional, defaults used if not set):
    - DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN
    - DROPBOX_REMOTE_SHARED_FOLDER, DROPBOX_REMOTE_RDAGENT_FOLDER
    - DROPBOX_LOCAL_DOWNLOAD_DIR, DROPBOX_LOCAL_FACTORS_DIR
    - VOLCENGINE_API_KEY, VOLCENGINE_BASE_URL
    - AIHUBMIX_API_KEY, AIHUBMIX_BASE_URL
    - CHAT_MODEL, EMBEDDING_MODEL
    - LITELLM_CONFIG_PATH
    - MAX_CONCURRENT_REQUESTS, REQUEST_TIMEOUT
    - RDAGENT_SOURCE, CONDA_ENV_NAME
    - RDAGENT_WORKSPACE, QLIB_DATA_PATH
    - MAX_ITERATIONS, SCENARIO
    - LOG_LEVEL

    Returns:
        AppConfig: Loaded configuration with all settings.
    """
    # Load .env file if present
    load_dotenv()

    # Build DropboxConfig
    dropbox = DropboxConfig(
        app_key=os.getenv("DROPBOX_APP_KEY", ""),
        app_secret=os.getenv("DROPBOX_APP_SECRET", ""),
        refresh_token=os.getenv("DROPBOX_REFRESH_TOKEN", ""),
        remote_shared_folder=os.getenv("DROPBOX_REMOTE_SHARED_FOLDER", "/qlib_shared"),
        remote_rdagent_folder=os.getenv(
            "DROPBOX_REMOTE_RDAGENT_FOLDER", "/qlib_shared/rdagent_outputs"
        ),
        local_download_dir=os.getenv(
            "DROPBOX_LOCAL_DOWNLOAD_DIR", "data/shared_import"
        ),
        local_factors_dir=os.getenv("DROPBOX_LOCAL_FACTORS_DIR", "data/factors"),
    )

    # Build LLMConfig
    llm = LLMConfig(
        chat_model=os.getenv("CHAT_MODEL", "volcengine/glm-4.7"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "aihubmix/text-embedding-3-small"),
        volcengine_api_key=os.getenv("VOLCENGINE_API_KEY", ""),
        volcengine_base_url=os.getenv(
            "VOLCENGINE_BASE_URL",
            "https://ark.cn-beijing.volces.com/api/coding/v3",
        ),
        aihubmix_api_key=os.getenv("AIHUBMIX_API_KEY", ""),
        aihubmix_base_url=os.getenv("AIHUBMIX_BASE_URL", "https://aihubmix.com/v1"),
        litellm_config_path=os.getenv("LITELLM_CONFIG_PATH", "litellm_config.yaml"),
        max_concurrent_requests=int(os.getenv("MAX_CONCURRENT_REQUESTS", "3")),
        request_timeout=int(os.getenv("REQUEST_TIMEOUT", "120")),
    )

    # Build RDAgentConfig
    rdagent = RDAgentConfig(
        rdagent_source=os.getenv("RDAGENT_SOURCE", ""),
        conda_env_name=os.getenv("CONDA_ENV_NAME", "rdagent4qlib"),
        workspace_dir=os.getenv("RDAGENT_WORKSPACE", "workspace"),
        qlib_data_path=os.getenv("QLIB_DATA_PATH", "data/qlib"),
        max_iterations=int(os.getenv("MAX_ITERATIONS", "10")),
        scenario=os.getenv("SCENARIO", "qlib"),
    )

    # Build AppConfig
    config = AppConfig(
        dropbox=dropbox,
        llm=llm,
        rdagent=rdagent,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )

    # Log configuration summary (mask secrets)
    logger.info("Configuration loaded:")
    logger.info("  Dropbox:")
    logger.info("    app_key: {}", _mask_secret(config.dropbox.app_key))
    logger.info("    app_secret: {}", _mask_secret(config.dropbox.app_secret))
    logger.info("    refresh_token: {}", _mask_secret(config.dropbox.refresh_token))
    logger.info("    remote_shared_folder: {}", config.dropbox.remote_shared_folder)
    logger.info("    remote_rdagent_folder: {}", config.dropbox.remote_rdagent_folder)
    logger.info("    local_download_dir: {}", config.dropbox.local_download_dir)
    logger.info("    local_factors_dir: {}", config.dropbox.local_factors_dir)
    logger.info("  LLM:")
    logger.info("    chat_model: {}", config.llm.chat_model)
    logger.info("    embedding_model: {}", config.llm.embedding_model)
    logger.info(
        "    volcengine_api_key: {}", _mask_secret(config.llm.volcengine_api_key)
    )
    logger.info("    volcengine_base_url: {}", config.llm.volcengine_base_url)
    logger.info("    aihubmix_api_key: {}", _mask_secret(config.llm.aihubmix_api_key))
    logger.info("    aihubmix_base_url: {}", config.llm.aihubmix_base_url)
    logger.info("    litellm_config_path: {}", config.llm.litellm_config_path)
    logger.info("    max_concurrent_requests: {}", config.llm.max_concurrent_requests)
    logger.info("    request_timeout: {}", config.llm.request_timeout)
    logger.info("  RDAgent:")
    logger.info(
        "    rdagent_source: {}", config.rdagent.rdagent_source or "(use pip installed)"
    )
    logger.info("    conda_env_name: {}", config.rdagent.conda_env_name)
    logger.info("    workspace_dir: {}", config.rdagent.workspace_dir)
    logger.info("    qlib_data_path: {}", config.rdagent.qlib_data_path)
    logger.info("    max_iterations: {}", config.rdagent.max_iterations)
    logger.info("    scenario: {}", config.rdagent.scenario)
    logger.info("  log_level: {}", config.log_level)

    return config
