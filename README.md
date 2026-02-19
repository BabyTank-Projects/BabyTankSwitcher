# Baby Tank Switcher

A Windows tool to switch between RuneLite / Microbot accounts linked to a single
Jagex account by swapping `credentials.properties`, with a built-in
Multi-Client Viewer so you can monitor all your clients at a glance.

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

## Quick Start

1. Download the `.exe` from the [Releases](../../releases/latest) page
2. Run it
3. Go to **Settings** → set your `.runelite` folder and your `microbot-x.x.x.jar` path
4. For each account:
   - Open Jagex Launcher → select the account → launch RuneLite/Microbot
   - Once it's loaded, switch back to Baby Tank Switcher
   - Click **Import Account**
5. From now on, click **Switch** to swap credentials or **▶ Launch** to swap + start the jar

---

## How It Works

1. You log in via the Jagex Launcher → RuneLite writes your session token to
   `%USERPROFILE%\.runelite\credentials.properties`
2. Baby Tank Switcher saves a copy of that file per account
3. To switch: it copies that account's saved credentials back into `.runelite`,
   then optionally launches your jar with `--profile <name>` so each account
   keeps its own RuneLite settings

---

## Client Viewer

The **Client Viewer** tab shows live thumbnails of all your running clients.

- **Thumbnails scale** automatically as you resize the window
- **Click a thumbnail** to bring that client to the front
- **Auto-minimize** sends the client back to the taskbar when you click away
- **+ Add Window** lets you manually add any window (failsafe for slow-loading clients)
- Clients launched through the switcher are **auto-detected** — even if Microbot
  takes a while to fully load

---

## Settings

| Field | Description |
|---|---|
| `.runelite` folder | Usually `C:\Users\You\.runelite` — auto-detected |
| Jar path | Path to your `microbot-x.x.x.jar` |
| JVM args | e.g. `-Xmx512m -Xms256m` |

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
├── app.py                          # Main app + Client Viewer
├── config.py                       # Settings & account storage
├── switcher.py                     # Credential swap + launch logic
├── requirements.txt                # Python dependencies
├── BabyTankSwitcher.spec           # PyInstaller build spec
├── build.bat                       # Local build helper
└── .github/
    └── workflows/
        └── build.yml               # GitHub Actions CI/CD
```
