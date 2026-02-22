"""
config.py - Settings and account storage
"""
import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path

APP_NAME = "BabyTankSwitcher"
APP_DATA_DIR = Path(os.getenv("APPDATA", Path.home())) / APP_NAME / "Configurations"
PROFILES_DIR = APP_DATA_DIR
SETTINGS_FILE = APP_DATA_DIR / "settings.json"
ACCOUNTS_FILE = APP_DATA_DIR / "accounts.json"
CREDENTIALS_FILENAME = "credentials.properties"
MANAGED_PLUGINS_FILE = APP_DATA_DIR / "managed_plugins.json"


def _detect_runelite_folder() -> str:
    return str(Path.home() / ".runelite")


def _detect_config_location() -> str:
    return str(APP_DATA_DIR)


def ensure_dirs():
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)


def read_account_name_from_credentials(credentials_path: Path) -> str:
    try:
        text = credentials_path.read_text(encoding="utf-8", errors="ignore")
        for key in ("JX_DISPLAY_NAME", "displayName", "display_name", "accountName",
                    "account_name", "username", "name", "id", "accountId"):
            for line in text.splitlines():
                line = line.strip()
                if line.lower().startswith(key.lower() + "="):
                    val = line.split("=", 1)[1].strip()
                    if val and not _looks_like_token(val):
                        return val
    except Exception:
        pass

    runelite_folder = credentials_path.parent
    profiles2 = runelite_folder / "profiles2"
    if profiles2.exists():
        try:
            profile_files = sorted(
                profiles2.glob("*.profile"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            if profile_files:
                name = profile_files[0].stem
                if name and name.lower() not in ("default", ""):
                    return name
        except Exception:
            pass

    if profiles2.exists():
        try:
            for pfile in sorted(profiles2.glob("*.profile"),
                                key=lambda p: p.stat().st_mtime, reverse=True):
                text = pfile.read_text(encoding="utf-8", errors="ignore")
                for line in text.splitlines():
                    line = line.strip()
                    for key in ("name", "displayName", "accountName"):
                        if line.lower().startswith(key.lower() + "="):
                            val = line.split("=", 1)[1].strip()
                            if val:
                                return val
        except Exception:
            pass

    return ""


def _looks_like_token(val: str) -> bool:
    return len(val) > 40 and " " not in val


# ── Managed plugins persistence ────────────────────────────────────────────────

def load_managed_plugins() -> set:
    """
    Load managed plugin classNames from disk.
    Returns empty set by default — all plugins start unmanaged.
    """
    try:
        if MANAGED_PLUGINS_FILE.exists():
            data = json.loads(MANAGED_PLUGINS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return set(data)
    except Exception:
        pass
    return set()


def save_managed_plugins(managed: set):
    """Persist managed plugin classNames to disk."""
    try:
        ensure_dirs()
        MANAGED_PLUGINS_FILE.write_text(
            json.dumps(sorted(managed), indent=2), encoding="utf-8")
    except Exception:
        pass


@dataclass
class ClientArgs:
    clean_jagex_launcher: bool = False
    developer_mode: bool = False
    debug_mode: bool = False
    microbot_debug: bool = False
    safe_mode: bool = False
    insecure_skip_tls: bool = False
    disable_telemetry: bool = False
    disable_walker_update: bool = False
    no_update: bool = False
    jav_config_url: str = ""
    profile: str = ""
    proxy_type: str = "None"
    ram_limitation: str = ""
    raw_args: str = ""

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ClientArgs":
        return ClientArgs(
            clean_jagex_launcher=d.get("clean_jagex_launcher", False),
            developer_mode=d.get("developer_mode", False),
            debug_mode=d.get("debug_mode", False),
            microbot_debug=d.get("microbot_debug", False),
            safe_mode=d.get("safe_mode", False),
            insecure_skip_tls=d.get("insecure_skip_tls", False),
            disable_telemetry=d.get("disable_telemetry", False),
            disable_walker_update=d.get("disable_walker_update", False),
            no_update=d.get("no_update", False),
            jav_config_url=d.get("jav_config_url", ""),
            profile=d.get("profile", ""),
            proxy_type=d.get("proxy_type", "None"),
            ram_limitation=d.get("ram_limitation", ""),
            raw_args=d.get("raw_args", ""),
        )

    def build_args(self) -> list:
        args = []
        if self.clean_jagex_launcher:  args.append("--clean-jagex-launcher")
        if self.developer_mode:        args.append("--developer-mode")
        if self.debug_mode:            args.append("--debug")
        if self.microbot_debug:        args.append("--microbot-debug")
        if self.safe_mode:             args.append("--safe-mode")
        if self.insecure_skip_tls:     args.append("--insecure-skip-tls-verification")
        if self.disable_telemetry:     args.append("--disable-telemetry")
        if self.disable_walker_update: args.append("--disable-walker-update")
        if self.no_update:             args.append("--no-update")
        if self.jav_config_url:        args += ["--jav-config", self.jav_config_url]
        if self.profile:               args += ["--profile", self.profile]
        if self.proxy_type and self.proxy_type != "None":
            args += ["--proxy-type", self.proxy_type]
        if self.ram_limitation:        args += ["--ram", self.ram_limitation]
        if self.raw_args:              args += self.raw_args.split()
        return args

    def has_any(self) -> bool:
        return bool(self.build_args())


@dataclass
class Account:
    display_name: str
    credentials_file: str
    client_args: ClientArgs = field(default_factory=ClientArgs)
    notes: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    http_port: int = 0
    skip_launch: bool = False  # if True, excluded from Launch All

    def to_dict(self):
        return {
            "display_name": self.display_name,
            "credentials_file": self.credentials_file,
            "client_args": self.client_args.to_dict(),
            "notes": self.notes,
            "id": self.id,
            "http_port": self.http_port,
            "skip_launch": self.skip_launch,
        }

    @staticmethod
    def from_dict(d: dict) -> "Account":
        ca = d.get("client_args", {})
        if isinstance(ca, dict):
            client_args = ClientArgs.from_dict(ca)
        else:
            client_args = ClientArgs()
        if not client_args.profile and d.get("runelite_profile"):
            client_args.profile = d.get("runelite_profile", "")
        return Account(
            display_name=d.get("display_name", ""),
            credentials_file=d.get("credentials_file", ""),
            client_args=client_args,
            notes=d.get("notes", ""),
            id=d.get("id", str(uuid.uuid4())),
            http_port=d.get("http_port", 0),
            skip_launch=d.get("skip_launch", False),
        )


@dataclass
class Settings:
    runelite_folder: str  = field(default_factory=_detect_runelite_folder)
    config_location: str  = field(default_factory=_detect_config_location)
    jar_path: str         = ""
    jvm_args: str         = "-Xmx512m"
    protect_process: bool = False

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Settings":
        return Settings(
            runelite_folder  = d.get("runelite_folder", _detect_runelite_folder()),
            config_location  = d.get("config_location", _detect_config_location()),
            jar_path         = d.get("jar_path", ""),
            jvm_args         = d.get("jvm_args", "-Xmx512m"),
            protect_process  = d.get("protect_process", False),
        )

    @property
    def credentials_path(self) -> Path:
        return Path(self.runelite_folder) / CREDENTIALS_FILENAME


def load_settings() -> Settings:
    ensure_dirs()
    if SETTINGS_FILE.exists():
        try:
            return Settings.from_dict(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return Settings()


def save_settings(s: Settings):
    ensure_dirs()
    SETTINGS_FILE.write_text(json.dumps(s.to_dict(), indent=2), encoding="utf-8")


def load_accounts() -> list:
    ensure_dirs()
    if ACCOUNTS_FILE.exists():
        try:
            data = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
            return [Account.from_dict(a) for a in data]
        except Exception:
            pass
    return []


def save_accounts(accounts: list):
    ensure_dirs()
    ACCOUNTS_FILE.write_text(
        json.dumps([a.to_dict() for a in accounts], indent=2), encoding="utf-8"
    )
