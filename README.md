# Baby Tank Switcher

A Windows tool for managing multiple Microbot/RuneLite accounts linked to a single Jagex account. Handles credential swapping, client launching, and live bot monitoring — all from one interface.

---

## Download

👉 **[Latest Release](../../releases/latest)** — download `BabyTankSwitcher-vX.X.X.exe`

No Python, no dependencies — just run the `.exe`.

> **Windows SmartScreen warning:** On first launch Windows may say "Windows
> protected your PC". Click **More info → Run anyway**. This happens because
> the exe isn't code-signed (expensive certificate). The source code is fully
> open above.

---

## Requirements

| Requirement | Notes |
|---|---|
| Windows 10 / 11 | Required — uses Windows-only APIs |
| Java 17+ on PATH | Required to launch Microbot / RuneLite |

---

## How It Works

The Jagex Launcher writes your session token to `%USERPROFILE%\.runelite\credentials.properties` when you log in. Baby Tank Switcher saves a copy of that file per account. To switch accounts it copies the saved credentials back into `.runelite`, then optionally launches your Microbot jar with `--profile <name>` so each account keeps its own RuneLite settings.

---

## Quick Start

1. Download the `.exe` from the [Releases](../../releases/latest) page and run it
2. Go to **Settings** → set your `.runelite` folder and your `microbot-x.x.x.jar` path
3. For each account, log in via the Jagex Launcher, then go to **Account Overview** and click **Import Account** — the account name is read from the credentials file automatically
4. Go to **Account Handler** → select an account → click **▶ Launch** to swap credentials and start the client
5. Enable the **BabyTank HTTP Server** plugin inside each Microbot client to unlock live monitoring in the Bot Manager

---

## Pages

### Account Overview
Manages your saved accounts and their credentials.

- **Import Account** — reads credentials from the active `.runelite` folder and saves them. Account name is auto-detected from the credentials file
- **Refresh Active Account** — re-imports credentials for the selected account after re-authenticating
- **Switch to Account** — swaps credentials without launching a client
- **Delete** — removes an account
- **Double-click** a row to rename an account
- **Right-click** a row for the full context menu:
  - Set Client Arguments (per-account launch flags)
  - Override HTTP Port (pin a manual port or revert to auto-detection)
  - Rename / Refresh Credentials / Delete

### Account Handler
Launches and kills Microbot clients.

- Shows each account's running status, PID, and active client arguments
- **▶ Launch** / **■ Kill** — start or stop a single selected account
- **▶ Launch All** / **■ Kill All** — batch launch or kill all accounts
- **Delay between launches** spinner — staggers Launch All so each client starts `N` ms after the previous one (default 1000 ms). When the BabyTank HTTP Server plugin is active, Baby Tank Switcher waits for each client to confirm it is fully logged in before launching the next one, rather than relying on the fixed delay alone
- Status updates every 2 seconds

### Bot Manager
Live monitoring dashboard for all running clients. Each account gets a card showing:

| Field | Description |
|---|---|
| Online indicator | Green dot when connected, grey when offline |
| World | Current world number |
| HP | Current / max hitpoints (turns red below 30%) |
| Run | Run energy percentage |
| Uptime | How long the client has been running |
| Script | Latest console log message from the running script, or script status. Shows ⏸ PAUSED when paused |

Controls on each card:
- **⏸ Pause** / **▶ Resume** — pause or resume the running script
- **⤢ Expand Client** — brings the Microbot window to the foreground
- **Plugin list** — shows all active Microbot plugins with Start/Stop buttons for each
- **↺ Reset All** — cycles every active plugin (stop → 1.2 s → start) to reinitialise from default settings

Clients are matched to accounts automatically by player name (ports 7070–7199 are scanned concurrently every 5 seconds). You can also pin a specific port per account via right-click → Override HTTP Port in Account Overview.

### Settings

| Field | Description |
|---|---|
| Runelite Location | Path to your `.runelite` folder — auto-detected |
| Configurations Location | Where Baby Tank Switcher stores its data — auto-detected |
| Microbot Jar Location | Path to your `microbot-x.x.x.jar` |
| JVM Arguments | e.g. `-Xmx512m -Xms256m` |
| Process Protection | Applies Windows process hardening on launch so Jagex cannot inspect running clients. Requires Baby Tank Switcher to be run as Administrator |

### Guide
Built-in step-by-step setup guide.

---

## Client Arguments

Per-account launch flags are configured via right-click → **Set Client Arguments** in Account Overview.

| Flag | Description |
|---|---|
| Clean Jagex Launcher | Remove Jagex launcher integration |
| Developer Mode | Enable developer tools and `-ea` JVM flag |
| Debug Mode | Enable additional debugging |
| Microbot Debug | Enable Microbot-specific debugging |
| Safe Mode | Disable external plugins |
| Insecure Skip TLS | Skip TLS certificate validation |
| Disable Telemetry | Prevent sending usage statistics |
| Disable Walker Update | Prevent automatic walker component updates |
| No Update | Skip RuneLite update checks |
| JavConfig URL | Custom jav_config URL |
| Profile | RuneLite profile name (keeps settings separate per account) |
| Proxy Type | None / HTTP / SOCKS4 / SOCKS5 |
| RAM Limitation | Heap size in MB (512 / 1024 / 2048 / 4096 / 8192) |
| Raw Arguments | Any additional flags passed directly to the jar |

---

## Data Locations

| Item | Path |
|---|---|
| Settings | `%APPDATA%\BabyTankSwitcher\Configurations\settings.json` |
| Accounts list | `%APPDATA%\BabyTankSwitcher\Configurations\accounts.json` |
| Saved credentials | `%APPDATA%\BabyTankSwitcher\Configurations\credentials.properties.<name>` |

---

## Building From Source

### Prerequisites

```
Python 3.11+
pip install -r requirements.txt
pip install pyinstaller
```

### Local build

```bat
build.bat
```

Output: `dist\BabyTankSwitcher.exe`

### GitHub Actions (automatic)

Push a version tag to trigger a release build:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The workflow (`.github/workflows/build.yml`) will:
1. Build the `.exe` on a Windows runner
2. Create a GitHub Release with the exe attached
3. Auto-generate release notes from your commit messages

---

## Project Structure

```
BabyTankSwitcher/
├── app.py                      # UI — all five pages and the Bot Manager cards
├── config.py                   # Settings & account storage (JSON)
├── switcher.py                 # Credential swap, jar launch, process protection
├── requirements.txt            # Python dependencies
├── BabyTankSwitcher.spec       # PyInstaller build spec
├── generate_version_info.py    # Generates version_info.txt for the exe metadata
├── build.bat                   # Local build helper
└── .github/
    └── workflows/
        └── build.yml           # GitHub Actions CI/CD
```
