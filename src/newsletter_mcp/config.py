from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(os.getenv("NEWSLETTER_DATA_DIR", Path.cwd() / "data"))
        database_url = os.getenv(
            "DATABASE_URL",
            f"sqlite:///{(Path.cwd() / 'newsletters.db').as_posix()}",
        )
        return cls(data_dir=root, database_url=database_url)

