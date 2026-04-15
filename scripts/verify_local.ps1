$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

@'
from newsletter_mcp.config import Settings
from newsletter_mcp.database import Database, Newsletter
from sqlalchemy import select, func

settings = Settings.from_env()
database = Database(settings.database_url)
database.create_schema()

with database.session() as session:
    count = session.execute(select(func.count(Newsletter.id))).scalar_one()

print("CONFIG")
print(f"data_dir={settings.data_dir}")
print(f"database_url={settings.database_url}")
print("STATUS")
print("import_ok=True")
print(f"newsletter_count={count}")
'@ | python -
