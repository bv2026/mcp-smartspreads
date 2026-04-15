from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHWAB_ROOT = Path(r"C:\work\schwab-mcp-file")
RUN_DIR = ROOT / "run"
RUN_DIR.mkdir(exist_ok=True)

NEWSLETTER_STATE = RUN_DIR / "newsletter-mcp.json"
SCHWAB_STATE = RUN_DIR / "schwab-smartspreads-file.json"


def load_export_env(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not env_path.exists():
        return env

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or not line.startswith("export "):
            continue
        key_value = line[len("export ") :]
        if "=" not in key_value:
            continue
        key, value = key_value.split("=", 1)
        env[key] = value.strip().strip('"').strip("'")
    return env


def read_state(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def remove_state(path: Path) -> None:
    if path.exists():
        path.unlink()


def process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start_server(name: str, module: str, cwd: Path, env: dict[str, str], state_path: Path) -> None:
    state = read_state(state_path)
    if state and process_running(state["pid"]):
        print(f"{name} already running with PID {state['pid']}")
        return

    child_env = os.environ.copy()
    child_env.update(env)
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    proc = subprocess.Popen(
        [sys.executable, "-m", module],
        cwd=str(cwd),
        env=child_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    write_state(
        state_path,
        {
            "pid": proc.pid,
            "module": module,
            "cwd": str(cwd),
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
    )
    print(f"{name} started with PID {proc.pid}")


def stop_server(name: str, state_path: Path) -> None:
    state = read_state(state_path)
    if not state:
        print(f"{name} is not tracked.")
        return
    pid = state["pid"]
    if process_running(pid):
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"{name} stopped (PID {pid})")
    else:
        print(f"{name} was not running.")
    remove_state(state_path)


def status_server(name: str, state_path: Path) -> None:
    state = read_state(state_path)
    if not state:
        print(f"{name}: tracked=False running=False")
        return
    print(f"{name}: tracked=True running={process_running(state['pid'])} pid={state['pid']}")


def newsletter_env() -> dict[str, str]:
    return {
        "PYTHONPATH": str(ROOT / "src"),
        "NEWSLETTER_DATA_DIR": str(ROOT / "data"),
        "DATABASE_URL": "sqlite:///C:/work/SmartSpreads/newsletters.db",
    }


def schwab_env() -> dict[str, str]:
    env = {
        "PYTHONPATH": str(SCHWAB_ROOT / "src"),
        "SCHWAB_WATCHLIST_CONFIG": str(ROOT / "published" / "watchlist.yaml"),
        "SCHWAB_DB_PATH": str(SCHWAB_ROOT / "config" / "smartspreads.db"),
        "SCHWAB_DASHBOARD_PORT": "8766",
        "SCHWAB_TOKEN_PATH": str(Path.home() / ".schwab" / "token.json"),
        "SCHWAB_TOS_STATEMENT_PATH": r"C:\work\schwab-smartspreads-mcp\config\tos-statement.csv",
        "TOS_STATEMENT_PATH": r"C:\work\schwab-smartspreads-mcp\config\tos-statement.csv",
    }
    env.update(load_export_env(Path(r"C:\work\schwab-smartspreads-mcp\.env")))
    return env


def verify() -> None:
    status_server("newsletter-mcp", NEWSLETTER_STATE)
    status_server("schwab-smartspreads-file", SCHWAB_STATE)

    sys.path.insert(0, str(ROOT / "src"))
    from newsletter_mcp.config import Settings
    from newsletter_mcp.database import Database, Newsletter
    from sqlalchemy import func, select

    settings = Settings.from_env()
    database = Database(newsletter_env()["DATABASE_URL"])
    database.create_schema()
    with database.session() as session:
        count = session.execute(select(func.count(Newsletter.id))).scalar_one()

    print(f"newsletter_count={count}")
    print(f"newsletter_data_dir={settings.data_dir}")

    sys.path.insert(0, str(SCHWAB_ROOT / "src"))
    os.environ.update(schwab_env())
    from schwab_mcp.auth import check_token_age
    from schwab_mcp.config import load_watchlist_config, load_watchlist_metadata

    watchlist = load_watchlist_config()
    metadata = load_watchlist_metadata()
    token = check_token_age()

    print(f"schwab_watchlist_entries={len(watchlist)}")
    print(f"schwab_week_ending={metadata.get('week_ending')}")
    print(f"schwab_updated={metadata.get('updated')}")
    print(f"schwab_token_exists={token.get('exists')}")
    print(f"schwab_token_needs_reauth={token.get('needs_reauth')}")

    try:
        with urllib.request.urlopen("http://127.0.0.1:8766/dashboard", timeout=5) as response:
            print(f"schwab_dashboard_status={response.status}")
    except Exception:
        print("schwab_dashboard_status=unreachable")


def smoke() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from newsletter_mcp.server import get_watchlist, publish_issue

    publish_result = publish_issue("2026-04-10")
    watchlist = get_watchlist("2026-04-10")

    print(f"published_version={publish_result['publication_version']}")
    print(f"published_count={publish_result['watchlist_count']}")
    print(f"watchlist_entries={len(watchlist['entries'])}")
    print(f"watchlist_reference_present={watchlist.get('watchlist_reference') is not None}")

    sys.path.insert(0, str(SCHWAB_ROOT / "src"))
    os.environ.update(schwab_env())
    from schwab_mcp.config import load_watchlist_config, load_watchlist_metadata

    schwab_watchlist = load_watchlist_config()
    metadata = load_watchlist_metadata()
    print(f"schwab_seen_entries={len(schwab_watchlist)}")
    print(f"schwab_seen_week_ending={metadata.get('week_ending')}")
    print(f"schwab_first_entry={schwab_watchlist[0]['name'] if schwab_watchlist else 'none'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the local Phase 1 MCP stack.")
    parser.add_argument("command", choices=["start", "stop", "status", "verify", "smoke"])
    args = parser.parse_args()

    if args.command == "start":
        start_server("newsletter-mcp", "newsletter_mcp.server", ROOT, newsletter_env(), NEWSLETTER_STATE)
        start_server("schwab-smartspreads-file", "schwab_mcp.server", SCHWAB_ROOT, schwab_env(), SCHWAB_STATE)
    elif args.command == "stop":
        stop_server("newsletter-mcp", NEWSLETTER_STATE)
        stop_server("schwab-smartspreads-file", SCHWAB_STATE)
    elif args.command == "status":
        status_server("newsletter-mcp", NEWSLETTER_STATE)
        status_server("schwab-smartspreads-file", SCHWAB_STATE)
    elif args.command == "verify":
        verify()
    elif args.command == "smoke":
        smoke()


if __name__ == "__main__":
    main()
