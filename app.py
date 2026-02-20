"""
Baby Tank Switcher - Windows only
"""
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

import customtkinter as ctk
import win32gui
import win32con
import win32process
import psutil

import config as cfg
import switcher as sw

# ── Favorites storage (per-account plugin favorites, local only) ──────────────

_FAVORITES_FILE = cfg.APP_DATA_DIR / "favorites.json"

def _load_favorites() -> dict:
    """Load {account_id: [className, ...]} from disk. Returns {} on any error."""
    try:
        if _FAVORITES_FILE.exists():
            import json as _json
            return _json.loads(_FAVORITES_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def _save_favorites(data: dict):
    """Persist favorites dict to disk."""
    try:
        import json as _json
        cfg.ensure_dirs()
        _FAVORITES_FILE.write_text(
            _json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass

# ── Theme ─────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BG_DARK   = "#0d1117"
BG_SIDE   = "#161b22"
BG_MID    = "#1c2128"
BG_TABLE  = "#161b22"
BG_ROW    = "#1c2128"
BG_SEL    = "#1f3a5f"
BG_HOVER  = "#262d36"
ACCENT    = "#2f81f7"
BTN_GRAY  = "#30363d"
BTN_GRAY2 = "#3d444d"
TEXT_PRI  = "#e6edf3"
TEXT_SEC  = "#8b949e"
TEXT_HEAD = "#cdd9e5"
GREEN     = "#3fb950"
RED       = "#f85149"
BORDER    = "#30363d"

FONT_NAV   = ("Segoe UI", 12, "bold")
FONT_HEAD  = ("Segoe UI", 13, "bold")
FONT_BODY  = ("Segoe UI", 12)
FONT_SMALL = ("Segoe UI", 10)
FONT_MONO  = ("Consolas", 11)
FONT_TITLE = ("Segoe UI", 18, "bold")

NAV_ITEMS    = ["Account Overview", "Account Handler", "Bot Manager", "Settings", "Guide"]
RAM_OPTIONS  = ["", "512", "1024", "2048", "4096", "8192"]
PROXY_OPTIONS = ["None", "HTTP", "SOCKS4", "SOCKS5"]



# ── Helpers ───────────────────────────────────────────────────────────────────

def show_error(msg):
    messagebox.showerror("Error", msg)

def show_info(msg):
    messagebox.showinfo("Info", msg)

def ask_yn(title, msg):
    return messagebox.askyesno(title, msg)


# ── Spinner widget ─────────────────────────────────────────────────────────────

class Spinner(ctk.CTkFrame):
    """Integer up/down spinner styled to match the dark theme."""
    def __init__(self, parent, min_val=0, max_val=60000, step=100,
                 initial=1000, width=70, **kwargs):
        super().__init__(parent, fg_color=BG_MID, corner_radius=6,
                         border_width=1, border_color=BORDER, **kwargs)
        self._min  = min_val
        self._max  = max_val
        self._step = step
        self._var  = tk.IntVar(value=initial)

        self._entry = ctk.CTkEntry(
            self, textvariable=self._var, width=width,
            font=FONT_BODY, fg_color="transparent",
            border_width=0, justify="center",
        )
        self._entry.grid(row=0, column=0, rowspan=2, padx=(6, 0), pady=2)

        btn_cfg = dict(width=22, height=16, fg_color=BTN_GRAY,
                       hover_color=BTN_GRAY2, text_color=TEXT_PRI,
                       corner_radius=4, border_width=0)
        ctk.CTkButton(self, text="▲", command=self._up,
                      font=("Segoe UI", 9), **btn_cfg).grid(
            row=0, column=1, padx=(2, 4), pady=(3, 1))
        ctk.CTkButton(self, text="▼", command=self._dn,
                      font=("Segoe UI", 9), **btn_cfg).grid(
            row=1, column=1, padx=(2, 4), pady=(1, 3))

    def _up(self):
        self._var.set(min(self._var.get() + self._step, self._max))

    def _dn(self):
        self._var.set(max(self._var.get() - self._step, self._min))

    def get(self) -> int:
        try:
            return int(self._var.get())
        except (tk.TclError, ValueError):
            return 1000


# ── Client Arguments Builder ──────────────────────────────────────────────────

class ClientArgsDialog(ctk.CTkToplevel):
    FLAGS = [
        ("clean_jagex_launcher",  "Clean Jagex Launcher",    "Remove Jagex launcher integration"),
        ("developer_mode",        "Developer Mode",           "Enable developer tools and logging"),
        ("debug_mode",            "Debug Mode",               "Enable additional debugging options"),
        ("microbot_debug",        "Microbot Debug",           "Enable Microbot debugging features"),
        ("safe_mode",             "Safe Mode",                "Disable external plugins"),
        ("insecure_skip_tls",     "Insecure Skip TLS",        "Skip TLS certificate validation (not recommended)"),
        ("disable_telemetry",     "Disable Telemetry",        "Prevent sending usage statistics"),
        ("disable_walker_update", "Disable Walker Update",    "Prevent automatic updates to the walker component"),
        ("no_update",             "No Update",                "Skip checking for RuneLite updates"),
    ]

    def __init__(self, parent, account: cfg.Account):
        super().__init__(parent)
        self.title("Client Arguments Builder")
        self.geometry("420x680")
        self.resizable(False, True)
        self.grab_set()
        self.account = account
        self.result: cfg.ClientArgs | None = None
        self._build()

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(scroll, text="Client Options", font=FONT_HEAD,
                     text_color=TEXT_PRI).pack(anchor="w", padx=16, pady=(16, 8))

        ca = self.account.client_args
        self._flag_vars = {}
        for attr, label, desc in self.FLAGS:
            var = tk.BooleanVar(value=getattr(ca, attr))
            self._flag_vars[attr] = var
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)
            ctk.CTkCheckBox(row, text=label, variable=var, font=FONT_BODY,
                            text_color=TEXT_PRI, checkbox_width=20,
                            checkbox_height=20).pack(anchor="w")
            ctk.CTkLabel(row, text=desc, font=FONT_SMALL,
                         text_color=TEXT_SEC).pack(anchor="w", padx=28)

        ctk.CTkLabel(scroll, text="Options With Values", font=FONT_HEAD,
                     text_color=TEXT_PRI).pack(anchor="w", padx=16, pady=(20, 8))

        def labeled_entry(label, attr, placeholder=""):
            ctk.CTkLabel(scroll, text=label, font=FONT_BODY,
                         text_color=TEXT_PRI).pack(anchor="w", padx=16, pady=(6, 2))
            var = ctk.StringVar(value=getattr(ca, attr))
            ctk.CTkEntry(scroll, textvariable=var, placeholder_text=placeholder,
                         fg_color=BG_MID, border_color=BORDER).pack(
                fill="x", padx=16, pady=(0, 2))
            return var

        def labeled_dropdown(label, attr, options):
            ctk.CTkLabel(scroll, text=label, font=FONT_BODY,
                         text_color=TEXT_PRI).pack(anchor="w", padx=16, pady=(6, 2))
            val = getattr(ca, attr) or options[0]
            var = ctk.StringVar(value=val)
            ctk.CTkOptionMenu(scroll, variable=var, values=options,
                              fg_color=BG_MID, button_color=BTN_GRAY,
                              button_hover_color=BTN_GRAY2).pack(
                anchor="w", padx=16, pady=(0, 2))
            return var

        self._jav_var   = labeled_entry("JavConfig URL",    "jav_config_url", "Enter URL")
        self._prof_var  = labeled_entry("Profile",          "profile",        "Enter profile name")
        self._proxy_var = labeled_dropdown("Proxy Type",    "proxy_type",     PROXY_OPTIONS)
        self._ram_var   = labeled_dropdown("RAM Limitation","ram_limitation",  RAM_OPTIONS)

        ctk.CTkLabel(scroll, text="Raw Arguments", font=FONT_HEAD,
                     text_color=TEXT_PRI).pack(anchor="w", padx=16, pady=(20, 4))
        self._raw_box = ctk.CTkTextbox(scroll, height=70, font=FONT_MONO,
                                       fg_color=BG_MID, border_color=BORDER, border_width=1)
        self._raw_box.pack(fill="x", padx=16, pady=(0, 12))
        self._raw_box.insert("1.0", ca.raw_args)

        bar = ctk.CTkFrame(self, fg_color=BG_MID, height=54, corner_radius=0)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        ctk.CTkButton(bar, text="Cancel", width=100, fg_color=BTN_GRAY,
                      hover_color=BTN_GRAY2, command=self.destroy).pack(
            side="right", padx=(6, 16), pady=10)
        ctk.CTkButton(bar, text="OK", width=100, fg_color=ACCENT,
                      hover_color="#388bfd", command=self._ok).pack(
            side="right", padx=6, pady=10)

    def _ok(self):
        self.result = cfg.ClientArgs(
            clean_jagex_launcher  = self._flag_vars["clean_jagex_launcher"].get(),
            developer_mode        = self._flag_vars["developer_mode"].get(),
            debug_mode            = self._flag_vars["debug_mode"].get(),
            microbot_debug        = self._flag_vars["microbot_debug"].get(),
            safe_mode             = self._flag_vars["safe_mode"].get(),
            insecure_skip_tls     = self._flag_vars["insecure_skip_tls"].get(),
            disable_telemetry     = self._flag_vars["disable_telemetry"].get(),
            disable_walker_update = self._flag_vars["disable_walker_update"].get(),
            no_update             = self._flag_vars["no_update"].get(),
            jav_config_url        = self._jav_var.get().strip(),
            profile               = self._prof_var.get().strip(),
            proxy_type            = self._proxy_var.get(),
            ram_limitation        = self._ram_var.get(),
            raw_args              = self._raw_box.get("1.0", "end").strip(),
        )
        self.destroy()


# ── Rename dialog ─────────────────────────────────────────────────────────────

class RenameDialog(ctk.CTkToplevel):
    def __init__(self, parent, current_name):
        super().__init__(parent)
        self.title("Rename Account")
        self.geometry("380x140")
        self.resizable(False, False)
        self.grab_set()
        self.result = None
        ctk.CTkLabel(self, text="Display name:", font=FONT_BODY).pack(
            anchor="w", padx=20, pady=(18, 4))
        self.var = ctk.StringVar(value=current_name)
        ctk.CTkEntry(self, textvariable=self.var, font=FONT_BODY, width=340).pack(padx=20)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=14)
        ctk.CTkButton(row, text="OK", width=100, command=self._ok).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Cancel", width=100, fg_color=BTN_GRAY,
                      hover_color=BTN_GRAY2, command=self.destroy).pack(side="left", padx=6)
        self.bind("<Return>", lambda e: self._ok())

    def _ok(self):
        v = self.var.get().strip()
        if v:
            self.result = v
            self.destroy()


# ── Settings page ─────────────────────────────────────────────────────────────

class SettingsPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Settings", font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(anchor="center", pady=(30, 24))
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="x", padx=40)

        s = self.app.settings
        self.rl_var       = ctk.StringVar(value=s.runelite_folder)
        self.cfg_var      = ctk.StringVar(value=s.config_location)
        self.jar_var      = ctk.StringVar(value=s.jar_path)
        self.jvm_var      = ctk.StringVar(value=s.jvm_args)
        self.protect_var  = tk.BooleanVar(value=s.protect_process)

        def field(label, var, browse_fn=None):
            ctk.CTkLabel(container, text=label, font=FONT_BODY,
                         text_color=TEXT_PRI).pack(anchor="w", pady=(12, 2))
            row = ctk.CTkFrame(container, fg_color="transparent")
            row.pack(fill="x")
            ctk.CTkEntry(row, textvariable=var, font=FONT_MONO,
                         fg_color=BG_MID, border_color=BORDER).pack(
                side="left", fill="x", expand=True)
            if browse_fn:
                ctk.CTkButton(row, text="Browse", width=80, fg_color=BTN_GRAY,
                              hover_color=BTN_GRAY2, command=browse_fn).pack(
                    side="left", padx=(6, 0))

        field("Runelite Location",       self.rl_var,  self._browse_rl)
        field("Configurations Location", self.cfg_var, self._browse_cfg)
        field("Microbot Jar Location",   self.jar_var, self._browse_jar)
        field("JVM Arguments",           self.jvm_var)

        # ── Process protection ────────────────────────────────────────────────
        protect_row = ctk.CTkFrame(container, fg_color="transparent")
        protect_row.pack(anchor="w", pady=(16, 0))
        ctk.CTkCheckBox(
            protect_row,
            text="Process Protection  (requires admin — hides clients from Jagex fingerprinting)",
            variable=self.protect_var,
            font=FONT_BODY, text_color=TEXT_PRI,
            checkbox_width=20, checkbox_height=20,
        ).pack(side="left")
        ctk.CTkLabel(
            container,
            text="When enabled, Baby Tank Switcher must be run as Administrator. "
                 "Applies Windows process hardening so Jagex cannot inspect launched clients.",
            font=FONT_SMALL, text_color=TEXT_SEC, wraplength=560, justify="left",
        ).pack(anchor="w", padx=28, pady=(2, 0))

        ctk.CTkButton(container, text="Save Settings", width=160,
                      fg_color=ACCENT, hover_color="#388bfd",
                      command=self._save).pack(pady=24)

    def _browse_rl(self):
        d = filedialog.askdirectory(title="Select .runelite folder",
                                    initialdir=self.rl_var.get())
        if d: self.rl_var.set(d)

    def _browse_cfg(self):
        d = filedialog.askdirectory(title="Select Configurations folder",
                                    initialdir=self.cfg_var.get())
        if d: self.cfg_var.set(d)

    def _browse_jar(self):
        p = self.jar_var.get()
        init = str(Path(p).parent) if p else str(Path.home())
        f = filedialog.askopenfilename(title="Select Microbot jar",
                                       filetypes=[("JAR files", "*.jar"), ("All", "*.*")],
                                       initialdir=init)
        if f: self.jar_var.set(f)

    def _save(self):
        s = self.app.settings
        s.runelite_folder  = self.rl_var.get().strip()
        s.config_location  = self.cfg_var.get().strip()
        s.jar_path         = self.jar_var.get().strip()
        s.jvm_args         = self.jvm_var.get().strip()
        s.protect_process  = self.protect_var.get()
        cfg.save_settings(s)
        if s.protect_process and not sw.is_admin():
            show_info("Settings saved.\n\nWarning: Process Protection is enabled but Baby Tank Switcher "
                      "is not running as Administrator. Protection will be skipped until you relaunch as admin.")
        else:
            show_info("Settings saved.")


# ── Guide page ────────────────────────────────────────────────────────────────

class GuidePage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self._build()

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=30, pady=20)

        def section(title, body):
            ctk.CTkLabel(scroll, text=title, font=FONT_HEAD,
                         text_color=ACCENT).pack(anchor="w", pady=(16, 4))
            ctk.CTkLabel(scroll, text=body, font=FONT_BODY, text_color=TEXT_PRI,
                         wraplength=600, justify="left").pack(anchor="w", padx=8)

        ctk.CTkLabel(scroll, text="How to use", font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(anchor="w", pady=(0, 8))

        section("Step 1 - Configure Settings",
                "Go to Settings and browse to your Microbot jar file. "
                "Runelite Location and Configurations Location are auto-detected.")

        section("Step 2 - Import accounts",
                "Log in to each account via the Jagex Launcher or Microbot Launcher so RuneLite "
                "writes credentials.\n\n"
                "Then go to Account Overview and click 'Import Account'. "
                "The account name is read automatically from the credentials file. "
                "Repeat for every account.")

        section("Optional Step 3 - Switch accounts (only if session token has expired)",
                "Select an account and click 'Switch to Account' to copy its credentials "
                "into the active .runelite folder. Then launch your client manually.\n\n"
                "'Refresh Active Account' re-imports credentials for the selected account "
                "from the current .runelite folder (use after re-authenticating).")

        section("Step 4 - Account Handler",
                "Use Account Handler to launch and kill Microbot clients per account. "
                "Running clients show a green dot and their PID.\n\n"
                "Use 'Launch All' to start every account at once. Set 'Update Delay (ms)' "
                "to stagger launches so each client starts with a delay (default 1000 ms), "
                "preventing system lag.")

        section("Step 5 - Enable the BabyTank HTTP Server plugin",
                "Inside each Microbot client, enable the BabyTank HTTP Server plugin. "
                "This plugin lets Baby Tank Switcher communicate with your running clients.\n\n"
                "Important: leave the plugin's port setting at its default (0). "
                "It will automatically pick a free port in the 7070–7199 range.\n\n"
                "To confirm auto-detection is working, go to Account Overview, right-click the "
                "account's username, choose 'Override HTTP Port', then click 'Clear (use auto)'. "
                "Baby Tank Switcher will match each client by player name automatically.")

        section("Step 6 - Bot Manager",
                "The Bot Manager tab shows live status for all running clients. "
                "Each card shows HP, run energy, world, uptime, and the latest console log "
                "message from the script.\n\n"
                "Use Pause/Resume to control scripts. "
                "Click 'Expand Client' to bring a client window to the foreground — "
                "it stays there until you manually minimize it. "
                "Start/Stop individual plugins directly from the card.")


# ── Account Overview page ──────────────────────────────────────────────────────

class AccountOverviewPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._selected_id = None
        self._build()
        self.refresh()

    def _build(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(self, fg_color=BG_MID, corner_radius=0, height=36)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(0, weight=3)
        hdr.grid_columnconfigure(1, weight=1)
        hdr.grid_columnconfigure(2, weight=2)
        for col, txt in enumerate(["Account Name", "Active", "Has Client Arguments"]):
            ctk.CTkLabel(hdr, text=txt, font=("Segoe UI", 11, "bold"),
                         text_color=TEXT_HEAD, anchor="w").grid(
                row=0, column=col, sticky="w",
                padx=(20 if col == 0 else 8, 0))

        self.list_frame = ctk.CTkScrollableFrame(self, fg_color=BG_TABLE,
                                                  scrollbar_button_color=BTN_GRAY)
        self.list_frame.grid(row=1, column=0, sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)

        bar = ctk.CTkFrame(self, fg_color=BG_MID, corner_radius=0, height=52)
        bar.grid(row=2, column=0, sticky="ew")
        bar.grid_propagate(False)

        ctk.CTkButton(bar, text="Import Account", width=130, height=34,
                      font=FONT_SMALL, fg_color=BTN_GRAY, hover_color=BTN_GRAY2,
                      command=self._import_account).pack(side="left", padx=(12, 4), pady=9)
        ctk.CTkButton(bar, text="Refresh Active Account", width=165, height=34,
                      font=FONT_SMALL, fg_color=BTN_GRAY, hover_color=BTN_GRAY2,
                      command=self._refresh_active).pack(side="left", padx=4, pady=9)
        ctk.CTkButton(bar, text="Delete", width=80, height=34,
                      font=FONT_SMALL, fg_color="#6e2020", hover_color="#8b2a2a",
                      command=self._delete).pack(side="left", padx=4, pady=9)
        ctk.CTkButton(bar, text="Switch to Account", width=140, height=34,
                      font=FONT_SMALL, fg_color=ACCENT, hover_color="#388bfd",
                      command=self._switch).pack(side="left", padx=4, pady=9)

    def refresh(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        if not self.app.accounts:
            ctk.CTkLabel(self.list_frame,
                         text="No accounts yet. Click 'Import Account' to get started.",
                         font=FONT_BODY, text_color=TEXT_SEC).grid(row=0, column=0, pady=40)
            return
        for i, acc in enumerate(self.app.accounts):
            self._make_row(i, acc)

    def _make_row(self, idx, acc):
        bg = BG_SEL if acc.id == self._selected_id else (BG_ROW if idx % 2 == 0 else BG_TABLE)
        row = ctk.CTkFrame(self.list_frame, fg_color=bg, corner_radius=0, height=36)
        row.grid(row=idx, column=0, sticky="ew")
        row.grid_propagate(False)
        row.grid_columnconfigure(0, weight=3)
        row.grid_columnconfigure(1, weight=1)
        row.grid_columnconfigure(2, weight=2)

        has_creds = sw.has_credentials(acc)
        has_args  = acc.client_args.has_any()

        ctk.CTkLabel(row, text=acc.display_name, font=FONT_BODY,
                     text_color=TEXT_PRI, anchor="w").grid(row=0, column=0, sticky="w", padx=20)
        ctk.CTkLabel(row, text="✓" if has_creds else "✗", font=FONT_BODY,
                     text_color=GREEN if has_creds else RED).grid(row=0, column=1, sticky="w", padx=8)
        ctk.CTkLabel(row, text="✓" if has_args else "✗", font=FONT_BODY,
                     text_color=GREEN if has_args else RED).grid(row=0, column=2, sticky="w", padx=8)

        for widget in (row,) + tuple(row.winfo_children()):
            widget.bind("<Button-1>",        lambda e, a=acc: self._select(a))
            widget.bind("<Double-Button-1>", lambda e, a=acc: self._rename(a))
            widget.bind("<Button-3>",        lambda e, a=acc: self._context_menu(e, a))

    def _context_menu(self, event, acc):
        self._select(acc)
        menu = tk.Menu(self, tearoff=0, bg=BG_MID, fg=TEXT_PRI,
                       activebackground=BG_HOVER, activeforeground=TEXT_PRI,
                       relief="flat", bd=1)
        menu.add_command(label="Switch to Account",    command=self._switch)
        menu.add_command(label="Set Client Arguments", command=lambda: self._set_client_args(acc))
        port_label = f"Override HTTP Port  (pinned: {acc.http_port})" if acc.http_port else "Override HTTP Port  (auto)"
        menu.add_command(label=port_label,             command=lambda: self._set_http_port(acc))
        menu.add_separator()
        menu.add_command(label="Rename",               command=lambda: self._rename(acc))
        menu.add_command(label="Refresh Credentials",  command=self._refresh_active)
        menu.add_separator()
        menu.add_command(label="Delete",               command=self._delete)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _select(self, acc):
        self._selected_id = acc.id
        self.refresh()

    def _get_selected(self):
        if not self._selected_id:
            show_error("No account selected.")
            return None
        return next((a for a in self.app.accounts if a.id == self._selected_id), None)

    def _import_account(self):
        settings  = self.app.settings
        creds_path = sw.get_active_credentials_path(settings)
        if not creds_path.exists():
            show_error(f"credentials.properties not found at:\n{creds_path}\n\n"
                       "Launch RuneLite or Microbot via the Jagex Launcher first.")
            return

        auto_name = cfg.read_account_name_from_credentials(creds_path)
        if auto_name:
            if any(a.display_name.lower() == auto_name.lower() for a in self.app.accounts):
                if not ask_yn("Duplicate account",
                              f"An account named '{auto_name}' already exists.\n"
                              "Import again and overwrite its credentials?"):
                    return
            name = auto_name
        else:
            dlg = ImportDialog(self, "")
            self.wait_window(dlg)
            if not dlg.result:
                return
            name = dlg.result

        existing = next((a for a in self.app.accounts
                         if a.display_name.lower() == name.lower()), None)
        if existing:
            try:
                sw.import_current_credentials(existing, settings)
                show_info(f"Credentials updated for '{name}'.")
            except sw.SwitcherError as e:
                show_error(str(e))
            self.refresh()
            return

        account = cfg.Account(display_name=name,
                        credentials_file=sw.new_credentials_filename(name))
        try:
            sw.import_current_credentials(account, settings)
        except sw.SwitcherError as e:
            show_error(str(e))
            return

        self.app.accounts.append(account)
        self.app.save()
        self.refresh()
        self.app.handler_page.refresh()
        show_info(f"Imported account: {name}")

    def _refresh_active(self):
        acc = self._get_selected()
        if not acc:
            return
        if not ask_yn("Refresh credentials",
                      f"Re-import current credentials.properties into '{acc.display_name}'?"):
            return
        try:
            sw.import_current_credentials(acc, self.app.settings)
            show_info(f"Credentials updated for '{acc.display_name}'.")
            self.refresh()
        except sw.SwitcherError as e:
            show_error(str(e))

    def _delete(self):
        acc = self._get_selected()
        if not acc:
            return
        if not ask_yn("Delete account", f"Delete '{acc.display_name}'?"):
            return
        self.app.accounts = [a for a in self.app.accounts if a.id != acc.id]
        self._selected_id = None
        self.app.save()
        self.refresh()
        self.app.handler_page.refresh()

    def _switch(self):
        acc = self._get_selected()
        if not acc:
            return
        def _do():
            try:
                sw.switch_to(acc, self.app.settings)
                self.app.after(0, lambda: show_info(
                    f"Switched to '{acc.display_name}'.\nYou can now launch your client."))
            except sw.SwitcherError as e:
                self.app.after(0, lambda: show_error(str(e)))
        threading.Thread(target=_do, daemon=True).start()

    def _set_client_args(self, acc):
        dlg = ClientArgsDialog(self, acc)
        self.wait_window(dlg)
        if dlg.result is not None:
            acc.client_args = dlg.result
            self.app.save()
            self.refresh()
            self.app.handler_page.refresh()

    def _set_http_port(self, acc):
        dlg = HttpPortDialog(self, acc)
        self.wait_window(dlg)
        if dlg.result is not None:
            acc.http_port = dlg.result
            self.app.save()
            self.refresh()
            self.app.handler_page.refresh()
            self.app.bot_status_page._refresh_cards()

    def _rename(self, acc):
        dlg = RenameDialog(self, acc.display_name)
        self.wait_window(dlg)
        if dlg.result:
            acc.display_name = dlg.result
            self.app.save()
            self.refresh()
            self.app.handler_page.refresh()


# ── Import dialog ──────────────────────────────────────────────────────────────

class ImportDialog(ctk.CTkToplevel):
    def __init__(self, parent, auto_name: str):
        super().__init__(parent)
        self.title("Import Account")
        self.geometry("400x200")
        self.resizable(False, False)
        self.grab_set()
        self.result = None
        self._build(auto_name)

    def _build(self, auto_name):
        ctk.CTkLabel(self, text="Import Account", font=FONT_HEAD).pack(
            anchor="w", padx=20, pady=(18, 4))
        hint = ("Name detected from credentials file:"
                if auto_name else "Enter a display name for this account:")
        ctk.CTkLabel(self, text=hint, font=FONT_SMALL,
                     text_color=TEXT_SEC).pack(anchor="w", padx=20)
        self.name_var = ctk.StringVar(value=auto_name)
        ctk.CTkEntry(self, textvariable=self.name_var,
                     placeholder_text="Account display name",
                     width=360, font=FONT_BODY).pack(padx=20, pady=(4, 16))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack()
        ctk.CTkButton(row, text="Import", width=120, fg_color=ACCENT,
                      hover_color="#388bfd", command=self._ok).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Cancel", width=120, fg_color=BTN_GRAY,
                      hover_color=BTN_GRAY2, command=self.destroy).pack(side="left", padx=6)
        self.bind("<Return>", lambda e: self._ok())

    def _ok(self):
        name = self.name_var.get().strip()
        if not name:
            show_error("Display name cannot be empty.")
            return
        self.result = name
        self.destroy()


# ── Account Handler page ──────────────────────────────────────────────────────

class AccountHandlerPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._selected_id = None
        self._launching   = False   # True while any launch is in progress
        self._build()
        self.refresh()
        self._tick()

    def _build(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(self, fg_color=BG_MID, corner_radius=0, height=36)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(0, weight=3)
        hdr.grid_columnconfigure(1, weight=1)
        hdr.grid_columnconfigure(2, weight=1)
        hdr.grid_columnconfigure(3, weight=2)
        for col, txt in enumerate(["Account Name", "Status", "PID", "Client Args"]):
            ctk.CTkLabel(hdr, text=txt, font=("Segoe UI", 11, "bold"),
                         text_color=TEXT_HEAD, anchor="w").grid(
                row=0, column=col, sticky="w",
                padx=(20 if col == 0 else 8, 0))

        self.list_frame = ctk.CTkScrollableFrame(self, fg_color=BG_TABLE,
                                                  scrollbar_button_color=BTN_GRAY)
        self.list_frame.grid(row=1, column=0, sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)

        # ── Toolbar ───────────────────────────────────────────────────────────
        bar = ctk.CTkFrame(self, fg_color=BG_MID, corner_radius=0, height=52)
        bar.grid(row=2, column=0, sticky="ew")
        bar.grid_propagate(False)

        self._btn_launch = ctk.CTkButton(bar, text="▶ Launch", width=100, height=34,
                      font=FONT_SMALL, fg_color="#238636", hover_color="#2ea043",
                      command=self._launch)
        self._btn_launch.pack(side="left", padx=(12, 4), pady=9)

        self._btn_launch_all = ctk.CTkButton(bar, text="▶ Launch All", width=115, height=34,
                      font=FONT_SMALL, fg_color="#1a5e2a", hover_color="#238636",
                      command=self._launch_all)
        self._btn_launch_all.pack(side="left", padx=4, pady=9)
        ctk.CTkButton(bar, text="■ Kill", width=80, height=34,
                      font=FONT_SMALL, fg_color="#6e2020", hover_color="#8b2a2a",
                      command=self._kill).pack(side="left", padx=4, pady=9)
        ctk.CTkButton(bar, text="■ Kill All", width=90, height=34,
                      font=FONT_SMALL, fg_color="#4a1010", hover_color="#6e2020",
                      command=self._kill_all).pack(side="left", padx=4, pady=9)

        # ── Launch delay spinner ──────────────────────────────────────────────
        delay_wrap = ctk.CTkFrame(bar, fg_color="transparent")
        delay_wrap.pack(side="left", padx=(18, 4), pady=9)
        ctk.CTkLabel(delay_wrap, text="Delay between launches (ms):", font=FONT_SMALL,
                     text_color=TEXT_SEC).pack(side="left", padx=(0, 6))
        self._delay_spinner = Spinner(delay_wrap, min_val=0, max_val=30000,
                                      step=100, initial=1000, width=70)
        self._delay_spinner.pack(side="left")

    def refresh(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        if not self.app.accounts:
            ctk.CTkLabel(self.list_frame,
                         text="No accounts yet. Add them in Account Overview.",
                         font=FONT_BODY, text_color=TEXT_SEC).grid(row=0, column=0, pady=40)
            return
        for i, acc in enumerate(self.app.accounts):
            self._make_row(i, acc)

    def _make_row(self, idx, acc):
        running = sw.is_running(acc)
        pid     = sw.get_pid(acc)
        bg = BG_SEL if acc.id == self._selected_id else (BG_ROW if idx % 2 == 0 else BG_TABLE)

        row = ctk.CTkFrame(self.list_frame, fg_color=bg, corner_radius=0, height=36)
        row.grid(row=idx, column=0, sticky="ew")
        row.grid_propagate(False)
        row.grid_columnconfigure(0, weight=3)
        row.grid_columnconfigure(1, weight=1)
        row.grid_columnconfigure(2, weight=1)
        row.grid_columnconfigure(3, weight=2)

        ctk.CTkLabel(row, text=acc.display_name, font=FONT_BODY,
                     text_color=TEXT_PRI, anchor="w").grid(row=0, column=0, sticky="w", padx=20)
        ctk.CTkLabel(row, text="● Running" if running else "○ Idle", font=FONT_SMALL,
                     text_color=GREEN if running else TEXT_SEC).grid(
            row=0, column=1, sticky="w", padx=8)
        ctk.CTkLabel(row, text=str(pid) if pid else "—", font=FONT_MONO,
                     text_color=TEXT_SEC).grid(row=0, column=2, sticky="w", padx=8)
        args_preview = " ".join(acc.client_args.build_args())[:40] or "—"
        ctk.CTkLabel(row, text=args_preview, font=FONT_SMALL,
                     text_color=TEXT_SEC, anchor="w").grid(row=0, column=3, sticky="w", padx=8)

        for widget in (row,) + tuple(row.winfo_children()):
            widget.bind("<Button-1>", lambda e, a=acc: self._select(a))

    def _select(self, acc):
        self._selected_id = acc.id
        self.refresh()

    def _get_selected(self):
        if not self._selected_id:
            show_error("No account selected.")
            return None
        return next((a for a in self.app.accounts if a.id == self._selected_id), None)

    def _set_launch_locked(self, locked: bool, status_name: str = ""):
        """Grey out / restore the Launch and Launch All buttons."""
        self._launching = locked
        if locked:
            label = f"⏳ {status_name}…" if status_name else "⏳ Launching…"
            self._btn_launch.configure(
                state="disabled", fg_color=BTN_GRAY, hover_color=BTN_GRAY,
                text=label)
            self._btn_launch_all.configure(
                state="disabled", fg_color=BTN_GRAY, hover_color=BTN_GRAY,
                text="⏳ Waiting…")
        else:
            self._btn_launch.configure(
                state="normal", fg_color="#238636", hover_color="#2ea043",
                text="▶ Launch")
            self._btn_launch_all.configure(
                state="normal", fg_color="#1a5e2a", hover_color="#238636",
                text="▶ Launch All")

    def _wait_for_login(self, acc, deadline: float) -> bool:
        """
        Poll every 2 s until loginState == LOGGED_IN or deadline passes.
        Uses a 0.1 s socket timeout so non-responding ports fail instantly —
        scanning all 130 ports takes under 1 s even with 7 clients running.
        Returns True if confirmed logged in, False if timed out/plugin absent.
        """
        import urllib.request as _ur, json as _j
        name_lower = acc.display_name.strip().lower()

        def _find_state() -> str | None:
            """Scan for this account's port and return its loginState, or None."""
            ports = [acc.http_port] if acc.http_port else range(7070, 7200)
            for port in ports:
                try:
                    with _ur.urlopen(
                        f"http://127.0.0.1:{port}/status", timeout=0.1
                    ) as r:
                        data = _j.loads(r.read())
                    if data.get("playerName", "").strip().lower() == name_lower:
                        return data.get("loginState", "")
                except Exception:
                    pass
            return None  # plugin not responding yet

        while time.time() < deadline:
            state = _find_state()
            if state == "LOGGED_IN":
                return True
            time.sleep(2)

        return False

    def _do_launch(self, acc, sequential=False, unlock_when_done=False):
        """
        Launch one account. Runs in a background thread.

        sequential=True: used by Launch All. Waits until the client confirms
        LOGGED_IN via HTTP before returning so the next credentials swap never
        clobbers this account mid-login. Falls back to 30 s if the plugin
        never responds (BabyTank HTTP Server not installed).

        unlock_when_done=True: re-enables Launch / Launch All buttons after
        this account confirms login (used by single Launch).
        """
        try:
            # Update button label to show which account is logging in
            self.app.after(0, lambda n=acc.display_name: self._set_launch_locked(True, n))
            sw.launch(acc, self.app.settings,
                      protect_process=self.app.settings.protect_process)
            self.app.after(0, self.refresh)

            if sequential or unlock_when_done:
                # Wait up to 3 minutes for LOGGED_IN confirmation.
                logged_in = self._wait_for_login(acc, time.time() + 180)
                if not logged_in:
                    # Plugin never responded — flat 30 s fallback so the
                    # client has time to reach the login screen before we
                    # swap the next account's credentials.
                    time.sleep(30)
            else:
                time.sleep(3)

        except sw.SwitcherError as e:
            self.app.after(0, lambda err=e: show_error(str(err)))
        except FileNotFoundError:
            self.app.after(0, lambda: show_error(
                "Java not found. Make sure Java 17 is installed and on your PATH."))
        finally:
            if unlock_when_done:
                self.app.after(0, lambda: self._set_launch_locked(False))

    def _launch(self):
        if self._launching:
            return
        acc = self._get_selected()
        if not acc:
            return
        # Lock immediately on the main thread before the background thread starts
        self._set_launch_locked(True, acc.display_name)
        threading.Thread(
            target=self._do_launch,
            args=(acc,),
            kwargs={"unlock_when_done": True},
            daemon=True).start()

    def _launch_all(self):
        if self._launching:
            return
        accounts = [a for a in self.app.accounts if not sw.is_running(a)]
        if not accounts:
            show_info("All accounts are already running.")
            return
        delay_ms = self._delay_spinner.get()
        # Lock immediately before the thread starts
        self._set_launch_locked(True, accounts[0].display_name)

        def _do():
            try:
                for i, acc in enumerate(accounts):
                    # Update label for current account being launched
                    self.app.after(0, lambda n=acc.display_name:
                                   self._set_launch_locked(True, n))
                    if i > 0 and delay_ms > 0:
                        time.sleep(delay_ms / 1000.0)
                    # sequential=True waits for LOGGED_IN before continuing.
                    # unlock_when_done=False — we unlock once after the full loop.
                    self._do_launch(acc, sequential=True, unlock_when_done=False)
            finally:
                self.app.after(0, lambda: self._set_launch_locked(False))

        threading.Thread(target=_do, daemon=True).start()

    def _kill(self):
        acc = self._get_selected()
        if not acc:
            return
        if not sw.is_running(acc):
            show_error(f"'{acc.display_name}' is not running.")
            return
        try:
            sw.kill(acc)
            self.refresh()
        except sw.SwitcherError as e:
            show_error(str(e))

    def _kill_all(self):
        running = [a for a in self.app.accounts if sw.is_running(a)]
        if not running:
            show_info("No clients are running.")
            return
        if not ask_yn("Kill all", f"Kill all {len(running)} running clients?"):
            return
        for acc in running:
            try:
                sw.kill(acc)
            except Exception:
                pass
        self.refresh()

    def _tick(self):
        # Only refresh if the page is currently visible — skip when hidden to
        # avoid rebuilding all row widgets every 2 s for nothing.
        try:
            if self.winfo_ismapped():
                self.refresh()
        except Exception:
            pass
        self.after(2000, self._tick)




# ── Bot Manager page ─────────────────────────────────────────────────────────

import urllib.request
import urllib.error
import json as _json

def _is_microbot_plugin(class_name: str) -> bool:
    cn = class_name.lower()
    return ".microbot." in cn or ".babytank" in cn

_SCAN_PORTS = list(range(7070, 7200))  # 130 ports — supports up to 130 concurrent bots


def _http_get(port: int, path: str):
    try:
        url = f"http://127.0.0.1:{port}{path}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=1) as r:
            return _json.loads(r.read().decode())
    except Exception:
        return None


def _http_post(port: int, path: str, body=None):
    try:
        url  = f"http://127.0.0.1:{port}{path}"
        data = _json.dumps(body or {}).encode()
        req  = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        return False


def _central_scan() -> dict:
    """
    Scan all auto-assign ports CONCURRENTLY.  Returns:
        { port: {"status": dict, "plugins": list, "logs": list} }
    Only ports that respond to /status are included.
    Concurrent scanning keeps the full 130-port range fast (all probes
    run in parallel, total time ≈ the slowest single response).
    """
    results: dict = {}
    lock = threading.Lock()

    def _probe(port: int):
        status = _http_get(port, "/status")
        if status is None:
            return
        plugins = _http_get(port, "/plugins") or []
        logs    = _http_get(port, "/logs")    or []
        with lock:
            results[port] = {"status": status, "plugins": plugins, "logs": logs}

    threads = [threading.Thread(target=_probe, args=(p,), daemon=True)
               for p in _SCAN_PORTS]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=3.0)

    return results


class _ClientCard(ctk.CTkFrame):
    """
    One card per account.

    Port resolution (checked in order):
      1. account.http_port > 0  — manual override, self-polls independently.
      2. BotStatusPage pushes data via push_scan_result() after matching
         playerName to account.display_name from a central scan.

    Plugin toggle: Stop → 1 s pause → Start so the plugin reinitialises from
    default settings on every cycle (Microbot HTTP Server has no reset endpoint).
    """
    POLL_MS = 5000  # only used for manual-port self-poll

    def __init__(self, parent, app, account: cfg.Account):
        super().__init__(parent, fg_color=BG_MID, corner_radius=8,
                         border_width=1, border_color=BORDER)
        self.app          = app
        self.account      = account
        self._alive       = True
        self._plugin_rows: dict = {}  # className -> (frame, btn, star_btn)
        self._auto_port: int | None = None  # last port matched by central scan
        self._last_plugins: list = []  # last known plugin list for cross-referencing
        self._last_log: str = ""       # last console log message from /logs endpoint
        # Favorites: set of plugin classNames starred by the local user for this account
        all_favs = _load_favorites()
        self._favorites: set = set(all_favs.get(account.id, []))
        self._build()
        if account.http_port:
            self._self_poll()

    # ── Public API called by BotStatusPage ────────────────────────────────────

    def update_account(self, account: cfg.Account):
        old_port = self.account.http_port
        self.account = account
        self._update_port_label()
        if account.http_port and not old_port:
            self._self_poll()

    def push_scan_result(self, port: int, status: dict, plugins: list, logs: list = None):
        """BotStatusPage calls this after matching this account in a central scan."""
        if not self._alive:
            return
        self._auto_port = port
        self.after(0, self._update_port_label)
        self.after(0, lambda: self._apply_log(logs or []))
        self.after(0, lambda: self._apply_status(status))
        self.after(0, lambda: self._apply_plugins(plugins))

    def push_offline(self):
        """BotStatusPage calls this when no scan match found (auto-port mode only)."""
        if not self._alive or self.account.http_port:
            return
        self._auto_port = None
        self.after(0, self._update_port_label)
        self.after(0, lambda: self._apply_log([]))
        self.after(0, lambda: self._apply_status(None))
        self.after(0, lambda: self._apply_plugins(None))

    def destroy_card(self):
        self._alive = False
        self.destroy()

    # ── Effective port ────────────────────────────────────────────────────────

    def _port(self) -> int | None:
        return self.account.http_port or self._auto_port

    def _update_port_label(self):
        p = self._port()
        if p:
            suffix = "" if self.account.http_port else " (auto)"
            self._port_lbl.configure(text=f":{p}{suffix}")
        else:
            # http_port==0 means auto mode → show Scanning...
            # http_port>0 but no response yet → shouldn't happen, but show port anyway
            self._port_lbl.configure(
                text="Scanning..." if not self.account.http_port else "No port set")

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(self, fg_color=BG_DARK, corner_radius=0, height=40)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(1, weight=1)

        self._dot = tk.Canvas(hdr, width=10, height=10,
                              bg=BG_DARK, highlightthickness=0)
        self._dot.create_oval(2, 2, 8, 8, fill=TEXT_SEC, outline="", tags="dot")
        self._dot.grid(row=0, column=0, padx=(12, 6), pady=15)

        self._conn_lbl = ctk.CTkLabel(hdr, text=self.account.display_name,
                                       font=FONT_HEAD, text_color=TEXT_PRI,
                                       anchor="w")
        self._conn_lbl.grid(row=0, column=1, sticky="w")

        self._port_lbl = ctk.CTkLabel(hdr, text="", font=FONT_SMALL,
                                       text_color=TEXT_SEC)
        self._port_lbl.grid(row=0, column=2, padx=(0, 12))
        self._update_port_label()

        stat = ctk.CTkFrame(self, fg_color=BG_TABLE, corner_radius=0)
        stat.grid(row=1, column=0, sticky="ew")
        stat.grid_columnconfigure((0, 1, 2, 3), weight=1)

        def _cell(col, label):
            ctk.CTkLabel(stat, text=label, font=FONT_SMALL,
                         text_color=TEXT_SEC).grid(
                row=0, column=col, padx=10, pady=(6, 1), sticky="w")
            v = ctk.CTkLabel(stat, text="—", font=FONT_BODY, text_color=TEXT_PRI)
            v.grid(row=1, column=col, padx=10, pady=(0, 6), sticky="w")
            return v

        self._world_v  = _cell(0, "WORLD")
        self._hp_v     = _cell(1, "HP")
        self._profit_v = _cell(2, "PROFIT")
        self._uptime_v = _cell(3, "UPTIME")

        ctrl = ctk.CTkFrame(self, fg_color=BG_MID, corner_radius=0)
        ctrl.grid(row=2, column=0, sticky="ew")
        ctrl.grid_columnconfigure(0, weight=1)

        self._script_lbl = ctk.CTkLabel(ctrl, text="Script: —",
                                         font=FONT_SMALL, text_color=TEXT_SEC,
                                         anchor="w")
        self._script_lbl.grid(row=0, column=0, padx=12, pady=6, sticky="w")

        pbtn = ctk.CTkFrame(ctrl, fg_color="transparent")
        pbtn.grid(row=0, column=1, padx=8, pady=4)
        ctk.CTkButton(pbtn, text="⏸ Pause", width=76, height=26,
                      font=FONT_SMALL, fg_color=BTN_GRAY, hover_color=BTN_GRAY2,
                      command=lambda: self._do_post("/pause")).pack(
            side="left", padx=(0, 4))
        ctk.CTkButton(pbtn, text="▶ Resume", width=76, height=26,
                      font=FONT_SMALL, fg_color="#1a5e2a", hover_color="#238636",
                      command=lambda: self._do_post("/resume")).pack(side="left", padx=(0, 4))
        ctk.CTkButton(pbtn, text="⤢ Expand Client", width=110, height=26,
                      font=FONT_SMALL, fg_color="#1a3a5e", hover_color="#1f4f80",
                      command=self._expand_client).pack(side="left")

        ph = ctk.CTkFrame(self, fg_color=BG_DARK, corner_radius=0, height=28)
        ph.grid(row=3, column=0, sticky="ew")
        ph.grid_propagate(False)
        ctk.CTkLabel(ph, text="Plugins", font=("Segoe UI", 11, "bold"),
                     text_color=TEXT_HEAD, anchor="w").pack(
            side="left", padx=12, pady=4)
        ctk.CTkButton(ph, text="↺ Reset All", width=80, height=20,
                      font=FONT_SMALL, fg_color=BTN_GRAY, hover_color=BTN_GRAY2,
                      command=self._reset_all).pack(side="right", padx=(4, 8), pady=4)
        ctk.CTkButton(ph, text="⟳ Reset Profit", width=94, height=20,
                      font=FONT_SMALL, fg_color=BTN_GRAY, hover_color="#6e2020",
                      command=self._reset_profit).pack(side="right", padx=(0, 4), pady=4)

        self._plug_frame = ctk.CTkScrollableFrame(
            self, fg_color=BG_TABLE, corner_radius=0,
            height=200, scrollbar_button_color=BTN_GRAY)
        self._plug_frame.grid(row=4, column=0, sticky="nsew")
        self._plug_frame.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)
        # Disable CTkScrollableFrame's own global mousewheel handler so it
        # doesn't scroll the plugin list when the wheel is used anywhere in
        # the app. Plugin list is click-drag scroll only.
        self._plug_frame._mouse_wheel_all = lambda event: None
        self._plug_frame._parent_canvas.bind("<MouseWheel>", lambda e: "break")

        self._empty_plug = ctk.CTkLabel(
            self._plug_frame,
            text="No Microbot plugins found.\nEnable BabyTank HTTP Server in this client.",
            font=FONT_SMALL, text_color=TEXT_SEC, justify="center")
        self._empty_plug.grid(row=0, column=0, pady=24)

    # ── Self-poll (manual port mode only) ─────────────────────────────────────

    def _self_poll(self):
        if not self._alive or not self.account.http_port:
            return
        p = self.account.http_port

        def _bg():
            status  = _http_get(p, "/status")
            plugins = _http_get(p, "/plugins") or []
            logs    = _http_get(p, "/logs")    or []
            # Guard against widget being destroyed while the request was in flight
            if not self._alive:
                return
            try:
                self.after(0, lambda: self._apply_log(logs))
                self.after(0, lambda: self._apply_status(status))
                self.after(0, lambda: self._apply_plugins(plugins))
                # Reschedule only after the previous request completes so polls
                # can never stack up if the HTTP call takes longer than POLL_MS.
                self.after(self.POLL_MS, self._self_poll)
            except Exception:
                pass  # widget destroyed between the alive check and after()

        threading.Thread(target=_bg, daemon=True).start()

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _do_post(self, path: str, body=None):
        p = self._port()
        if not p:
            return
        threading.Thread(
            target=_http_post, args=(p, path, body), daemon=True).start()

    # ── Apply log / status / plugins ──────────────────────────────────────────

    def _apply_log(self, log_lines):
        """
        Parse the /logs response and store the last meaningful message.
        ConsoleLogAppender format: "HH:mm:ss LEVEL logger - message"
        We extract just the message portion after " - ".
        """
        if not log_lines:
            self._last_log = ""
            return
        # log_lines may be a list of strings or a single string
        if isinstance(log_lines, str):
            log_lines = [log_lines]
        # Walk from the end to find the last non-empty line
        for line in reversed(log_lines):
            line = line.strip()
            if not line:
                continue
            # Strip the timestamp / level / logger prefix if present
            if " - " in line:
                msg = line.split(" - ", 1)[1].strip()
            else:
                msg = line
            # Truncate long messages for display
            self._last_log = msg[:80] + ("…" if len(msg) > 80 else "")
            return
        self._last_log = ""

    @staticmethod
    def _fmt_profit(gp: int) -> tuple:
        """Return (text, color) for a profit value in GP."""
        if gp == 0:
            return "0 gp", TEXT_SEC
        sign  = "+" if gp > 0 else "-"
        color = GREEN if gp > 0 else RED
        val   = abs(gp)
        if val >= 1_000_000:
            text = f"{sign}{val / 1_000_000:.1f}m"
        elif val >= 1_000:
            text = f"{sign}{val / 1_000:.1f}k"
        else:
            text = f"{sign}{val:,} gp"
        return text, color

    def _apply_status(self, data):
        if data is None:
            self._dot.itemconfig("dot", fill=TEXT_SEC)
            self._conn_lbl.configure(
                text=f"{self.account.display_name}  (offline)",
                text_color=TEXT_SEC)
            for lbl in (self._world_v, self._hp_v, self._uptime_v):
                lbl.configure(text="—", text_color=TEXT_PRI)
            self._profit_v.configure(text="—", text_color=TEXT_SEC)
            self._script_lbl.configure(text="Script: —", text_color=TEXT_SEC)
            return

        self._dot.itemconfig("dot", fill=GREEN)
        player = data.get("playerName", "Unknown")
        self._conn_lbl.configure(
            text=f"{self.account.display_name}  ({player})", text_color=TEXT_PRI)

        world    = data.get("world", 0)
        hp       = data.get("hp", 0)
        maxhp    = data.get("maxHp", 0)
        up       = data.get("uptimeSeconds", 0)
        paused   = data.get("paused", False)
        script   = data.get("scriptStatus", "IDLE")
        profit   = data.get("profitGp", None)

        self._world_v.configure(text=str(world) if world else "—")
        self._hp_v.configure(
            text=f"{hp}/{maxhp}" if maxhp else "—",
            text_color=RED if maxhp and hp < maxhp * 0.3 else TEXT_PRI)
        h, m, s = up // 3600, (up % 3600) // 60, up % 60
        self._uptime_v.configure(text=f"{h}h {m}m" if h else f"{m}m {s}s")

        if profit is not None:
            txt, col = self._fmt_profit(int(profit))
            self._profit_v.configure(text=txt, text_color=col)
        else:
            # Older plugin version without profitGp — show dash
            self._profit_v.configure(text="—", text_color=TEXT_SEC)

        if paused:
            self._script_lbl.configure(text="Script: ⏸ PAUSED", text_color="#FFA500")
            return

        if self._last_log:
            self._script_lbl.configure(text=f"Script: {self._last_log}", text_color=GREEN)
            return

        display_script = script
        if script in ("IDLE", ""):
            drop_party_active = any(
                p.get("active", False) and
                any(kw in p.get("className", "").lower()
                    for kw in ("dropparty", "drop_party", "babydropparty"))
                for p in self._last_plugins
            )
            if drop_party_active:
                display_script = "DROP PARTY"

        color = GREEN if display_script not in ("IDLE", "") else TEXT_SEC
        self._script_lbl.configure(text=f"Script: {display_script}", text_color=color)

    # ── Favorites ─────────────────────────────────────────────────────────────

    def _toggle_favorite(self, cls: str):
        """Star/unstar a plugin and persist to disk, then re-render plugin list."""
        if cls in self._favorites:
            self._favorites.discard(cls)
        else:
            self._favorites.add(cls)
        # Persist: load full file, update this account's entry, save
        all_favs = _load_favorites()
        all_favs[self.account.id] = list(self._favorites)
        _save_favorites(all_favs)
        # Re-render with current plugin data so order + star colour updates
        self._apply_plugins(self._last_plugins)

    def _apply_plugins(self, data):
        bot_plugins = [p for p in (data or [])
                       if _is_microbot_plugin(p.get("className", ""))]
        self._last_plugins = data or []  # store all plugins for cross-referencing

        if not bot_plugins:
            for _, (row, _btn, _star) in list(self._plugin_rows.items()):
                row.destroy()
            self._plugin_rows.clear()
            self._empty_plug.grid(row=0, column=0, pady=24)
            return

        self._empty_plug.grid_remove()
        seen = set()

        # Sort: favorites first (sorted by name), then rest (sorted by name)
        fav_plugins  = sorted(
            [p for p in bot_plugins if p.get("className", "") in self._favorites],
            key=lambda p: p.get("name", p.get("className", "")).lower())
        rest_plugins = sorted(
            [p for p in bot_plugins if p.get("className", "") not in self._favorites],
            key=lambda p: p.get("name", p.get("className", "")).lower())
        ordered = fav_plugins + rest_plugins

        for idx, plug in enumerate(ordered):
            cls       = plug.get("className", "")
            name      = plug.get("name", cls.split(".")[-1])
            active    = plug.get("active", False)
            is_fav    = cls in self._favorites
            seen.add(cls)

            bg        = BG_ROW if idx % 2 == 0 else BG_TABLE
            dot_color = GREEN if active else TEXT_SEC
            btn_text  = "■ Stop"  if active else "▶ Start"
            btn_fg    = "#6e2020" if active else "#1a5e2a"
            btn_hov   = "#8b2a2a" if active else "#238636"
            star_char = "★" if is_fav else "☆"
            star_fg   = "#f0c040" if is_fav else BTN_GRAY

            if cls in self._plugin_rows:
                row_frame, btn, star_btn = self._plugin_rows[cls]
                # Reposition row in case sort order changed
                row_frame.grid(row=idx, column=0, sticky="ew")
                # Update dot
                children = row_frame.winfo_children()
                if children:
                    children[0].itemconfig("dot", fill=dot_color)
                btn.configure(text=btn_text, fg_color=btn_fg,
                              hover_color=btn_hov,
                              command=lambda c=cls, a=active: self._toggle(c, a))
                star_btn.configure(text=star_char, fg_color=star_fg,
                                   hover_color="#c8a020" if is_fav else BTN_GRAY2,
                                   text_color="#1a1a1a" if is_fav else TEXT_PRI,
                                   command=lambda c=cls: self._toggle_favorite(c))
            else:
                row_frame = ctk.CTkFrame(self._plug_frame, fg_color=bg,
                                          corner_radius=0, height=34)
                row_frame.grid(row=idx, column=0, sticky="ew")
                row_frame.grid_propagate(False)
                row_frame.grid_columnconfigure(2, weight=1)  # name column expands

                dot = tk.Canvas(row_frame, width=10, height=10,
                                bg=bg, highlightthickness=0)
                dot.create_oval(2, 2, 8, 8, fill=dot_color,
                                outline="", tags="dot")
                dot.grid(row=0, column=0, padx=(10, 4), pady=12)

                # Star button (column 1, before name)
                star_btn = ctk.CTkButton(
                    row_frame, text=star_char, width=26, height=22,
                    font=("Segoe UI", 12), fg_color=star_fg,
                    hover_color="#c8a020" if is_fav else BTN_GRAY2,
                    text_color="#1a1a1a" if is_fav else TEXT_PRI,
                    corner_radius=4, border_width=0,
                    command=lambda c=cls: self._toggle_favorite(c))
                star_btn.grid(row=0, column=1, padx=(0, 6), pady=6)

                ctk.CTkLabel(row_frame, text=name, font=FONT_SMALL,
                             text_color=TEXT_PRI, anchor="w").grid(
                    row=0, column=2, sticky="w", padx=4)

                btn = ctk.CTkButton(
                    row_frame, text=btn_text, width=68, height=22,
                    font=FONT_SMALL, fg_color=btn_fg, hover_color=btn_hov,
                    command=lambda c=cls, a=active: self._toggle(c, a))
                btn.grid(row=0, column=3, padx=8)
                self._plugin_rows[cls] = (row_frame, btn, star_btn)

        for cls in list(self._plugin_rows):
            if cls not in seen:
                self._plugin_rows.pop(cls)[0].destroy()

    # ── Plugin toggle + reset ─────────────────────────────────────────────────

    def _toggle(self, class_name: str, currently_active: bool):
        """Toggle plugin: if active → stop it; if inactive → start it."""
        p = self._port()
        if not p:
            return

        def _bg():
            if currently_active:
                _http_post(p, "/plugins/stop", {"className": class_name})
            else:
                _http_post(p, "/plugins/start", {"className": class_name})
            time.sleep(0.6)
            status  = _http_get(p, "/status")
            plugins = _http_get(p, "/plugins") or []
            self.after(0, lambda: self._apply_status(status))
            self.after(0, lambda: self._apply_plugins(plugins))

        threading.Thread(target=_bg, daemon=True).start()

    def _expand_client(self):
        """Bring the RuneLite/Microbot window for this account to the foreground."""
        def _do():
            pid = sw.get_pid(self.account)
            if pid is None:
                return

            # Find all HWNDs belonging to this PID and its children
            target_hwnd = None

            def _enum_cb(hwnd, _):
                nonlocal target_hwnd
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                try:
                    _, wpid = win32process.GetWindowThreadProcessId(hwnd)
                    if wpid == pid:
                        # Prefer windows with a title (the main game window)
                        title = win32gui.GetWindowText(hwnd)
                        if title:
                            target_hwnd = hwnd
                except Exception:
                    pass
                return True

            win32gui.EnumWindows(_enum_cb, None)

            # Also check child processes
            if target_hwnd is None:
                try:
                    parent = psutil.Process(pid)
                    for child in parent.children(recursive=True):
                        def _enum_child(hwnd, _, _cpid=child.pid):
                            # _cpid captured by value via default arg — avoids
                            # loop closure bug where all callbacks would share
                            # the last iteration's child reference.
                            nonlocal target_hwnd
                            if not win32gui.IsWindowVisible(hwnd):
                                return True
                            try:
                                _, wpid = win32process.GetWindowThreadProcessId(hwnd)
                                if wpid == _cpid:
                                    title = win32gui.GetWindowText(hwnd)
                                    if title:
                                        target_hwnd = hwnd
                            except Exception:
                                pass
                            return True
                        win32gui.EnumWindows(_enum_child, None)
                        if target_hwnd:
                            break
                except Exception:
                    pass

            if target_hwnd is None:
                return

            try:
                if win32gui.IsIconic(target_hwnd):
                    win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
                    time.sleep(0.25)
                # Bring to foreground and keep it there (stays until manually minimized)
                for _ in range(3):
                    try:
                        win32gui.ShowWindow(target_hwnd, win32con.SW_SHOW)
                        win32gui.BringWindowToTop(target_hwnd)
                        win32gui.SetForegroundWindow(target_hwnd)
                        time.sleep(0.1)
                        if win32gui.GetForegroundWindow() == target_hwnd:
                            break
                    except Exception:
                        time.sleep(0.2)
            except Exception:
                pass

        threading.Thread(target=_do, daemon=True).start()

    def _reset_all(self):
        """Cycle every active plugin: stop all → 1.2 s → start all."""
        p = self._port()
        if not p:
            return
        active = [cls for cls, (_, btn, _star) in self._plugin_rows.items()
                  if btn.cget("text") == "■ Stop"]
        if not active:
            return

        def _bg():
            for cls in active:
                _http_post(p, "/plugins/stop",  {"className": cls})
            time.sleep(1.2)
            for cls in active:
                _http_post(p, "/plugins/start", {"className": cls})
            time.sleep(0.6)
            status  = _http_get(p, "/status")
            plugins = _http_get(p, "/plugins") or []
            self.after(0, lambda: self._apply_status(status))
            self.after(0, lambda: self._apply_plugins(plugins))

        threading.Thread(target=_bg, daemon=True).start()

    def _reset_profit(self):
        """POST /profit/reset to zero out the session profit counter on the client."""
        p = self._port()
        if not p:
            show_error("Client is offline — cannot reset profit.")
            return

        def _bg():
            ok = _http_post(p, "/profit/reset")
            if ok:
                # Immediately reflect zero in UI
                self.after(0, lambda: self._profit_v.configure(
                    text="0 gp", text_color=TEXT_SEC))
            else:
                self.after(0, lambda: show_error(
                    "Could not reach client.\n"
                    "Make sure the BabyTank HTTP Server plugin is running."))

        threading.Thread(target=_bg, daemon=True).start()


# ── HTTP Port dialog ────────────────────────────────────────────────────────────

class HttpPortDialog(ctk.CTkToplevel):
    def __init__(self, parent, account: cfg.Account):
        super().__init__(parent)
        self.title("Set HTTP Port (Manual Override)")
        self.geometry("400x230")
        self.resizable(False, False)
        self.grab_set()
        self.result = None
        self._build(account)

    def _build(self, account):
        ctk.CTkLabel(self, text=f"Manual HTTP Port — {account.display_name}",
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(
            anchor="w", padx=20, pady=(18, 4))
        ctk.CTkLabel(self,
                     text="Optional override. Leave blank if you want auto-detection.\n"
                          "Auto-detection: the Java plugin picks a free port (7070–7199)\n"
                          "automatically and Baby Tank Switcher matches it by player name.\n"
                          "Only set this manually if auto-detection is not working.",
                     font=FONT_SMALL, text_color=TEXT_SEC, justify="left").pack(
            anchor="w", padx=20)
        self._var = ctk.StringVar(
            value=str(account.http_port) if account.http_port else "")
        ctk.CTkEntry(self, textvariable=self._var, width=200,
                     font=FONT_BODY, placeholder_text="Leave blank for auto").pack(
            padx=20, pady=(10, 16))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack()
        ctk.CTkButton(row, text="Save Override", width=120, fg_color=ACCENT,
                      hover_color="#388bfd", command=self._ok).pack(
            side="left", padx=6)
        ctk.CTkButton(row, text="Clear (use auto)", width=120,
                      fg_color=BTN_GRAY, hover_color=BTN_GRAY2,
                      command=self._clear).pack(side="left", padx=6)
        self.bind("<Return>", lambda e: self._ok())

    def _ok(self):
        v = self._var.get().strip()
        if not v:
            self._clear()
            return
        try:
            port = int(v)
            assert 1024 <= port <= 65535
        except Exception:
            show_error("Port must be a number between 1024 and 65535.")
            return
        self.result = port
        self.destroy()

    def _clear(self):
        self.result = 0
        self.destroy()


# ── BotStatusPage ───────────────────────────────────────────────────────────────

class BotStatusPage(ctk.CTkFrame):
    """
    Grid of _ClientCard widgets — one per account.  (Now called "Bot Manager" in the UI.)

    Auto-detection flow (runs every SCAN_MS in one background thread):
      1. _central_scan() concurrently probes ports 7070-7199, collects
         {port: {status, plugins, logs}}
      2. For each account WITHOUT a manual http_port:
           - Match by playerName == account.display_name (case-insensitive)
           - If matched: call card.push_scan_result(port, status, plugins, logs)
           - If not: call card.push_offline()
      3. Accounts WITH a manual http_port self-poll independently.

    This means only ONE goroutine ever touches the port scan, so cards can
    never race each other and grab the same port's data.
    """
    CARDS_PER_ROW = 2
    SCAN_MS       = 5000

    def __init__(self, parent, app):
        super().__init__(parent, fg_color=BG_DARK)
        self.app      = app
        self._cards: dict = {}   # account.id -> _ClientCard
        self._scanning    = False
        self._build()
        self._refresh_cards()
        self._schedule_scan()

    def _build(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(self, fg_color=BG_MID, corner_radius=0, height=48)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(hdr, text="Bot Manager", font=FONT_HEAD,
                     text_color=TEXT_PRI).pack(side="left", padx=16, pady=12)
        ctk.CTkLabel(hdr,
                     text="Auto-detects clients by player name  •  right-click account to set manual port",
                     font=FONT_SMALL, text_color=TEXT_SEC).pack(side="left", padx=4)
        ctk.CTkButton(hdr, text="↺ Refresh", font=FONT_SMALL,
                      fg_color=BTN_GRAY, hover_color=BTN_GRAY2,
                      height=30, width=90,
                      command=self._manual_refresh).pack(side="right", padx=12, pady=9)

        outer = ctk.CTkFrame(self, fg_color=BG_DARK, corner_radius=0)
        outer.grid(row=1, column=0, sticky="nsew")
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(outer, bg=BG_DARK, highlightthickness=0)
        vsb = tk.Scrollbar(outer, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        self._canvas.grid(row=0, column=0, sticky="nsew")

        self._grid_frame = tk.Frame(self._canvas, bg=BG_DARK)
        self._win_id = self._canvas.create_window((0, 0), window=self._grid_frame,
                                                   anchor="nw")
        self._grid_frame.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Scroll the outer canvas with the mouse wheel.
        # bind_all is scoped: we attach it when this page is shown and detach
        # when hidden so it never interferes with other pages.
        # The plugin CTkScrollableFrame inside each card should be click-drag
        # only — we block mousewheel there by checking widget ancestry.
        def _outer_scroll(event):
            # Always scroll the outer Bot Manager canvas regardless of where
            # the cursor is. The plugin list scrollbar is click-drag only.
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self._outer_scroll_handler = _outer_scroll

        self._empty_lbl = ctk.CTkLabel(
            self._grid_frame,
            text="No accounts yet.\nAdd accounts in Account Overview first.\n\n"
                 "Enable the BabyTank HTTP Server plugin in each Microbot client.\n"
                 "Leave the plugin port at 0 — Baby Tank Switcher auto-detects ports 7070–7199\n"
                 "and matches clients to accounts by player name automatically.",
            font=FONT_BODY, text_color=TEXT_SEC, justify="center")
        self._empty_lbl.grid(row=0, column=0, columnspan=2, padx=60, pady=80)

    def _on_frame_configure(self, _):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self._canvas.itemconfig(self._win_id, width=e.width)

    def _refresh_cards(self):
        """Sync card widgets to current account list."""
        all_accounts = list(self.app.accounts)
        current  = set(self._cards)
        new_ids  = {a.id for a in all_accounts}

        for aid in current - new_ids:
            self._cards.pop(aid).destroy_card()

        for acc in all_accounts:
            if acc.id not in self._cards:
                card = _ClientCard(self._grid_frame, self.app, acc)
                self._cards[acc.id] = card
            else:
                self._cards[acc.id].update_account(acc)

        for idx, (aid, card) in enumerate(self._cards.items()):
            r = idx // self.CARDS_PER_ROW
            c = idx % self.CARDS_PER_ROW
            card.grid(row=r, column=c, padx=10, pady=10, sticky="nsew")
            self._grid_frame.grid_columnconfigure(c, weight=1)

        if self._cards:
            self._empty_lbl.grid_remove()
        else:
            self._empty_lbl.grid(row=0, column=0, columnspan=2, padx=60, pady=80)

    def _schedule_scan(self):
        """Kick off one central scan in a background thread, then reschedule."""
        self._refresh_cards()
        # Only run scan if there are auto-port accounts (no manual override)
        auto_accounts = [a for a in self.app.accounts if not a.http_port]
        if auto_accounts and not self._scanning:
            self._scanning = True
            threading.Thread(target=self._run_scan, daemon=True).start()
        self.after(self.SCAN_MS, self._schedule_scan)

    def _run_scan(self):
        """
        Background thread: scan all ports once, then push results to matching cards.
        playerName from /status is matched case-insensitively to account.display_name.
        Each port can only match ONE account (first match wins, then port is claimed).
        """
        try:
            scan = _central_scan()
            # Build a name->port mapping from scan results
            name_to_data = {}
            for port, data in scan.items():
                player = data["status"].get("playerName", "").strip().lower()
                if player and player not in name_to_data:
                    name_to_data[player] = (port, data)

            # Push results to cards (main thread)
            def _dispatch():
                for acc in list(self.app.accounts):
                    if acc.http_port:
                        continue  # manual port — self-polled
                    card = self._cards.get(acc.id)
                    if not card:
                        continue
                    key = acc.display_name.strip().lower()
                    if key in name_to_data:
                        port, data = name_to_data[key]
                        card.push_scan_result(port, data["status"], data["plugins"],
                                              data.get("logs", []))
                    else:
                        card.push_offline()

            self.after(0, _dispatch)
        finally:
            self._scanning = False

    def _manual_refresh(self):
        self._refresh_cards()
        if not self._scanning:
            self._scanning = True
            threading.Thread(target=self._run_scan, daemon=True).start()

    def on_show(self):
        """Called by App when this page becomes visible — attach our mousewheel handler.
        Uses add='+' so we stack on top of CTkScrollableFrame's own bind_all handlers
        rather than replacing them (CTkScrollableFrame also uses add='+')."""
        self._canvas.bind_all("<MouseWheel>", self._outer_scroll_handler, add="+")

    def on_hide(self):
        """Called by App when this page is hidden — replace our handler with a no-op.
        We cannot cleanly unbind a specific stacked handler in tkinter, so we rebind
        with a no-op. CTkScrollableFrame's handlers (registered with add='+') remain
        intact underneath and work normally on other pages."""
        try:
            self._canvas.bind_all("<MouseWheel>", lambda e: None, add="+")
        except Exception:
            pass


# ── Main window ───────────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Baby Tank Switcher")
        self.geometry("860x520")
        self.minsize(720, 420)
        self.configure(fg_color=BG_DARK)

        self.settings: cfg.Settings = cfg.load_settings()
        self.accounts: list         = cfg.load_accounts()

        self._pages = {}
        self._build()
        self._nav_to("Account Overview")

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        sidebar = ctk.CTkFrame(self, fg_color=BG_SIDE, corner_radius=0, width=180)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        ctk.CTkLabel(sidebar, text="Navigation", font=("Segoe UI", 13, "bold"),
                     text_color=TEXT_HEAD, anchor="w").pack(fill="x", padx=16, pady=(20, 12))

        self._nav_btns = {}
        for item in NAV_ITEMS:
            btn = ctk.CTkButton(
                sidebar, text=item, font=FONT_NAV, anchor="w",
                fg_color="transparent", hover_color=BG_HOVER,
                text_color=TEXT_PRI, corner_radius=6, height=38,
                command=lambda i=item: self._nav_to(i)
            )
            btn.pack(fill="x", padx=8, pady=2)
            self._nav_btns[item] = btn

        self.content = ctk.CTkFrame(self, fg_color=BG_DARK, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self.overview_page    = AccountOverviewPage(self.content, self)
        self.handler_page     = AccountHandlerPage(self.content, self)
        self.bot_status_page  = BotStatusPage(self.content, self)
        self.settings_page    = SettingsPage(self.content, self)
        self.guide_page       = GuidePage(self.content, self)

        self._pages = {
            "Account Overview": self.overview_page,
            "Account Handler":  self.handler_page,
            "Bot Manager":      self.bot_status_page,
            "Settings":         self.settings_page,
            "Guide":            self.guide_page,
        }

    def _nav_to(self, name: str):
        for n, page in self._pages.items():
            if n != name:
                page.grid_forget()
                if hasattr(page, "on_hide"):
                    page.on_hide()
        self._pages[name].grid(row=0, column=0, sticky="nsew")
        if hasattr(self._pages[name], "on_show"):
            self._pages[name].on_show()
        for n, btn in self._nav_btns.items():
            btn.configure(fg_color=BG_HOVER if n == name else "transparent")

    def save(self):
        cfg.save_accounts(self.accounts)


if __name__ == "__main__":
    if sys.platform != "win32":
        print("This tool is Windows-only.")
        sys.exit(1)
    app = App()
    app.mainloop()
