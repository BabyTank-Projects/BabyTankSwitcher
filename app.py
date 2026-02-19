"""
Baby Tank Switcher - Windows only
Includes embedded Multi-Client Viewer tab.
"""
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import queue

import customtkinter as ctk
from PIL import Image, ImageTk
import win32gui
import win32con
import win32ui
import win32process
from ctypes import windll
import psutil

import config as cfg
import switcher as sw

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

NAV_ITEMS    = ["Account Overview", "Account Handler", "Settings", "Client Viewer", "Guide"]
RAM_OPTIONS  = ["", "512", "1024", "2048", "4096", "8192"]
PROXY_OPTIONS = ["None", "HTTP", "SOCKS4", "SOCKS5"]

GRID_COLUMNS    = 4
THUMB_W_DEFAULT = 320
THUMB_H_DEFAULT = 240


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
        self.rl_var  = ctk.StringVar(value=s.runelite_folder)
        self.cfg_var = ctk.StringVar(value=s.config_location)
        self.jar_var = ctk.StringVar(value=s.jar_path)
        self.jvm_var = ctk.StringVar(value=s.jvm_args)

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
        s.runelite_folder = self.rl_var.get().strip()
        s.config_location = self.cfg_var.get().strip()
        s.jar_path        = self.jar_var.get().strip()
        s.jvm_args        = self.jvm_var.get().strip()
        cfg.save_settings(s)
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
                "Log in to each account via the Jagex Launcher so RuneLite writes credentials.\n\n"
                "Then go to Account Overview and click 'Import Account'. "
                "The account name is read automatically from the credentials file. "
                "Repeat for every account.")

        section("Step 3 - Switch accounts",
                "Select an account and click 'Switch to Account' to copy its credentials "
                "into the active .runelite folder. Then launch your client manually.\n\n"
                "'Refresh Active Account' re-imports credentials for the selected account "
                "from the current .runelite folder (use after re-authenticating).")

        section("Step 4 - Client Arguments",
                "Right-click any account and choose 'Set Client Arguments' to open the "
                "Client Arguments Builder. Options like --developer-mode, --no-update, "
                "RAM limits and proxy settings are applied when launching from Account Handler.")

        section("Step 5 - Account Handler",
                "Use Account Handler to launch and kill Microbot clients per account. "
                "Running clients show a green dot and their PID.\n\n"
                "Use 'Launch All' to start every account at once. Set 'Update Delay (ms)' "
                "to stagger launches so each client starts with a delay (default 1000 ms), "
                "preventing system lag.")

        section("Step 6 - Client Viewer",
                "The Client Viewer tab shows live thumbnails of all running Microbot clients. "
                "Clients appear automatically when launched and disappear when killed. "
                "Click any thumbnail to bring that client to the front. "
                "Click away and it minimizes back. "
                "Enable Movie Mode to drop to 5 FPS and reduce CPU usage.")


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

        ctk.CTkButton(bar, text="▶ Launch", width=100, height=34,
                      font=FONT_SMALL, fg_color="#238636", hover_color="#2ea043",
                      command=self._launch).pack(side="left", padx=(12, 4), pady=9)
        ctk.CTkButton(bar, text="▶ Launch All", width=115, height=34,
                      font=FONT_SMALL, fg_color="#1a5e2a", hover_color="#238636",
                      command=self._launch_all).pack(side="left", padx=4, pady=9)
        ctk.CTkButton(bar, text="■ Kill", width=80, height=34,
                      font=FONT_SMALL, fg_color="#6e2020", hover_color="#8b2a2a",
                      command=self._kill).pack(side="left", padx=4, pady=9)
        ctk.CTkButton(bar, text="■ Kill All", width=90, height=34,
                      font=FONT_SMALL, fg_color="#4a1010", hover_color="#6e2020",
                      command=self._kill_all).pack(side="left", padx=4, pady=9)

        # ── Launch delay spinner ──────────────────────────────────────────────
        delay_wrap = ctk.CTkFrame(bar, fg_color="transparent")
        delay_wrap.pack(side="left", padx=(18, 4), pady=9)
        ctk.CTkLabel(delay_wrap, text="Update Delay (ms):", font=FONT_SMALL,
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

    def _do_launch(self, acc):
        """Launch one account and notify viewer (runs in background thread)."""
        try:
            pid = sw.launch(acc, self.app.settings)
            # Register PID immediately so the viewer knows which process to watch for.
            # Java spawns child JVMs so we also track children in the scan.
            self.app.viewer_page.register_launched_pid(pid)
            self.app.after(0, self.refresh)
            for _ in range(12):
                time.sleep(5)
                self.app.after(0, self.app.viewer_page.scan_for_new_clients)
        except sw.SwitcherError as e:
            self.app.after(0, lambda err=e: show_error(str(err)))
        except FileNotFoundError:
            self.app.after(0, lambda: show_error(
                "Java not found. Make sure Java 17 is installed and on your PATH."))

    def _launch(self):
        acc = self._get_selected()
        if not acc:
            return
        threading.Thread(target=self._do_launch, args=(acc,), daemon=True).start()

    def _launch_all(self):
        accounts = [a for a in self.app.accounts if not sw.is_running(a)]
        if not accounts:
            show_info("All accounts are already running.")
            return
        delay_ms = self._delay_spinner.get()

        def _do():
            for i, acc in enumerate(accounts):
                if i > 0 and delay_ms > 0:
                    time.sleep(delay_ms / 1000.0)
                self._do_launch(acc)
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
            self.app.viewer_page.remove_client_by_account(acc)
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
                self.app.viewer_page.remove_client_by_account(acc)
            except Exception:
                pass
        self.refresh()

    def _tick(self):
        self.refresh()
        self.after(2000, self._tick)


# ── Client Viewer page ────────────────────────────────────────────────────────

class ClientViewerPage(ctk.CTkFrame):
    """
    Embedded PiP multi-client viewer.
    Clients are added/removed automatically by Account Handler.
    """
    CARD_BG = "#1c2128"

    def __init__(self, parent, app):
        super().__init__(parent, fg_color=BG_DARK)
        self.app = app

        self._clients: dict      = {}   # hwnd -> data dict
        self._client_lock        = threading.Lock()
        self._expanded: set      = set()
        self._expanded_lock      = threading.Lock()
        self._paused_clients: set = set()

        self._running     = True
        self._movie_mode  = False
        self._fps         = 20
        self._ui_queue: queue.Queue = queue.Queue()

        self._pid_to_hwnd: dict  = {}   # pid -> hwnd for kill lookups
        self._dismissed: set   = set()  # hwnds explicitly removed — never auto-add again
        self._launched_pids: set = set() # PIDs registered at launch time (root Java processes)

        # Dynamic thumbnail dimensions (recalculated on canvas resize)
        self._thumb_w = THUMB_W_DEFAULT
        self._thumb_h = THUMB_H_DEFAULT

        # Will be set after the window is mapped — used to ignore self-focus in auto-minimize
        self._app_hwnd: int | None = None

        self._build()
        self._start_threads()
        self._process_ui_queue()
        # Grab the Win32 HWND of our root window once it's mapped
        self.after(500, self._capture_app_hwnd)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _capture_app_hwnd(self):
        """Store the Win32 HWND of our root app window for use in auto-minimize logic."""
        try:
            self._app_hwnd = self.app.winfo_id()
        except Exception:
            pass

    def _build(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=BG_MID, corner_radius=0, height=48)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)

        ctk.CTkLabel(hdr, text="Client Viewer", font=FONT_HEAD,
                     text_color=TEXT_PRI).pack(side="left", padx=16, pady=12)

        self._movie_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(hdr, text="🎬 Movie Mode", variable=self._movie_var,
                        font=FONT_SMALL, text_color=TEXT_SEC,
                        command=self._toggle_movie,
                        checkbox_width=18, checkbox_height=18).pack(
            side="left", padx=16)

        ctk.CTkButton(hdr, text="＋ Add Window", font=FONT_SMALL,
                      fg_color=BTN_GRAY, hover_color=BTN_GRAY2,
                      text_color=TEXT_PRI, corner_radius=6,
                      height=30, width=120,
                      command=self._show_add_window_dialog).pack(
            side="left", padx=(0, 8))

        # Status dot + label
        self._status_dot = tk.Canvas(hdr, width=12, height=12,
                                     bg=BG_MID, highlightthickness=0)
        self._status_dot.create_oval(2, 2, 10, 10, fill=GREEN, outline="")
        self._status_dot.pack(side="right", padx=(0, 4), pady=18)
        self._status_lbl = ctk.CTkLabel(hdr, text="Active",
                                        font=FONT_SMALL, text_color=GREEN)
        self._status_lbl.pack(side="right", padx=(0, 12))

        # Scrollable grid
        content = ctk.CTkFrame(self, fg_color=BG_DARK)
        content.pack(fill="both", expand=True, padx=10, pady=10)

        self._canvas = tk.Canvas(content, bg=BG_DARK, highlightthickness=0)
        self._scroll_frame = tk.Frame(self._canvas, bg=BG_DARK)
        self._scroll_frame.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        )
        self._canvas.create_window((0, 0), window=self._scroll_frame, anchor="nw")
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind_all(
            "<MouseWheel>",
            lambda e: self._canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        )
        # Recalculate thumbnail sizes when canvas width changes
        self._canvas.bind("<Configure>", self._on_canvas_resize)

        # Empty state label
        self._empty_lbl = ctk.CTkLabel(
            self._scroll_frame,
            text="No clients running.\nLaunch accounts from the Account Handler tab.",
            font=FONT_BODY, text_color=TEXT_SEC,
        )
        self._empty_lbl.grid(row=0, column=0, padx=60, pady=80)

    def _refresh_empty(self):
        with self._client_lock:
            has_clients = bool(self._clients)
        if has_clients:
            self._empty_lbl.grid_remove()
        else:
            self._empty_lbl.grid(row=0, column=0, padx=60, pady=80)

    def _calc_thumb_size(self, canvas_width: int):
        """Calculate thumbnail dimensions to fill the canvas width evenly."""
        pad = 10 * 2  # padx per card (left + right)
        gap = 10 * 2  # extra margin per column
        available = canvas_width - (GRID_COLUMNS * (pad + gap)) - 4
        w = max(160, available // GRID_COLUMNS)
        h = int(w * 0.75)  # maintain 4:3 aspect ratio
        return w, h

    def _on_canvas_resize(self, event):
        """Recalculate thumbnail sizes and update all existing cards."""
        new_w, new_h = self._calc_thumb_size(event.width)
        if new_w == self._thumb_w and new_h == self._thumb_h:
            return
        self._thumb_w = new_w
        self._thumb_h = new_h
        # Resize all existing card image containers
        with self._client_lock:
            for data in self._clients.values():
                try:
                    data["img_container"].configure(width=new_w, height=new_h)
                except Exception:
                    pass
        self._reorganize()

    # ── Threading helpers ─────────────────────────────────────────────────────

    def _start_threads(self):
        threading.Thread(target=self._capture_loop,          daemon=True).start()
        # NOTE: _monitor_expanded is intentionally NOT started.
        # Clients stay in the foreground after clicking a thumbnail until the
        # user manually minimizes them. No auto-minimize on focus change.
        threading.Thread(target=self._monitor_window_states, daemon=True).start()
        threading.Thread(target=self._monitor_cpu,           daemon=True).start()
        threading.Thread(target=self._auto_scan_loop,        daemon=True).start()

    def _process_ui_queue(self):
        try:
            while not self._ui_queue.empty():
                fn, args, kw = self._ui_queue.get_nowait()
                fn(*args, **kw)
        except Exception:
            pass
        finally:
            if self._running:
                self.after(50, self._process_ui_queue)

    def _queue(self, fn, *args, **kw):
        self._ui_queue.put((fn, args, kw))

    # ── Public API ────────────────────────────────────────────────────────────

    def _auto_scan_loop(self):
        """
        Background thread that polls every 15 s for windows belonging to accounts
        launched through the switcher (PIDs tracked in _pid_to_hwnd).
        Intentionally does NOT auto-add random RuneLite windows the user opened
        themselves — use the '+ Add Window' button for those.
        Respects the dismissed set: if the user removed a card, it won't come back.
        """
        time.sleep(5)
        while self._running:
            try:
                all_pids = self._get_all_tracked_pids()
                if all_pids:
                    def cb(hwnd, _):
                        if not win32gui.IsWindowVisible(hwnd):
                            return True
                        title = win32gui.GetWindowText(hwnd)
                        if not title:
                            return True
                        try:
                            _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        except Exception:
                            return True
                        if pid not in all_pids:
                            return True
                        if hwnd in self._dismissed:
                            return True
                        with self._client_lock:
                            if hwnd in self._clients:
                                return True
                        keywords = ("RuneLite", "Microbot", "Old School RuneScape")
                        if not any(k.lower() in title.lower() for k in keywords):
                            return True
                        with self._client_lock:
                            position = len(self._clients)
                        self._pid_to_hwnd[pid] = hwnd
                        self._queue(self._add_card, hwnd, title, position)
                        return True
                    win32gui.EnumWindows(cb, None)
            except Exception:
                pass
            time.sleep(10)

    def _show_add_window_dialog(self):
        """Show a dialog listing all visible windows so the user can manually add one."""
        def _collect():
            windows = []
            def cb(hwnd, _):
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                title = win32gui.GetWindowText(hwnd)
                if not title:
                    return True
                # Skip our own app and already-tracked windows
                with self._client_lock:
                    already = hwnd in self._clients
                if already:
                    return True
                try:
                    our_root = win32gui.GetAncestor(self.app.winfo_id(), 2)
                    win_root = win32gui.GetAncestor(hwnd, 2)
                    if our_root == win_root:
                        return True
                except Exception:
                    pass
                windows.append((hwnd, title))
                return True
            win32gui.EnumWindows(cb, None)
            self._queue(self._open_add_window_dialog, windows)

        threading.Thread(target=_collect, daemon=True).start()

    def _open_add_window_dialog(self, windows):
        """Open the actual Toplevel dialog on the UI thread."""
        if not windows:
            messagebox.showinfo("No Windows", "No additional windows found.")
            return

        dlg = ctk.CTkToplevel(self.app)
        dlg.title("Add Window")
        dlg.geometry("520x420")
        dlg.configure(fg_color=BG_DARK)
        dlg.transient(self.app)
        dlg.grab_set()
        dlg.lift()

        ctk.CTkLabel(dlg, text="Select a window to monitor",
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(
            anchor="w", padx=20, pady=(20, 8))

        # Search bar
        search_var = tk.StringVar()
        search_entry = ctk.CTkEntry(dlg, textvariable=search_var,
                                    placeholder_text="🔍  Filter windows…",
                                    fg_color=BG_MID, border_color=BORDER,
                                    font=FONT_BODY)
        search_entry.pack(fill="x", padx=20, pady=(0, 8))

        list_frame = ctk.CTkFrame(dlg, fg_color=BG_MID, corner_radius=6)
        list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            bg=BG_MID, fg=TEXT_PRI,
            font=FONT_BODY,
            selectbackground=ACCENT,
            selectforeground="white",
            relief="flat",
            highlightthickness=0,
            activestyle="none",
            bd=0,
        )
        scrollbar.config(command=listbox.yview)
        listbox.pack(side="left", fill="both", expand=True, padx=8, pady=8)

        filtered: list = list(windows)   # [(hwnd, title), ...]

        def _repopulate(term=""):
            listbox.delete(0, "end")
            filtered.clear()
            for hwnd, title in windows:
                if term.lower() in title.lower():
                    filtered.append((hwnd, title))
                    listbox.insert("end", title)

        _repopulate()
        search_var.trace_add("write", lambda *_: _repopulate(search_var.get()))

        def _on_add():
            sel = listbox.curselection()
            if not sel:
                return
            hwnd, title = filtered[sel[0]]
            with self._client_lock:
                position = len(self._clients)
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                self._pid_to_hwnd[pid] = hwnd
            except Exception:
                pass
            self._add_card(hwnd, title, position)
            self._refresh_empty()
            dlg.destroy()

        listbox.bind("<Double-Button-1>", lambda e: _on_add())

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(pady=(0, 16))
        ctk.CTkButton(btn_row, text="Add", width=120, fg_color=ACCENT,
                      hover_color="#1a6fd4", command=_on_add).pack(
            side="left", padx=6)
        ctk.CTkButton(btn_row, text="Cancel", width=120, fg_color=BTN_GRAY,
                      hover_color=BTN_GRAY2, command=dlg.destroy).pack(
            side="left", padx=6)

    def register_launched_pid(self, pid: int):
        """Call right after sw.launch() so we know which process tree to watch."""
        if pid:
            self._launched_pids.add(pid)

    def _get_all_tracked_pids(self) -> set:
        """Return launched PIDs plus all their children (Java spawns child JVMs)."""
        all_pids = set(self._launched_pids)
        for pid in list(self._launched_pids):
            try:
                for child in psutil.Process(pid).children(recursive=True):
                    all_pids.add(child.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return all_pids

    def scan_for_new_clients(self):
        """Scan for windows belonging to processes we launched. Never auto-adds
        anything the user opened themselves — use + Add Window for that."""
        def _do():
            all_pids = self._get_all_tracked_pids()
            if not all_pids:
                return
            found = []
            def cb(hwnd, _):
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                title = win32gui.GetWindowText(hwnd)
                if not title:
                    return True
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                except Exception:
                    return True
                if pid not in all_pids:
                    return True
                with self._client_lock:
                    if hwnd in self._clients:
                        return True
                if hwnd in self._dismissed:
                    return True
                keywords = ("RuneLite", "Microbot", "Old School RuneScape")
                if not any(k.lower() in title.lower() for k in keywords):
                    return True
                found.append((hwnd, title, pid))
                return True
            win32gui.EnumWindows(cb, None)
            for hwnd, title, pid in found:
                with self._client_lock:
                    position = len(self._clients)
                self._pid_to_hwnd[pid] = hwnd
                self._queue(self._add_card, hwnd, title, position)
        threading.Thread(target=_do, daemon=True).start()

    def remove_client_by_account(self, acc):
        """Called after killing an account — remove its viewer card."""
        # Find hwnd via pid map (process may already be dead)
        hwnd = None
        for pid, h in list(self._pid_to_hwnd.items()):
            try:
                proc = psutil.Process(pid)
                if not proc.is_running():
                    hwnd = h
                    del self._pid_to_hwnd[pid]
                    break
            except psutil.NoSuchProcess:
                hwnd = h
                del self._pid_to_hwnd[pid]
                break

        if hwnd is not None:
            self._queue(self._remove_client, hwnd)
        else:
            # Fallback: remove any hwnds that no longer exist
            self._queue(self._remove_dead_clients)

    # ── Card lifecycle ────────────────────────────────────────────────────────

    def _add_card(self, hwnd: int, title: str, position: int):
        with self._client_lock:
            if hwnd in self._clients:
                return

        self._empty_lbl.grid_remove()

        col  = position % GRID_COLUMNS
        row_ = position // GRID_COLUMNS

        card = tk.Frame(self._scroll_frame, bg=self.CARD_BG, relief="flat")
        card.grid(row=row_, column=col, padx=10, pady=10, sticky="nsew")
        self._scroll_frame.grid_columnconfigure(col, weight=1, minsize=self._thumb_w + 30)
        self._scroll_frame.grid_rowconfigure(row_, weight=1)

        # Header row
        card_hdr = tk.Frame(card, bg=self.CARD_BG, height=36)
        card_hdr.pack(fill="x", padx=12, pady=(10, 4))
        card_hdr.pack_propagate(False)

        title_lbl = tk.Label(card_hdr, text=f"#{position+1} {title}",
                             font=("Segoe UI", 10, "bold"),
                             fg=TEXT_PRI, bg=self.CARD_BG, anchor="w")
        title_lbl.pack(side="left", fill="x", expand=True)

        cpu_lbl = tk.Label(card_hdr, text="0%",
                           font=("Segoe UI", 9), fg=TEXT_SEC, bg=self.CARD_BG)
        cpu_lbl.pack(side="right")

        # Thumbnail
        img_frame     = tk.Frame(card, bg="#000000")
        img_frame.pack(padx=12, pady=4)
        img_container = tk.Frame(img_frame, width=self._thumb_w, height=self._thumb_h, bg="#000000")
        img_container.pack()
        img_container.pack_propagate(False)

        img_lbl = tk.Label(img_container, bg="#000000", cursor="hand2")
        img_lbl.pack(fill="both", expand=True)
        img_lbl.bind("<Button-1>", lambda e: self._expand(hwnd))

        # Status row
        stat_row = tk.Frame(card, bg=self.CARD_BG)
        stat_row.pack(fill="x", padx=12, pady=(4, 4))

        stat_dot = tk.Canvas(stat_row, width=10, height=10,
                             bg=self.CARD_BG, highlightthickness=0)
        stat_dot.create_oval(2, 2, 8, 8, fill=GREEN, outline="")
        stat_dot.pack(side="left", padx=(0, 4))

        stat_txt = tk.Label(stat_row, text="Minimized",
                            font=("Segoe UI", 9), fg=TEXT_SEC, bg=self.CARD_BG)
        stat_txt.pack(side="left")

        # Controls
        ctrl = tk.Frame(card, bg=self.CARD_BG)
        ctrl.pack(fill="x", padx=12, pady=(2, 10))

        up_lbl = tk.Label(ctrl, text="↑", fg=TEXT_PRI, bg=self.CARD_BG,
                          cursor="hand2", font=("Segoe UI", 12), padx=8)
        up_lbl.pack(side="left", padx=2)
        up_lbl.bind("<Button-1>", lambda e: self._move(hwnd, -1))

        dn_lbl = tk.Label(ctrl, text="↓", fg=TEXT_PRI, bg=self.CARD_BG,
                          cursor="hand2", font=("Segoe UI", 12), padx=8)
        dn_lbl.pack(side="left", padx=2)
        dn_lbl.bind("<Button-1>", lambda e: self._move(hwnd, 1))
        
        rm_lbl = tk.Label(ctrl, text="✕ Remove", fg=RED, bg=self.CARD_BG,
                  cursor="hand2", font=("Segoe UI", 9))
        rm_lbl.pack(side="right")
        rm_lbl.bind("<Button-1>", lambda e: self._queue(self._remove_client, hwnd))

        with self._client_lock:
            self._clients[hwnd] = {
                "title":         title,
                "frame":         card,
                "label":         img_lbl,
                "img_container": img_container,
                "title_lbl":     title_lbl,
                "cpu_lbl":       cpu_lbl,
                "stat_dot":      stat_dot,
                "stat_txt":      stat_txt,
                "photo":         None,
                "position":      position,
                "last_update":   0,
                "is_minimized":  False,
                "cpu_usage":     0.0,
            }

    def _remove_client(self, hwnd: int):
        with self._client_lock:
            if hwnd not in self._clients:
                return
            self._clients[hwnd]["frame"].destroy()
            del self._clients[hwnd]
            for idx, (h, d) in enumerate(
                sorted(self._clients.items(), key=lambda x: x[1]["position"])
            ):
                d["position"] = idx

        with self._expanded_lock:
            self._expanded.discard(hwnd)
            self._paused_clients.discard(hwnd)

        # Remember this hwnd so auto-scan never re-adds it
        self._dismissed.add(hwnd)

        self._reorganize()
        self._refresh_empty()

    def _remove_dead_clients(self):
        dead = []
        with self._client_lock:
            for hwnd in list(self._clients.keys()):
                if not win32gui.IsWindow(hwnd):
                    dead.append(hwnd)
        for hwnd in dead:
            self._dismissed.add(hwnd)
            self._remove_client(hwnd)

    def _reorganize(self):
        with self._client_lock:
            sorted_c = sorted(self._clients.items(), key=lambda x: x[1]["position"])
            for idx, (hwnd, d) in enumerate(sorted_c):
                r = idx // GRID_COLUMNS
                c = idx % GRID_COLUMNS
                d["frame"].grid(row=r, column=c, padx=10, pady=10, sticky="nsew")
                d["title_lbl"].configure(text=f"#{idx+1} {d['title']}")
                d["position"] = idx
                self._scroll_frame.grid_columnconfigure(c, weight=1, minsize=self._thumb_w + 30)

    # ── Window interaction ────────────────────────────────────────────────────

    def _expand(self, hwnd: int):
        def _do():
            if not win32gui.IsWindow(hwnd):
                return
            with self._expanded_lock:
                self._expanded.add(hwnd)
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.3)
            for _ in range(3):
                try:
                    win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                    win32gui.BringWindowToTop(hwnd)
                    win32gui.SetForegroundWindow(hwnd)
                    time.sleep(0.15)
                    if win32gui.GetForegroundWindow() == hwnd:
                        break
                except Exception:
                    time.sleep(0.2)
        threading.Thread(target=_do, daemon=True).start()

    def _move(self, hwnd: int, direction: int):
        with self._client_lock:
            if hwnd not in self._clients:
                return
            cur = self._clients[hwnd]["position"]
            nxt = cur + direction
            if nxt < 0 or nxt >= len(self._clients):
                return
            target = next(
                (h for h, d in self._clients.items() if d["position"] == nxt), None
            )
            if target:
                self._clients[hwnd]["position"] = nxt
                self._clients[target]["position"] = cur
        self._reorganize()

    # ── Movie mode ────────────────────────────────────────────────────────────

    def _toggle_movie(self):
        self._movie_mode = self._movie_var.get()
        if self._movie_mode:
            self._fps = 5
            self._status_lbl.configure(text="Movie Mode", text_color="#FFA500")
            self._status_dot.delete("all")
            self._status_dot.create_oval(2, 2, 10, 10, fill="#FFA500", outline="")
        else:
            self._fps = 20
            self._status_lbl.configure(text="Active", text_color=GREEN)
            self._status_dot.delete("all")
            self._status_dot.create_oval(2, 2, 10, 10, fill=GREEN, outline="")

    # ── Background threads ────────────────────────────────────────────────────

    def _capture_loop(self):
        while self._running:
            with self._client_lock:
                hwnds = list(self._clients.keys())

            if hwnds:
                t_start = time.time()
                with self._expanded_lock:
                    paused = self._paused_clients.copy()

                for hwnd in hwnds:
                    if hwnd in paused:
                        continue
                    if not win32gui.IsWindow(hwnd):
                        self._queue(self._remove_client, hwnd)
                        continue
                    img = self._capture(hwnd)
                    if img:
                        try:
                            photo = ImageTk.PhotoImage(img)
                            with self._client_lock:
                                if hwnd in self._clients:
                                    self._clients[hwnd]["photo"] = photo
                                    self._clients[hwnd]["last_update"] = time.time()
                            self._queue(self._update_image, hwnd, photo)
                        except Exception:
                            pass

                elapsed = time.time() - t_start
                time.sleep(max(0, 1.0 / self._fps - elapsed))
            else:
                time.sleep(0.1)

    def _capture(self, hwnd) -> Image.Image | None:
        try:
            # If the window is minimized, skip capture so the last good frame is preserved
            if win32gui.IsIconic(hwnd):
                return None

            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            w = right - left
            h = bottom - top
            if w <= 0 or h <= 0:
                return None

            hwndDC = win32gui.GetWindowDC(hwnd)
            mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            bmp    = win32ui.CreateBitmap()
            bmp.CreateCompatibleBitmap(mfcDC, w, h)
            saveDC.SelectObject(bmp)

            # PW_RENDERFULLCONTENT (3) captures even off-screen/occluded windows
            result = windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 3)

            img = None
            if result == 1:
                info = bmp.GetInfo()
                bits = bmp.GetBitmapBits(True)
                img  = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]),
                                        bits, "raw", "BGRX", 0, 1)
                img  = img.resize((self._thumb_w, self._thumb_h), Image.LANCZOS)

            win32gui.DeleteObject(bmp.GetHandle())
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwndDC)
            return img
        except Exception:
            return None

    def _update_image(self, hwnd, photo):
        try:
            with self._client_lock:
                if hwnd not in self._clients:
                    return
                lbl = self._clients[hwnd]["label"]
            lbl.configure(image=photo)
            lbl.image = photo
        except Exception:
            pass

    def _monitor_expanded(self):
        last_fg = None
        while self._running:
            try:
                with self._expanded_lock:
                    exp = self._expanded.copy()
                if exp:
                    fg = win32gui.GetForegroundWindow()
                    if fg != last_fg:
                        # If our own app window just got focus, don't minimize the
                        # expanded clients — the user is just interacting with the
                        # viewer/switcher, not switching away to something else.
                        our_app = self._app_hwnd
                        if our_app is not None:
                            try:
                                # Walk up to the top-level window so child widgets
                                # (canvas, frames) all compare equal to the root.
                                fg_root = win32gui.GetAncestor(fg, 2)  # GA_ROOT = 2
                                app_root = win32gui.GetAncestor(our_app, 2)
                                if fg_root == app_root:
                                    last_fg = fg
                                    time.sleep(0.3)
                                    continue
                            except Exception:
                                pass

                        for hwnd in list(exp):
                            if hwnd == fg:
                                continue
                            if not win32gui.IsWindow(hwnd):
                                with self._expanded_lock:
                                    self._expanded.discard(hwnd)
                                    self._paused_clients.discard(hwnd)
                                continue
                            if not win32gui.IsIconic(hwnd):
                                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                            with self._expanded_lock:
                                self._expanded.discard(hwnd)
                                self._paused_clients.discard(hwnd)
                        last_fg = fg
                time.sleep(0.3)
            except Exception:
                time.sleep(0.5)

    def _monitor_window_states(self):
        while self._running:
            try:
                with self._client_lock:
                    hwnds = list(self._clients.keys())
                for hwnd in hwnds:
                    if not win32gui.IsWindow(hwnd):
                        continue
                    minimized = bool(win32gui.IsIconic(hwnd))
                    with self._client_lock:
                        if hwnd in self._clients:
                            old = self._clients[hwnd].get("is_minimized", False)
                            if old != minimized:
                                self._clients[hwnd]["is_minimized"] = minimized
                                self._queue(self._update_status, hwnd, minimized)
                time.sleep(0.5)
            except Exception:
                time.sleep(1)

    def _update_status(self, hwnd, minimized):
        try:
            with self._client_lock:
                if hwnd not in self._clients:
                    return
                dot = self._clients[hwnd]["stat_dot"]
                txt = self._clients[hwnd]["stat_txt"]
            color = GREEN if minimized else RED
            dot.delete("all")
            dot.create_oval(2, 2, 8, 8, fill=color, outline="")
            txt.configure(text="Minimized" if minimized else "Active")
        except Exception:
            pass

    def _monitor_cpu(self):
        cache: dict = {}
        while self._running:
            try:
                with self._client_lock:
                    hwnds = list(self._clients.keys())
                for dead_h in [h for h in cache if h not in hwnds]:
                    del cache[dead_h]
                for hwnd in hwnds:
                    if not win32gui.IsWindow(hwnd):
                        continue
                    try:
                        if hwnd not in cache:
                            _, pid = win32process.GetWindowThreadProcessId(hwnd)
                            proc = psutil.Process(pid)
                            proc.cpu_percent(interval=None)
                            cache[hwnd] = proc
                        cpu = cache[hwnd].cpu_percent(interval=None)
                        self._queue(self._update_cpu, hwnd, cpu)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        cache.pop(hwnd, None)
                time.sleep(1)
            except Exception:
                time.sleep(2)

    def _update_cpu(self, hwnd, cpu):
        try:
            with self._client_lock:
                if hwnd not in self._clients:
                    return
                lbl = self._clients[hwnd]["cpu_lbl"]
            lbl.configure(text=f"{cpu:.1f}%")
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

        self.overview_page = AccountOverviewPage(self.content, self)
        self.handler_page  = AccountHandlerPage(self.content, self)
        self.settings_page = SettingsPage(self.content, self)
        self.viewer_page   = ClientViewerPage(self.content, self)
        self.guide_page    = GuidePage(self.content, self)

        self._pages = {
            "Account Overview": self.overview_page,
            "Account Handler":  self.handler_page,
            "Settings":         self.settings_page,
            "Client Viewer":    self.viewer_page,
            "Guide":            self.guide_page,
        }

    def _nav_to(self, name: str):
        for page in self._pages.values():
            page.grid_forget()
        self._pages[name].grid(row=0, column=0, sticky="nsew")
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
