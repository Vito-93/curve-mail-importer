from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_user: str
    imap_password: str
    imap_folder: str = "curve-receipts"

    firefly_base_url: str
    firefly_access_token: str
    firefly_source_account: str

    destination_rules_path: str = "/config/destination_rules.yaml"

    poll_interval_seconds: int = 300

    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
