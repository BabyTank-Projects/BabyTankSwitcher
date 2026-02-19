"""
switcher.py - Core logic: save/switch credentials, launch, kill.
"""
import shutil
import subprocess
import uuid
from pathlib import Path

import psutil

from config import Account, Settings, PROFILES_DIR, CREDENTIALS_FILENAME, ensure_dirs


class SwitcherError(Exception):
    pass


# account_id -> psutil.Process
_running: dict = {}


def get_active_credentials_path(settings: Settings) -> Path:
    return Path(settings.runelite_folder) / CREDENTIALS_FILENAME


def credentials_exist(settings: Settings) -> bool:
    return get_active_credentials_path(settings).exists()


def import_current_credentials(account: Account, settings: Settings) -> None:
    """Copy the live credentials.properties into profiles folder for this account."""
    src = get_active_credentials_path(settings)
    if not src.exists():
        raise SwitcherError(
            f"credentials.properties not found at:\n{src}\n\n"
            "Launch RuneLite or Microbot via the Jagex Launcher first so it writes the credentials file."
        )
    ensure_dirs()
    dest = PROFILES_DIR / account.credentials_file
    shutil.copy2(src, dest)


def switch_to(account: Account, settings: Settings) -> None:
    """Overwrite the live credentials.properties with this account's saved copy."""
    src = PROFILES_DIR / account.credentials_file
    if not src.exists():
        raise SwitcherError(
            f"No saved credentials for '{account.display_name}'.\n"
            "Select the account and click 'Import Account' after logging in via Jagex Launcher."
        )
    dest = get_active_credentials_path(settings)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def has_credentials(account: Account) -> bool:
    return (PROFILES_DIR / account.credentials_file).exists()


def launch(account: Account, settings: Settings) -> int:
    """Switch credentials then launch the jar. Returns the PID."""
    switch_to(account, settings)

    if not settings.jar_path:
        raise SwitcherError(
            "No Microbot jar configured.\nGo to Settings and set the Microbot Jar Location."
        )
    jar = Path(settings.jar_path)
    if not jar.exists():
        raise SwitcherError(f"Jar file not found:\n{jar}")

    cmd = ["java"]
    jvm_args = settings.jvm_args.split() if settings.jvm_args.strip() else []
    # RuneLite requires -ea when developer mode is on
    if account.client_args.developer_mode and "-ea" not in jvm_args:
        jvm_args.append("-ea")
    cmd += jvm_args
    cmd += ["-jar", str(jar)]
    cmd += account.client_args.build_args()

    proc = subprocess.Popen(
        cmd,
        cwd=str(jar.parent),
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    ps_proc = psutil.Process(proc.pid)
    _running[account.id] = ps_proc
    return proc.pid


def kill(account: Account) -> None:
    proc = _running.get(account.id)
    if proc is None:
        raise SwitcherError(f"No tracked process for '{account.display_name}'.")
    try:
        for child in proc.children(recursive=True):
            child.kill()
        proc.kill()
    except psutil.NoSuchProcess:
        pass
    _running.pop(account.id, None)


def is_running(account: Account) -> bool:
    proc = _running.get(account.id)
    if proc is None:
        return False
    try:
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        _running.pop(account.id, None)
        return False


def get_pid(account: Account):
    proc = _running.get(account.id)
    if proc and is_running(account):
        return proc.pid
    return None


def new_credentials_filename(display_name: str = "") -> str:
    if display_name:
        return f"credentials.properties.{display_name}"
    return f"credentials.properties.{uuid.uuid4().hex[:12]}"
