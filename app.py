"""Baby Tank Switcher - Windows only"""
import sys, threading, time, json as _json, http.client
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import customtkinter as ctk
import win32gui, win32con, win32process, psutil
import config as cfg
import switcher as sw

_managed_plugins: set = cfg.load_managed_plugins()

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BG_DARK=("#0d1117"); BG_SIDE=("#161b22"); BG_MID=("#1c2128"); BG_TABLE=("#161b22")
BG_ROW=("#1c2128");  BG_SEL=("#1f3a5f");  BG_HOVER=("#262d36"); ACCENT=("#2f81f7")
BTN_GRAY=("#30363d");BTN_GRAY2=("#3d444d");TEXT_PRI=("#e6edf3");TEXT_SEC=("#8b949e")
TEXT_HEAD=("#cdd9e5");GREEN=("#3fb950");RED=("#f85149");BORDER=("#30363d")

FN=("Segoe UI",12,"bold"); FH=("Segoe UI",13,"bold"); FB=("Segoe UI",12)
FS=("Segoe UI",10); FM=("Consolas",11); FT=("Segoe UI",18,"bold")
FONT_NAV=FN; FONT_HEAD=FH; FONT_BODY=FB; FONT_SMALL=FS; FONT_MONO=FM; FONT_TITLE=FT

NAV_ITEMS=["Account Overview","Account Handler","Bot Manager","Plugin Manager","Settings","Guide"]

# ── Flicker-free scrollable frame ────────────────────────────────────────────
class _SmoothScrollableFrame(ctk.CTkScrollableFrame):
    """CTkScrollableFrame with a scroll-end repaint to fix Windows ghost rendering."""

    def _get_canvas(self):
        """Return the inner tk.Canvas regardless of CTK version (attribute name varies)."""
        for attr in ("_canvas", "canvas", "_interior_frame"):
            c = getattr(self, attr, None)
            if c is not None and hasattr(c, "update_idletasks"):
                return c
        # Fallback: find first Canvas child widget
        for child in self.winfo_children():
            if isinstance(child, tk.Canvas):
                return child
        return None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scroll_job = None
        canvas = self._get_canvas()
        if canvas is not None:
            canvas.bind("<MouseWheel>", self._on_scroll, add="+")
            canvas.bind("<Button-4>",   self._on_scroll, add="+")
            canvas.bind("<Button-5>",   self._on_scroll, add="+")
        # Also bind on self as a fallback
        self.bind("<MouseWheel>", self._on_scroll, add="+")

    def _on_scroll(self, event=None):
        if self._scroll_job is not None:
            self.after_cancel(self._scroll_job)
        self._scroll_job = self.after(30, self._repaint)

    def _repaint(self):
        self._scroll_job = None
        canvas = self._get_canvas()
        try:
            if canvas is not None:
                canvas.update_idletasks()
                canvas.event_generate("<Configure>")
            self.update_idletasks()
        except Exception:
            pass

RAM_OPTIONS=["","512","1024","2048","4096","8192"]
PROXY_OPTIONS=["None","HTTP","SOCKS4","SOCKS5"]

show_error = lambda msg: messagebox.showerror("Error", msg)
show_info  = lambda msg: messagebox.showinfo("Info", msg)
ask_yn     = lambda t, m: messagebox.askyesno(t, m)

# ── HTTP connection pool ──────────────────────────────────────────────────────
_conns: dict = {}
_conn_lock = threading.Lock()

def _get_conn(port):
    with _conn_lock:
        c = _conns.get(port)
        if not c:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=0.3)
            _conns[port] = c
        return c

def _http_get(port, path):
    for _ in range(2):
        try:
            c = _get_conn(port)
            c.request("GET", path, headers={"Accept":"application/json"})
            return _json.loads(c.getresponse().read().decode())
        except Exception:
            with _conn_lock: _conns.pop(port, None)
    return None

def _http_post(port, path, body=None):
    try:
        import urllib.request
        data = _json.dumps(body or {}).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
              method="POST", headers={"Content-Type":"application/json"})
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        return False

_SCAN_PORTS = list(range(7070, 7200))

def _central_scan():
    results, lock = {}, threading.Lock()
    def _probe(port):
        s = _http_get(port, "/status")
        if s is None: return
        with lock:
            results[port] = {"status": s,
                             "plugins": _http_get(port, "/plugins") or [],
                             "logs":    _http_get(port, "/logs")    or []}
    with ThreadPoolExecutor(max_workers=len(_SCAN_PORTS)) as ex:
        futs = [ex.submit(_probe, p) for p in _SCAN_PORTS]
        for f in futs:
            try: f.result(timeout=1.2)
            except Exception: pass
    return results


# ── Shared widget helpers ─────────────────────────────────────────────────────
def _btn(parent, text, cmd, fg=None, hov=None, w=None, h=34, font=FS, **kw):
    return ctk.CTkButton(parent, text=text, command=cmd,
        fg_color=fg or BTN_GRAY, hover_color=hov or BTN_GRAY2,
        width=w or 100, height=h, font=font, **kw)

def _lbl(parent, text, font=FB, color=TEXT_PRI, **kw):
    return ctk.CTkLabel(parent, text=text, font=font, text_color=color, **kw)

def _entry(parent, var, **kw):
    return ctk.CTkEntry(parent, textvariable=var, fg_color=BG_MID, border_color=BORDER, **kw)


# ── Spinner ───────────────────────────────────────────────────────────────────
class Spinner(ctk.CTkFrame):
    def __init__(self, parent, min_val=0, max_val=60000, step=100, initial=1000, width=70, **kw):
        super().__init__(parent, fg_color=BG_MID, corner_radius=6, border_width=1, border_color=BORDER, **kw)
        self._min, self._max, self._step = min_val, max_val, step
        self._var = tk.IntVar(value=initial)
        ctk.CTkEntry(self, textvariable=self._var, width=width, font=FB,
            fg_color="transparent", border_width=0, justify="center"
        ).grid(row=0, column=0, rowspan=2, padx=(6,0), pady=2)
        bc = dict(width=22, height=16, fg_color=BTN_GRAY, hover_color=BTN_GRAY2,
                  text_color=TEXT_PRI, corner_radius=4, border_width=0)
        ctk.CTkButton(self, text="▲", command=self._up, font=("Segoe UI",9), **bc).grid(row=0,column=1,padx=(2,4),pady=(3,1))
        ctk.CTkButton(self, text="▼", command=self._dn, font=("Segoe UI",9), **bc).grid(row=1,column=1,padx=(2,4),pady=(1,3))

    def _up(self): self._var.set(min(self._var.get()+self._step, self._max))
    def _dn(self): self._var.set(max(self._var.get()-self._step, self._min))
    def get(self):
        try: return int(self._var.get())
        except: return 1000


# ── Dialogs ───────────────────────────────────────────────────────────────────
class RenameDialog(ctk.CTkToplevel):
    def __init__(self, parent, name):
        super().__init__(parent); self.title("Rename Account")
        self.geometry("380x140"); self.resizable(False,False); self.grab_set(); self.result=None
        _lbl(self,"Display name:").pack(anchor="w",padx=20,pady=(18,4))
        self.var = ctk.StringVar(value=name)
        _entry(self, self.var, width=340, font=FB).pack(padx=20)
        row=ctk.CTkFrame(self,fg_color="transparent"); row.pack(pady=14)
        _btn(row,"OK",self._ok,fg=ACCENT,hov="#388bfd").pack(side="left",padx=6)
        _btn(row,"Cancel",self.destroy).pack(side="left",padx=6)
        self.bind("<Return>",lambda e:self._ok())

    def _ok(self):
        v=self.var.get().strip()
        if v: self.result=v; self.destroy()


class ImportDialog(ctk.CTkToplevel):
    def __init__(self, parent, auto_name):
        super().__init__(parent); self.title("Import Account")
        self.geometry("400x200"); self.resizable(False,False); self.grab_set(); self.result=None
        _lbl(self,"Import Account",font=FH).pack(anchor="w",padx=20,pady=(18,4))
        hint="Name detected from credentials file:" if auto_name else "Enter a display name for this account:"
        _lbl(self,hint,font=FS,color=TEXT_SEC).pack(anchor="w",padx=20)
        self.var=ctk.StringVar(value=auto_name)
        _entry(self,self.var,placeholder_text="Account display name",width=360,font=FB).pack(padx=20,pady=(4,16))
        row=ctk.CTkFrame(self,fg_color="transparent"); row.pack()
        _btn(row,"Import",self._ok,fg=ACCENT,hov="#388bfd",w=120).pack(side="left",padx=6)
        _btn(row,"Cancel",self.destroy,w=120).pack(side="left",padx=6)
        self.bind("<Return>",lambda e:self._ok())

    def _ok(self):
        n=self.var.get().strip()
        if not n: show_error("Display name cannot be empty."); return
        self.result=n; self.destroy()


class HttpPortDialog(ctk.CTkToplevel):
    def __init__(self, parent, account):
        super().__init__(parent); self.title("Set HTTP Port (Manual Override)")
        self.geometry("400x230"); self.resizable(False,False); self.grab_set(); self.result=None
        _lbl(self,f"Manual HTTP Port — {account.display_name}",font=FH).pack(anchor="w",padx=20,pady=(18,4))
        _lbl(self,"Optional override. Leave blank for auto-detection.\n"
             "Auto-detection: Java plugin picks a free port (7070-7199)\n"
             "and Baby Tank Switcher matches it by player name.\n"
             "Only set this manually if auto-detection is not working.",
             font=FS,color=TEXT_SEC,justify="left").pack(anchor="w",padx=20)
        self._var=ctk.StringVar(value=str(account.http_port) if account.http_port else "")
        _entry(self,self._var,width=200,font=FB,placeholder_text="Leave blank for auto").pack(padx=20,pady=(10,16))
        row=ctk.CTkFrame(self,fg_color="transparent"); row.pack()
        _btn(row,"Save Override",self._ok,fg=ACCENT,hov="#388bfd",w=120).pack(side="left",padx=6)
        _btn(row,"Clear (use auto)",self._clear,w=120).pack(side="left",padx=6)
        self.bind("<Return>",lambda e:self._ok())

    def _ok(self):
        v=self._var.get().strip()
        if not v: self._clear(); return
        try:
            port=int(v); assert 1024<=port<=65535
        except: show_error("Port must be a number between 1024 and 65535."); return
        self.result=port; self.destroy()

    def _clear(self): self.result=0; self.destroy()


class ClientArgsDialog(ctk.CTkToplevel):
    FLAGS=[
        ("clean_jagex_launcher","Clean Jagex Launcher","Remove Jagex launcher integration"),
        ("developer_mode","Developer Mode","Enable developer tools and logging"),
        ("debug_mode","Debug Mode","Enable additional debugging options"),
        ("microbot_debug","Microbot Debug","Enable Microbot debugging features"),
        ("safe_mode","Safe Mode","Disable external plugins"),
        ("insecure_skip_tls","Insecure Skip TLS","Skip TLS certificate validation (not recommended)"),
        ("disable_telemetry","Disable Telemetry","Prevent sending usage statistics"),
        ("disable_walker_update","Disable Walker Update","Prevent automatic updates to the walker component"),
        ("no_update","No Update","Skip checking for RuneLite updates"),
    ]

    def __init__(self, parent, account):
        super().__init__(parent); self.title("Client Arguments Builder")
        self.geometry("420x680"); self.resizable(False,True); self.grab_set()
        self.account=account; self.result=None; self._build()

    def _build(self):
        sc=_SmoothScrollableFrame(self,fg_color="transparent"); sc.pack(fill="both",expand=True)
        _lbl(sc,"Client Options",font=FH).pack(anchor="w",padx=16,pady=(16,8))
        ca=self.account.client_args; self._fv={}
        for attr,label,desc in self.FLAGS:
            var=tk.BooleanVar(value=getattr(ca,attr)); self._fv[attr]=var
            row=ctk.CTkFrame(sc,fg_color="transparent"); row.pack(fill="x",padx=12,pady=2)
            ctk.CTkCheckBox(row,text=label,variable=var,font=FB,text_color=TEXT_PRI,
                checkbox_width=20,checkbox_height=20).pack(anchor="w")
            _lbl(row,desc,font=FS,color=TEXT_SEC).pack(anchor="w",padx=28)
        _lbl(sc,"Options With Values",font=FH).pack(anchor="w",padx=16,pady=(20,8))

        def le(label,attr,ph=""):
            _lbl(sc,label).pack(anchor="w",padx=16,pady=(6,2))
            var=ctk.StringVar(value=getattr(ca,attr))
            _entry(sc,var,placeholder_text=ph).pack(fill="x",padx=16,pady=(0,2))
            return var

        def ld(label,attr,opts):
            _lbl(sc,label).pack(anchor="w",padx=16,pady=(6,2))
            var=ctk.StringVar(value=getattr(ca,attr) or opts[0])
            ctk.CTkOptionMenu(sc,variable=var,values=opts,fg_color=BG_MID,
                button_color=BTN_GRAY,button_hover_color=BTN_GRAY2).pack(anchor="w",padx=16,pady=(0,2))
            return var

        self._jav=le("JavConfig URL","jav_config_url","Enter URL")
        self._prof=le("Profile","profile","Enter profile name")
        self._proxy=ld("Proxy Type","proxy_type",PROXY_OPTIONS)
        self._ram=ld("RAM Limitation","ram_limitation",RAM_OPTIONS)
        _lbl(sc,"Raw Arguments",font=FH).pack(anchor="w",padx=16,pady=(20,4))
        self._raw=ctk.CTkTextbox(sc,height=70,font=FM,fg_color=BG_MID,border_color=BORDER,border_width=1)
        self._raw.pack(fill="x",padx=16,pady=(0,12)); self._raw.insert("1.0",ca.raw_args)
        bar=ctk.CTkFrame(self,fg_color=BG_MID,height=54,corner_radius=0)
        bar.pack(fill="x",side="bottom"); bar.pack_propagate(False)
        _btn(bar,"Cancel",self.destroy).pack(side="right",padx=(6,16),pady=10)
        _btn(bar,"OK",self._ok,fg=ACCENT,hov="#388bfd").pack(side="right",padx=6,pady=10)

    def _ok(self):
        self.result=cfg.ClientArgs(
            **{attr:self._fv[attr].get() for attr,*_ in self.FLAGS},
            jav_config_url=self._jav.get().strip(), profile=self._prof.get().strip(),
            proxy_type=self._proxy.get(), ram_limitation=self._ram.get(),
            raw_args=self._raw.get("1.0","end").strip())
        self.destroy()


# ── Settings page ─────────────────────────────────────────────────────────────
class SettingsPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent,fg_color="transparent"); self.app=app; self._build()

    def _build(self):
        _lbl(self,"Settings",font=FT).pack(anchor="center",pady=(30,24))
        c=ctk.CTkFrame(self,fg_color="transparent"); c.pack(fill="x",padx=40)
        s=self.app.settings
        self.rl=ctk.StringVar(value=s.runelite_folder)
        self.cf=ctk.StringVar(value=s.config_location)
        self.jr=ctk.StringVar(value=s.jar_path)
        self.jv=ctk.StringVar(value=s.jvm_args)
        self.pr=tk.BooleanVar(value=s.protect_process)

        def field(label,var,browse=None):
            _lbl(c,label).pack(anchor="w",pady=(12,2))
            row=ctk.CTkFrame(c,fg_color="transparent"); row.pack(fill="x")
            _entry(row,var,font=FM).pack(side="left",fill="x",expand=True)
            if browse: _btn(row,"Browse",browse,w=80).pack(side="left",padx=(6,0))

        field("Runelite Location",self.rl,self._brl)
        field("Configurations Location",self.cf,self._bcf)
        field("Microbot Jar Location",self.jr,self._bjr)
        field("JVM Arguments",self.jv)

        pr=ctk.CTkFrame(c,fg_color="transparent"); pr.pack(anchor="w",pady=(16,0))
        ctk.CTkCheckBox(pr,text="Process Protection  (requires admin — hides clients from Jagex fingerprinting)",
            variable=self.pr,font=FB,text_color=TEXT_PRI,checkbox_width=20,checkbox_height=20).pack(side="left")
        _lbl(c,"When enabled, Baby Tank Switcher must be run as Administrator. "
             "Applies Windows process hardening so Jagex cannot inspect launched clients.",
             font=FS,color=TEXT_SEC,wraplength=560,justify="left").pack(anchor="w",padx=28,pady=(2,0))
        _btn(c,"Save Settings",self._save,fg=ACCENT,hov="#388bfd",w=160).pack(pady=24)

    def _brl(self):
        d=filedialog.askdirectory(title="Select .runelite folder",initialdir=self.rl.get())
        if d: self.rl.set(d)
    def _bcf(self):
        d=filedialog.askdirectory(title="Select Configurations folder",initialdir=self.cf.get())
        if d: self.cf.set(d)
    def _bjr(self):
        p=self.jr.get(); init=str(Path(p).parent) if p else str(Path.home())
        f=filedialog.askopenfilename(title="Select Microbot jar",
            filetypes=[("JAR files","*.jar"),("All","*.*")],initialdir=init)
        if f: self.jr.set(f)

    def _save(self):
        s=self.app.settings
        s.runelite_folder=self.rl.get().strip(); s.config_location=self.cf.get().strip()
        s.jar_path=self.jr.get().strip(); s.jvm_args=self.jv.get().strip()
        s.protect_process=self.pr.get(); cfg.save_settings(s)
        if s.protect_process and not sw.is_admin():
            show_info("Settings saved.\n\nWarning: Process Protection is enabled but Baby Tank Switcher "
                      "is not running as Administrator. Protection will be skipped until you relaunch as admin.")
        else:
            show_info("Settings saved.")


# ── Guide page ────────────────────────────────────────────────────────────────
class GuidePage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent,fg_color="transparent"); self._build()

    def _build(self):
        sc=_SmoothScrollableFrame(self,fg_color="transparent",
            scrollbar_button_color=BTN_GRAY,scrollbar_button_hover_color=BTN_GRAY2)
        sc.pack(fill="both",expand=True,padx=30,pady=20)

        def section(title,body):
            _lbl(sc,title,font=FH,color=ACCENT).pack(anchor="w",pady=(16,4))
            _lbl(sc,body,wraplength=600,justify="left").pack(anchor="w",padx=8)

        _lbl(sc,"How to use",font=FT).pack(anchor="w",pady=(0,8))
        section("Step 1 - Configure Settings",
            "Go to Settings and browse to your Microbot jar file. "
            "Runelite Location and Configurations Location are auto-detected.")
        section("Step 2 - Import accounts",
            "Log in to each account via the Jagex Launcher or Microbot Launcher so RuneLite "
            "writes credentials.\n\nThen go to Account Overview and click 'Import Account'. "
            "The account name is read automatically from the credentials file. Repeat for every account.")
        section("Optional Step 3 - Switch accounts (only if session token has expired)",
            "Select an account and click 'Switch to Account' to copy its credentials "
            "into the active .runelite folder. Then launch your client manually.\n\n"
            "'Refresh Active Account' re-imports credentials for the selected account "
            "from the current .runelite folder (use after re-authenticating).")
        section("Step 4 - Account Handler",
            "Use Account Handler to launch and kill Microbot clients per account. "
            "Running clients show a green dot and their PID.\n\nUse 'Launch All' to start every "
            "non-skipped account at once. Check 'Skip Acc' on any row to exclude that account from "
            "Launch All. Set the delay (ms) to stagger launches (default 1000 ms). "
            "Kill All will immediately stop any in-progress Launch All sequence.")
        section("Step 5 - Enable the BabyTank HTTP Server plugin",
            "Inside each Microbot client, enable the BabyTank HTTP Server plugin. "
            "This plugin lets Baby Tank Switcher communicate with your running clients.\n\n"
            "Important: leave the plugin's port setting at its default (0). "
            "It will automatically pick a free port in the 7070-7199 range.\n\n"
            "To confirm auto-detection is working, go to Account Overview, right-click the "
            "account's username, choose 'Override HTTP Port', then click 'Clear (use auto)'. "
            "Baby Tank Switcher will match each client by player name automatically.")
        section("Step 6 - Bot Manager",
            "The Bot Manager tab shows live status for all running clients. "
            "Each card shows HP, profit, world, uptime, and the latest console log message from the script.\n\n"
            "Use Pause/Resume to control scripts. Click 'Expand Client' to bring a client window to "
            "the foreground. Managed plugins (configured in Plugin Manager) appear as Start/Stop toggles on each card.")
        section("Step 7 - Plugin Manager",
            "Go to Plugin Manager to choose which plugins appear as controls in Bot Manager. "
            "All plugins are off by default. Toggle on any plugin you want to manage. "
            "Your selections are saved automatically and persist across restarts.")


# ── Account Overview ──────────────────────────────────────────────────────────
class AccountOverviewPage(ctk.CTkFrame):
    _COL_W=[(0,3),(1,1),(2,2)]

    def __init__(self, parent, app):
        super().__init__(parent,fg_color="transparent")
        self.app=app; self._sel=None; self._rows={}; self._build(); self.refresh()

    def _build(self):
        self.grid_rowconfigure(0,weight=1); self.grid_columnconfigure(0,weight=1)
        self.lf=_SmoothScrollableFrame(self,fg_color=BG_TABLE,
            scrollbar_button_color=BTN_GRAY,scrollbar_button_hover_color=BTN_GRAY2)
        self.lf.grid(row=0,column=0,sticky="nsew")
        for col,w in self._COL_W: self.lf.grid_columnconfigure(col,weight=w)
        for col,(txt,anch) in enumerate(zip(["Account Name","Active","Has Client Arguments"],["w","center","center"])):
            tk.Label(self.lf,text=txt,font=("Segoe UI",11,"bold"),fg=TEXT_HEAD,bg=BG_MID,
                anchor=anch,padx=(20 if col==0 else 0)).grid(row=0,column=col,sticky="ew",ipady=9)
        bar=ctk.CTkFrame(self,fg_color=BG_MID,corner_radius=0,height=52)
        bar.grid(row=1,column=0,sticky="ew"); bar.grid_propagate(False)
        _btn(bar,"Import Account",self._import,w=130,font=FS).pack(side="left",padx=(12,4),pady=9)
        _btn(bar,"Refresh Active Account",self._refresh_active,w=165,font=FS).pack(side="left",padx=4,pady=9)
        _btn(bar,"Delete",self._delete,fg="#6e2020",hov="#8b2a2a",w=80,font=FS).pack(side="left",padx=4,pady=9)
        _btn(bar,"Switch to Account",self._switch,fg=ACCENT,hov="#388bfd",w=140,font=FS).pack(side="left",padx=4,pady=9)

    def refresh(self, sel_only=False):
        cur=[a.id for a in self.app.accounts]; cached=list(self._rows.keys())
        if not sel_only and cur!=cached:
            self._rows.clear()
            for w in self.lf.winfo_children():
                if w.grid_info().get("row",0)==0: continue
                w.destroy()
            if not self.app.accounts:
                tk.Label(self.lf,text="No accounts yet. Click 'Import Account' to get started.",
                    font=FB,fg=TEXT_SEC,bg=BG_TABLE).grid(row=1,column=0,columnspan=3,pady=40)
                return
            for i,acc in enumerate(self.app.accounts): self._make_row(i,acc)
            return
        for i,acc in enumerate(self.app.accounts):
            ws=self._rows.get(acc.id)
            if not ws: continue
            bg=BG_SEL if acc.id==self._sel else (BG_ROW if i%2==0 else BG_TABLE)
            try:
                for w in ws: w.configure(bg=bg)
            except: pass

    def _make_row(self, idx, acc):
        bg=BG_SEL if acc.id==self._sel else (BG_ROW if idx%2==0 else BG_TABLE)
        hc=sw.has_credentials(acc); ha=acc.client_args.has_any(); rn=idx+1
        n=tk.Label(self.lf,text=acc.display_name,font=FB,fg=TEXT_PRI,bg=bg,anchor="w",padx=20)
        n.grid(row=rn,column=0,sticky="ew",ipady=9)
        a=tk.Label(self.lf,text="✓" if hc else "✗",font=FB,fg=GREEN if hc else RED,bg=bg,anchor="center")
        a.grid(row=rn,column=1,sticky="ew",ipady=9)
        r=tk.Label(self.lf,text="✓" if ha else "✗",font=FB,fg=GREEN if ha else RED,bg=bg,anchor="center")
        r.grid(row=rn,column=2,sticky="ew",ipady=9)
        ws=(n,a,r); self._rows[acc.id]=ws
        for w in ws:
            w.bind("<Button-1>",lambda e,x=acc:self._select(x))
            w.bind("<Double-Button-1>",lambda e,x=acc:self._rename(x))
            w.bind("<Button-3>",lambda e,x=acc:self._ctx(e,x))

    def _ctx(self, event, acc):
        self._select(acc)
        m=tk.Menu(self,tearoff=0,bg=BG_MID,fg=TEXT_PRI,activebackground=BG_HOVER,activeforeground=TEXT_PRI,relief="flat",bd=1)
        m.add_command(label="Switch to Account",command=self._switch)
        m.add_command(label="Set Client Arguments",command=lambda:self._set_args(acc))
        pl=f"Override HTTP Port  (pinned: {acc.http_port})" if acc.http_port else "Override HTTP Port  (auto)"
        m.add_command(label=pl,command=lambda:self._set_port(acc))
        m.add_separator()
        m.add_command(label="Rename",command=lambda:self._rename(acc))
        m.add_command(label="Refresh Credentials",command=self._refresh_active)
        m.add_separator()
        m.add_command(label="Delete",command=self._delete)
        try: m.tk_popup(event.x_root,event.y_root)
        finally: m.grab_release()

    def _select(self, acc): self._sel=acc.id; self.refresh(sel_only=True)

    def _get_sel(self):
        if not self._sel: show_error("No account selected."); return None
        return next((a for a in self.app.accounts if a.id==self._sel),None)

    def _import(self):
        s=self.app.settings; cp=sw.get_active_credentials_path(s)
        if not cp.exists():
            show_error(f"credentials.properties not found at:\n{cp}\n\nLaunch RuneLite or Microbot via the Jagex Launcher first.")
            return
        an=cfg.read_account_name_from_credentials(cp)
        if an:
            if any(a.display_name.lower()==an.lower() for a in self.app.accounts):
                if not ask_yn("Duplicate account",f"An account named '{an}' already exists.\nImport again and overwrite its credentials?"): return
            name=an
        else:
            d=ImportDialog(self,""); self.wait_window(d)
            if not d.result: return
            name=d.result
        ex=next((a for a in self.app.accounts if a.display_name.lower()==name.lower()),None)
        if ex:
            try: sw.import_current_credentials(ex,s); show_info(f"Credentials updated for '{name}'.")
            except sw.SwitcherError as e: show_error(str(e))
            self.refresh(); return
        acc=cfg.Account(display_name=name,credentials_file=sw.new_credentials_filename(name))
        try: sw.import_current_credentials(acc,s)
        except sw.SwitcherError as e: show_error(str(e)); return
        self.app.accounts.append(acc); self.app.save(); self.refresh()
        self.app.handler_page.refresh(); show_info(f"Imported account: {name}")

    def _refresh_active(self):
        acc=self._get_sel()
        if not acc: return
        if not ask_yn("Refresh credentials",f"Re-import current credentials.properties into '{acc.display_name}'?"): return
        try: sw.import_current_credentials(acc,self.app.settings); show_info(f"Credentials updated for '{acc.display_name}'."); self.refresh()
        except sw.SwitcherError as e: show_error(str(e))

    def _delete(self):
        acc=self._get_sel()
        if not acc: return
        if not ask_yn("Delete account",f"Delete '{acc.display_name}'?"): return
        self.app.accounts=[a for a in self.app.accounts if a.id!=acc.id]
        self._sel=None; self._rows.clear(); self.app.save(); self.refresh(); self.app.handler_page.refresh()

    def _switch(self):
        acc=self._get_sel()
        if not acc: return
        def _do():
            try: sw.switch_to(acc,self.app.settings); self.app.after(0,lambda:show_info(f"Switched to '{acc.display_name}'.\nYou can now launch your client."))
            except sw.SwitcherError as e: self.app.after(0,lambda:show_error(str(e)))
        threading.Thread(target=_do,daemon=True).start()

    def _set_args(self, acc):
        d=ClientArgsDialog(self,acc); self.wait_window(d)
        if d.result is not None:
            acc.client_args=d.result; self.app.save(); self.refresh(); self.app.handler_page.refresh()

    def _set_port(self, acc):
        d=HttpPortDialog(self,acc); self.wait_window(d)
        if d.result is not None:
            acc.http_port=d.result; self.app.save(); self.refresh()
            self.app.handler_page.refresh(); self.app.bot_status_page._refresh_cards()

    def _rename(self, acc):
        d=RenameDialog(self,acc.display_name); self.wait_window(d)
        if d.result:
            acc.display_name=d.result; self.app.save(); self.refresh(); self.app.handler_page.refresh()


# ── Account Handler ───────────────────────────────────────────────────────────
class AccountHandlerPage(ctk.CTkFrame):
    _COL_W=[(0,3),(1,1),(2,1),(3,2),(4,1)]

    def __init__(self, parent, app):
        super().__init__(parent,fg_color="transparent")
        self.app=app; self._sel=None; self._launching=False; self._cancel=False
        self._alive=True; self._rw={}; self._build(); self.refresh(); self._tick()

    def _build(self):
        self.grid_rowconfigure(0,weight=1); self.grid_columnconfigure(0,weight=1)
        self.lf=_SmoothScrollableFrame(self,fg_color=BG_TABLE,
            scrollbar_button_color=BTN_GRAY,scrollbar_button_hover_color=BTN_GRAY2)
        self.lf.grid(row=0,column=0,sticky="nsew")
        for col,w in self._COL_W: self.lf.grid_columnconfigure(col,weight=w)
        for col,(txt,anch,px) in enumerate(zip(
            ["Account Name","Status","PID","Client Args","Skip Acc"],
            ["w","w","w","w","center"],[20,8,8,8,0])):
            tk.Label(self.lf,text=txt,font=("Segoe UI",11,"bold"),fg=TEXT_HEAD,
                bg=BG_MID,anchor=anch,padx=px).grid(row=0,column=col,sticky="ew",ipady=9)
        bar=ctk.CTkFrame(self,fg_color=BG_MID,corner_radius=0,height=52)
        bar.grid(row=1,column=0,sticky="ew"); bar.grid_propagate(False)
        self._bl=_btn(bar,"▶ Launch",self._launch,fg="#238636",hov="#2ea043",w=100,font=FS)
        self._bl.pack(side="left",padx=(12,4),pady=9)
        self._bla=_btn(bar,"▶ Launch All",self._launch_all,fg="#1a5e2a",hov="#238636",w=115,font=FS)
        self._bla.pack(side="left",padx=4,pady=9)
        _btn(bar,"■ Kill",self._kill,fg="#6e2020",hov="#8b2a2a",w=80,font=FS).pack(side="left",padx=4,pady=9)
        _btn(bar,"■ Kill All",self._kill_all,fg="#4a1010",hov="#6e2020",w=90,font=FS).pack(side="left",padx=4,pady=9)
        dw=ctk.CTkFrame(bar,fg_color="transparent"); dw.pack(side="left",padx=(18,4),pady=9)
        _lbl(dw,"Delay between launches (ms):",font=FS,color=TEXT_SEC).pack(side="left",padx=(0,6))
        self._ds=Spinner(dw,min_val=0,max_val=30000,step=100,initial=1000,width=70); self._ds.pack(side="left")

    def refresh(self):
        self._rw.clear()
        for w in self.lf.winfo_children():
            if w.grid_info().get("row",0)==0: continue
            w.destroy()
        if not self.app.accounts:
            tk.Label(self.lf,text="No accounts yet. Add them in Account Overview.",
                font=FB,fg=TEXT_SEC,bg=BG_TABLE).grid(row=1,column=0,columnspan=5,pady=40)
            return
        for i,acc in enumerate(self.app.accounts): self._make_row(i,acc)

    def _make_row(self, idx, acc):
        run=sw.is_running(acc); pid=sw.get_pid(acc)
        is_sel=acc.id==self._sel
        bg=BG_SEL if is_sel else ("#141920" if acc.skip_launch else (BG_ROW if idx%2==0 else BG_TABLE))
        nc=TEXT_SEC if acc.skip_launch else TEXT_PRI; rn=idx+1
        n=tk.Label(self.lf,text=acc.display_name,font=FB,fg=nc,bg=bg,anchor="w",padx=20)
        n.grid(row=rn,column=0,sticky="ew",ipady=9)
        sl=tk.Label(self.lf,text="● Running" if run else "○ Idle",font=FS,
            fg=GREEN if run else TEXT_SEC,bg=bg,anchor="w",padx=8)
        sl.grid(row=rn,column=1,sticky="ew",ipady=9)
        pl=tk.Label(self.lf,text=str(pid) if pid else "—",font=FM,fg=TEXT_SEC,bg=bg,anchor="w",padx=8)
        pl.grid(row=rn,column=2,sticky="ew",ipady=9)
        ap=(" ".join(acc.client_args.build_args())[:40] or "—")
        al=tk.Label(self.lf,text=ap,font=FS,fg=TEXT_SEC,bg=bg,anchor="w",padx=8)
        al.grid(row=rn,column=3,sticky="ew",ipady=9)
        sv=tk.BooleanVar(value=acc.skip_launch)
        def _on_skip(a=acc,v=sv):
            a.skip_launch=v.get(); self.app.save(); self.refresh(); self.app.bot_status_page._refresh_cards()
        ctk.CTkCheckBox(self.lf,text="",variable=sv,command=_on_skip,width=20,height=20,
            checkbox_width=18,checkbox_height=18,fg_color=ACCENT,hover_color="#388bfd",
            border_color=BTN_GRAY2,bg_color=bg).grid(row=rn,column=4,sticky="",pady=9)
        self._rw[acc.id]=(sl,pl)
        for w in (n,sl,pl,al): w.bind("<Button-1>",lambda e,a=acc:self._select(a))

    def _tick(self):
        def _bg():
            updates=[]
            for acc in list(self.app.accounts):
                ws=self._rw.get(acc.id)
                if not ws: continue
                run=sw.is_running(acc); pid=sw.get_pid(acc)
                updates.append((ws,"● Running" if run else "○ Idle",GREEN if run else TEXT_SEC,str(pid) if pid else "—"))
            def _apply():
                if not self._alive: return
                for (sl,pl),st,sc,pt in updates:
                    try:
                        if sl.cget("text")!=st: sl.configure(text=st,fg=sc)
                        if pl.cget("text")!=pt: pl.configure(text=pt)
                    except: pass
                self.after(3000,self._tick)
            try: self.after(0,_apply)
            except RuntimeError: pass
        try:
            if self.winfo_ismapped(): threading.Thread(target=_bg,daemon=True).start()
            else: self.after(3000,self._tick)
        except: self.after(3000,self._tick)

    def _select(self, acc): self._sel=acc.id; self.refresh()

    def _get_sel(self):
        if not self._sel: show_error("No account selected."); return None
        return next((a for a in self.app.accounts if a.id==self._sel),None)

    def _lock(self, locked, name=""):
        self._launching=locked
        if locked:
            lbl=f"⏳ {name}…" if name else "⏳ Launching…"
            self._bl.configure(state="disabled",fg_color=BTN_GRAY,hover_color=BTN_GRAY,text=lbl)
            self._bla.configure(state="disabled",fg_color=BTN_GRAY,hover_color=BTN_GRAY,text="⏳ Waiting…")
        else:
            self._bl.configure(state="normal",fg_color="#238636",hover_color="#2ea043",text="▶ Launch")
            self._bla.configure(state="normal",fg_color="#1a5e2a",hover_color="#238636",text="▶ Launch All")

    def _wait_login(self, acc, deadline):
        import urllib.request
        nl=acc.display_name.strip().lower()
        def _find():
            ports=[acc.http_port] if acc.http_port else range(7070,7200)
            for port in ports:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/status",timeout=0.1) as r:
                        d=_json.loads(r.read())
                    if d.get("playerName","").strip().lower()==nl: return d.get("loginState","")
                except: pass
        while time.time()<deadline:
            if _find()=="LOGGED_IN": return True
            time.sleep(2)
        return False

    def _do_launch(self, acc, sequential=False, unlock=False):
        try:
            self.app.after(0,lambda n=acc.display_name:self._lock(True,n))
            sw.launch(acc,self.app.settings,protect_process=self.app.settings.protect_process)
            self.app.after(0,self.refresh)
            if sequential or unlock:
                if not self._wait_login(acc,time.time()+180): time.sleep(30)
            else:
                time.sleep(3)
        except sw.SwitcherError as e: self.app.after(0,lambda err=e:show_error(str(err)))
        except FileNotFoundError: self.app.after(0,lambda:show_error("Java not found. Make sure Java 17 is installed and on your PATH."))
        finally:
            if unlock: self.app.after(0,lambda:self._lock(False))

    def _launch(self):
        if self._launching: return
        acc=self._get_sel()
        if not acc: return
        self._lock(True,acc.display_name)
        threading.Thread(target=self._do_launch,args=(acc,),kwargs={"unlock":True},daemon=True).start()

    def _launch_all(self):
        if self._launching: return
        accs=[a for a in self.app.accounts if not sw.is_running(a) and not a.skip_launch]
        if not accs: show_info("All non-skipped accounts are already running (or all accounts are set to skip)."); return
        dm=self._ds.get(); self._cancel=False; self._lock(True,accs[0].display_name)
        def _do():
            try:
                for i,acc in enumerate(accs):
                    if self._cancel: break
                    self.app.after(0,lambda n=acc.display_name:self._lock(True,n))
                    if i>0 and dm>0:
                        el=0
                        while el<dm/1000.0:
                            if self._cancel: break
                            time.sleep(0.1); el+=0.1
                    if self._cancel: break
                    self._do_launch(acc,sequential=True)
            finally: self.app.after(0,lambda:self._lock(False))
        threading.Thread(target=_do,daemon=True).start()

    def _kill(self):
        acc=self._get_sel()
        if not acc: return
        if not sw.is_running(acc): show_error(f"'{acc.display_name}' is not running."); return
        try: sw.kill(acc); self.refresh()
        except sw.SwitcherError as e: show_error(str(e))

    def _kill_all(self):
        run=[a for a in self.app.accounts if sw.is_running(a)]
        if not run: show_info("No clients are running."); return
        if not ask_yn("Kill all",f"Kill all {len(run)} running clients?"): return
        self._cancel=True; self._lock(False)
        for acc in run:
            try: sw.kill(acc)
            except: pass
        self.refresh()


# ── _ClientCard ───────────────────────────────────────────────────────────────
class _ClientCard(ctk.CTkFrame):
    POLL_MS=6000

    def __init__(self, parent, app, account):
        super().__init__(parent,fg_color=BG_MID,corner_radius=8,border_width=1,border_color=BORDER)
        self.app=app; self.account=account; self._alive=True
        self._plugin_rows={}; self._auto_port=None; self._last_plugins=[]
        self._last_log=""; self._offline_ticks=0; self._build()
        if account.http_port: self._self_poll()

    def update_account(self, account):
        op=self.account.http_port; self.account=account; self._update_port_lbl()
        if account.http_port and not op: self._self_poll()

    def push_scan_result(self, port, status, plugins, logs=None):
        if not self._alive: return
        self._auto_port=port; self._offline_ticks=0
        def _a():
            self._update_port_lbl(); self._apply_log(logs or [])
            self._apply_status(status); self._apply_plugins(plugins)
        self.after(0,_a)

    def push_offline(self):
        if not self._alive or self.account.http_port: return
        self._offline_ticks+=1
        if self._offline_ticks<3: return
        self._auto_port=None
        def _a():
            self._update_port_lbl(); self._apply_log([])
            self._apply_status(None); self._apply_plugins(None)
        self.after(0,_a)

    def destroy_card(self): self._alive=False; self.destroy()
    def _port(self): return self.account.http_port or self._auto_port

    def _update_port_lbl(self):
        p=self._port()
        if p: self._plbl.configure(text=f":{p}{'' if self.account.http_port else ' (auto)'}")
        else: self._plbl.configure(text="Scanning..." if not self.account.http_port else "No port set")

    def _build(self):
        self.grid_columnconfigure(0,weight=1)
        hdr=ctk.CTkFrame(self,fg_color=BG_DARK,corner_radius=0,height=40)
        hdr.grid(row=0,column=0,sticky="ew"); hdr.grid_propagate(False); hdr.grid_columnconfigure(1,weight=1)
        self._dot=tk.Canvas(hdr,width=10,height=10,bg=BG_DARK,highlightthickness=0)
        self._dot.create_oval(2,2,8,8,fill=TEXT_SEC,outline="",tags="dot")
        self._dot.grid(row=0,column=0,padx=(12,6),pady=15)
        self._clbl=_lbl(hdr,self.account.display_name,font=FH); self._clbl.grid(row=0,column=1,sticky="w")
        self._plbl=_lbl(hdr,"",font=FS,color=TEXT_SEC); self._plbl.grid(row=0,column=2,padx=(0,12))
        self._update_port_lbl()
        # Fixed-height stat row — never resizes regardless of content
        stat=ctk.CTkFrame(self,fg_color=BG_TABLE,corner_radius=0,height=56)
        stat.grid(row=1,column=0,sticky="ew"); stat.grid_propagate(False)
        stat.grid_columnconfigure((0,1,2,3),weight=1)
        def _cell(col,lbl):
            _lbl(stat,lbl,font=FS,color=TEXT_SEC).grid(row=0,column=col,padx=10,pady=(6,1),sticky="w")
            v=_lbl(stat,"—"); v.grid(row=1,column=col,padx=10,pady=(0,6),sticky="w"); return v
        self._wv=_cell(0,"WORLD"); self._hv=_cell(1,"HP"); self._pv=_cell(2,"PROFIT"); self._uv=_cell(3,"UPTIME")
        # Fixed-height ctrl row — script label truncates, buttons never shift card width
        ctrl=ctk.CTkFrame(self,fg_color=BG_MID,corner_radius=0,height=38)
        ctrl.grid(row=2,column=0,sticky="ew"); ctrl.grid_propagate(False); ctrl.grid_columnconfigure(0,weight=1)
        self._slbl=_lbl(ctrl,"Script: —",font=FS,color=TEXT_SEC,anchor="w")
        self._slbl.grid(row=0,column=0,padx=12,pady=6,sticky="ew")
        pb=ctk.CTkFrame(ctrl,fg_color="transparent"); pb.grid(row=0,column=1,padx=8,pady=4)
        _btn(pb,"⏸ Pause",lambda:self._do_post("/pause"),w=76,h=26,font=FS).pack(side="left",padx=(0,4))
        _btn(pb,"▶ Resume",lambda:self._do_post("/resume"),fg="#1a5e2a",hov="#238636",w=76,h=26,font=FS).pack(side="left",padx=(0,4))
        _btn(pb,"⤢ Expand Client",self._expand,fg="#1a3a5e",hov="#1f4f80",w=110,h=26,font=FS).pack(side="left")
        # Fixed-height plugin header
        ph=ctk.CTkFrame(self,fg_color=BG_DARK,corner_radius=0,height=28)
        ph.grid(row=3,column=0,sticky="ew"); ph.grid_propagate(False)
        _lbl(ph,"Managed Plugins",font=("Segoe UI",11,"bold"),color=TEXT_HEAD,anchor="w").pack(side="left",padx=12,pady=4)
        _btn(ph,"⟳ Reset Profit",self._reset_profit,w=94,h=20,font=FS).pack(side="right",padx=(0,8),pady=4)
        # Plugin rows are fixed height=30 (set in _apply_plugins) so adding/removing never reflows card
        self._pf=ctk.CTkFrame(self,fg_color=BG_TABLE,corner_radius=0)
        self._pf.grid(row=4,column=0,sticky="ew"); self._pf.grid_columnconfigure(0,weight=1)
        self._ep=_lbl(self._pf,"No managed plugins. Configure them in Plugin Manager.",font=FS,color=TEXT_SEC,justify="center")
        self._ep.grid(row=0,column=0,pady=10,padx=12,sticky="w")

    def _self_poll(self):
        if not self._alive or not self.account.http_port: return
        p=self.account.http_port
        def _bg():
            st=_http_get(p,"/status"); pl=_http_get(p,"/plugins") or []; lg=_http_get(p,"/logs") or []
            if not self._alive: return
            try:
                self.after(0,lambda:self._apply_log(lg))
                self.after(0,lambda:self._apply_status(st))
                self.after(0,lambda:self._apply_plugins(pl))
                self.after(self.POLL_MS,self._self_poll)
            except: pass
        threading.Thread(target=_bg,daemon=True).start()

    def _do_post(self, path, body=None):
        p=self._port()
        if p: threading.Thread(target=_http_post,args=(p,path,body),daemon=True).start()

    def _apply_log(self, lines):
        if not lines: self._last_log=""; return
        if isinstance(lines,str): lines=[lines]
        for ln in reversed(lines):
            ln=ln.strip()
            if not ln: continue
            msg=ln.split(" - ",1)[1].strip() if " - " in ln else ln
            self._last_log=msg[:80]+("…" if len(msg)>80 else ""); return
        self._last_log=""

    @staticmethod
    def _fmt_profit(gp):
        if gp==0: return "0 gp",TEXT_SEC
        s,c=("+",GREEN) if gp>0 else ("-",RED); v=abs(gp)
        if v>=1_000_000: t=f"{s}{v/1_000_000:.1f}m"
        elif v>=1_000:   t=f"{s}{v/1_000:.1f}k"
        else:            t=f"{s}{v:,} gp"
        return t,c

    def _apply_status(self, d):
        if d is None:
            self._dot.itemconfig("dot",fill=TEXT_SEC)
            self._clbl.configure(text=f"{self.account.display_name}  (offline)",text_color=TEXT_SEC)
            for l in (self._wv,self._hv,self._uv): l.configure(text="—",text_color=TEXT_PRI)
            self._pv.configure(text="—",text_color=TEXT_SEC)
            self._slbl.configure(text="Script: —",text_color=TEXT_SEC); return
        self._dot.itemconfig("dot",fill=GREEN)
        self._clbl.configure(text=f"{self.account.display_name}  ({d.get('playerName','Unknown')})",text_color=TEXT_PRI)
        w=d.get("world",0); hp=d.get("hp",0); mhp=d.get("maxHp",0)
        up=d.get("uptimeSeconds",0); paused=d.get("paused",False)
        script=d.get("scriptStatus","IDLE"); profit=d.get("profitGp",None)
        self._wv.configure(text=str(w) if w else "—")
        self._hv.configure(text=f"{hp}/{mhp}" if mhp else "—",
            text_color=RED if mhp and hp<mhp*0.3 else TEXT_PRI)
        h,m,s=up//3600,(up%3600)//60,up%60
        self._uv.configure(text=f"{h}h {m}m" if h else f"{m}m {s}s")
        if profit is not None:
            t,c=self._fmt_profit(int(profit)); self._pv.configure(text=t,text_color=c)
        else:
            self._pv.configure(text="—",text_color=TEXT_SEC)
        if paused: self._slbl.configure(text="Script: ⏸ PAUSED",text_color="#FFA500"); return
        if self._last_log: self._slbl.configure(text=f"Script: {self._last_log}",text_color=GREEN); return
        ds=script
        if script in ("IDLE",""):
            if any(p.get("active",False) and any(k in p.get("className","").lower()
                   for k in ("dropparty","drop_party","babydropparty")) for p in self._last_plugins):
                ds="DROP PARTY"
        self._slbl.configure(text=f"Script: {ds}",text_color=GREEN if ds not in ("IDLE","") else TEXT_SEC)

    def _apply_plugins(self, data):
        self._last_plugins=data or []
        managed=sorted([p for p in (data or []) if p.get("className","") in _managed_plugins],
            key=lambda p:p.get("name",p.get("className","")).lower())
        if not managed:
            for cls in list(self._plugin_rows): self._plugin_rows.pop(cls)[0].destroy()
            self._plugin_rows.clear(); self._ep.grid(row=0,column=0,pady=10,padx=12,sticky="w"); return
        self._ep.grid_remove(); seen=set()
        for idx,plug in enumerate(managed):
            cls=plug.get("className",""); name=plug.get("name",cls.split(".")[-1])
            active=plug.get("active",False); seen.add(cls)
            bg=BG_ROW if idx%2==0 else BG_TABLE
            bt="■ Stop" if active else "▶ Start"; bf="#6e2020" if active else "#1a5e2a"; bh="#8b2a2a" if active else "#238636"
            if cls in self._plugin_rows:
                rf,btn,dot=self._plugin_rows[cls]; rf.grid(row=idx,column=0,sticky="ew")
                dot.itemconfig("dot",fill=GREEN if active else TEXT_SEC)
                btn.configure(text=bt,fg_color=bf,hover_color=bh,command=lambda c=cls,a=active:self._toggle(c,a))
            else:
                rf=ctk.CTkFrame(self._pf,fg_color=bg,corner_radius=0,height=30)
                rf.grid(row=idx,column=0,sticky="ew"); rf.grid_propagate(False); rf.grid_columnconfigure(1,weight=1)
                dot=tk.Canvas(rf,width=10,height=10,bg=bg,highlightthickness=0)
                dot.create_oval(2,2,8,8,fill=GREEN if active else TEXT_SEC,outline="",tags="dot")
                dot.grid(row=0,column=0,padx=(10,6),pady=10)
                _lbl(rf,name,font=FS,anchor="w").grid(row=0,column=1,sticky="w")
                btn=_btn(rf,bt,lambda c=cls,a=active:self._toggle(c,a),fg=bf,hov=bh,w=68,h=22,font=FS)
                btn.grid(row=0,column=2,padx=8); self._plugin_rows[cls]=(rf,btn,dot)
        for cls in list(self._plugin_rows):
            if cls not in seen: self._plugin_rows.pop(cls)[0].destroy()

    def _toggle(self, cls, active):
        p=self._port()
        if not p: return
        # Optimistic instant UI flip — no re-render, next scan corrects if needed
        row=self._plugin_rows.get(cls)
        if row:
            rf,btn,dot=row; new_active=not active
            bt="■ Stop" if new_active else "▶ Start"
            bf="#6e2020" if new_active else "#1a5e2a"; bh="#8b2a2a" if new_active else "#238636"
            dot.itemconfig("dot",fill=GREEN if new_active else TEXT_SEC)
            btn.configure(text=bt,fg_color=bf,hover_color=bh,command=lambda c=cls,a=new_active:self._toggle(c,a))
        threading.Thread(target=_http_post,args=(p,"/plugins/stop" if active else "/plugins/start",{"className":cls}),daemon=True).start()

    def _expand(self):
        def _do():
            pid=sw.get_pid(self.account)
            if pid is None: return
            hwnd=None
            def _cb(h,_):
                nonlocal hwnd
                if not win32gui.IsWindowVisible(h): return True
                try:
                    _,wp=win32process.GetWindowThreadProcessId(h)
                    if wp==pid and win32gui.GetWindowText(h): hwnd=h
                except: pass
                return True
            win32gui.EnumWindows(_cb,None)
            if hwnd is None:
                try:
                    for child in psutil.Process(pid).children(recursive=True):
                        def _cc(h,_,cp=child.pid):
                            nonlocal hwnd
                            if not win32gui.IsWindowVisible(h): return True
                            try:
                                _,wp=win32process.GetWindowThreadProcessId(h)
                                if wp==cp and win32gui.GetWindowText(h): hwnd=h
                            except: pass
                            return True
                        win32gui.EnumWindows(_cc,None)
                        if hwnd: break
                except: pass
            if hwnd is None: return
            try:
                if win32gui.IsIconic(hwnd): win32gui.ShowWindow(hwnd,win32con.SW_RESTORE); time.sleep(0.25)
                for _ in range(3):
                    try:
                        win32gui.ShowWindow(hwnd,win32con.SW_SHOW); win32gui.BringWindowToTop(hwnd)
                        win32gui.SetForegroundWindow(hwnd); time.sleep(0.1)
                        if win32gui.GetForegroundWindow()==hwnd: break
                    except: time.sleep(0.2)
            except: pass
        threading.Thread(target=_do,daemon=True).start()

    def _reset_all(self):
        p=self._port()
        if not p: return
        active=[cls for cls,(_,btn,__) in self._plugin_rows.items() if btn.cget("text")=="■ Stop"]
        if not active: return
        # Optimistic: show all as stopped immediately, re-start fires in background
        for cls in active:
            row=self._plugin_rows.get(cls)
            if row:
                rf,btn,dot=row
                dot.itemconfig("dot",fill=TEXT_SEC)
                btn.configure(text="▶ Start",fg_color="#1a5e2a",hover_color="#238636",
                    command=lambda c=cls:self._toggle(c,False))
        def _bg():
            for cls in active: _http_post(p,"/plugins/stop",{"className":cls})
            time.sleep(1.2)
            for cls in active: _http_post(p,"/plugins/start",{"className":cls})
            if not self._alive: return
            # After restart, flip dots/buttons back to active
            def _reactivate():
                for cls in active:
                    row=self._plugin_rows.get(cls)
                    if row:
                        rf,btn,dot=row
                        dot.itemconfig("dot",fill=GREEN)
                        btn.configure(text="■ Stop",fg_color="#6e2020",hover_color="#8b2a2a",
                            command=lambda c=cls:self._toggle(c,True))
            try: self.after(0,_reactivate)
            except RuntimeError: pass
        threading.Thread(target=_bg,daemon=True).start()

    def _reset_profit(self):
        p=self._port()
        if not p: show_error("Client is offline — cannot reset profit."); return
        def _bg():
            ok=_http_post(p,"/profit/reset")
            if not self._alive: return
            try:
                if ok: self.after(0,lambda:self._pv.configure(text="0 gp",text_color=TEXT_SEC))
                else: self.after(0,lambda:show_error("Could not reach client.\nMake sure the BabyTank HTTP Server plugin is running."))
            except RuntimeError: pass
        threading.Thread(target=_bg,daemon=True).start()


# ── BotStatusPage ─────────────────────────────────────────────────────────────
class BotStatusPage(ctk.CTkFrame):
    CARDS_PER_ROW=2; SCAN_MS=3000

    def __init__(self, parent, app):
        super().__init__(parent,fg_color=BG_DARK)
        self.app=app; self._cards={}; self._scanning=False; self._paused=False; self._alive=True
        self._build(); self._refresh_cards(); self._schedule_scan()

    def _build(self):
        self.grid_rowconfigure(1,weight=1); self.grid_columnconfigure(0,weight=1)
        hdr=ctk.CTkFrame(self,fg_color=BG_MID,corner_radius=0,height=48)
        hdr.grid(row=0,column=0,sticky="ew"); hdr.grid_propagate(False); hdr.grid_columnconfigure(0,weight=1)
        _lbl(hdr,"Bot Manager",font=FH).pack(side="left",padx=16,pady=12)
        _lbl(hdr,"Auto-detects clients by player name  •  right-click account to set manual port",font=FS,color=TEXT_SEC).pack(side="left",padx=4)
        _btn(hdr,"↺ Refresh",self._manual_refresh,h=30,w=90,font=FS).pack(side="right",padx=12,pady=9)
        self._sf=_SmoothScrollableFrame(self,fg_color=BG_DARK,
            scrollbar_button_color=BTN_GRAY,scrollbar_button_hover_color=BTN_GRAY2)
        self._sf.grid(row=1,column=0,sticky="nsew")
        self._sf.grid_columnconfigure(0,weight=1); self._sf.grid_columnconfigure(1,weight=1)
        self._gf=self._sf
        self._el=_lbl(self._gf,
            "No accounts yet.\nAdd accounts in Account Overview first.\n\n"
            "Enable the BabyTank HTTP Server plugin in each Microbot client.\n"
            "Leave the plugin port at 0 — Baby Tank Switcher auto-detects ports 7070-7199\n"
            "and matches clients to accounts by player name automatically.",
            color=TEXT_SEC,justify="center")
        self._el.grid(row=0,column=0,columnspan=2,padx=60,pady=80)

    def _refresh_cards(self):
        all_acc=[a for a in self.app.accounts if not a.skip_launch]
        cur=set(self._cards); new={a.id for a in all_acc}
        for aid in cur-new: self._cards.pop(aid).destroy_card()
        for acc in all_acc:
            if acc.id not in self._cards: self._cards[acc.id]=_ClientCard(self._gf,self.app,acc)
            else: self._cards[acc.id].update_account(acc)
        for idx,(aid,card) in enumerate(self._cards.items()):
            r,c=idx//self.CARDS_PER_ROW,idx%self.CARDS_PER_ROW
            card.grid(row=r,column=c,padx=10,pady=10,sticky="nsew")
            self._gf.grid_columnconfigure(c,weight=1)
        if self._cards: self._el.grid_remove()
        else: self._el.grid(row=0,column=0,columnspan=2,padx=60,pady=80)

    def _schedule_scan(self):
        if not self._alive: return
        auto=[a for a in self.app.accounts if not a.http_port and not a.skip_launch]
        if auto and not self._scanning and not self._paused:
            self._scanning=True; threading.Thread(target=self._run_scan,daemon=True).start()
        self.after(self.SCAN_MS,self._schedule_scan)

    def _run_scan(self):
        try:
            scan=_central_scan(); ntd={}
            for port,data in scan.items():
                pl=data["status"].get("playerName","").strip().lower()
                if pl and pl not in ntd: ntd[pl]=(port,data)
            if not self._alive: return
            def _dispatch():
                if not self._alive: return
                for acc in list(self.app.accounts):
                    if acc.http_port: continue
                    card=self._cards.get(acc.id)
                    if not card: continue
                    key=acc.display_name.strip().lower()
                    if key in ntd:
                        port,data=ntd[key]; card.push_scan_result(port,data["status"],data["plugins"],data.get("logs",[]))
                    else: card.push_offline()
            try: self.after(0,_dispatch)
            except RuntimeError: pass
        finally: self._scanning=False

    def _manual_refresh(self):
        self._refresh_cards()
        if not self._scanning:
            self._scanning=True; threading.Thread(target=self._run_scan,daemon=True).start()

    def on_show(self): self._paused=False
    def on_hide(self): self._paused=True


# ── Plugin Manager ────────────────────────────────────────────────────────────
class PluginManagerPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent,fg_color="transparent")
        self.app=app; self._pvars={}; self._known={}; self._prows={}; self._alive=True; self._build()

    def _build(self):
        self.grid_rowconfigure(1,weight=1); self.grid_columnconfigure(0,weight=1)
        hdr=ctk.CTkFrame(self,fg_color=BG_MID,corner_radius=0,height=48)
        hdr.grid(row=0,column=0,sticky="ew"); hdr.grid_propagate(False); hdr.grid_columnconfigure(0,weight=1)
        _lbl(hdr,"Plugin Manager",font=FH).pack(side="left",padx=16,pady=12)
        _lbl(hdr,"Toggle plugins you want to control from Bot Manager  •  all off by default",font=FS,color=TEXT_SEC).pack(side="left",padx=4)
        _btn(hdr,"↺ Scan Clients",self._scan,h=30,w=110,font=FS).pack(side="right",padx=12,pady=9)
        self._sc=_SmoothScrollableFrame(self,fg_color=BG_TABLE,
            scrollbar_button_color=BTN_GRAY,scrollbar_button_hover_color=BTN_GRAY2)
        self._sc.grid(row=1,column=0,sticky="nsew"); self._sc.grid_columnconfigure(0,weight=1)
        self._el=_lbl(self._sc,"No plugins found yet.\n\nMake sure at least one Microbot client is running with the\n"
            "BabyTank HTTP Server plugin enabled, then click '↺ Scan Clients'.",color=TEXT_SEC,justify="center")
        self._el.grid(row=0,column=0,pady=60)

    def on_show(self): self._scan()

    def _scan(self):
        def _bg():
            plugins={}
            for port,data in _central_scan().items():
                for plug in data.get("plugins",[]):
                    cls=plug.get("className",""); name=plug.get("name",cls.split(".")[-1])
                    if cls and cls not in plugins: plugins[cls]=name
            if not self._alive: return
            try: self.after(0,lambda:self._populate(plugins))
            except RuntimeError: pass
        threading.Thread(target=_bg,daemon=True).start()

    def _populate(self, plugins):
        if not plugins and not self._known: self._el.grid(row=0,column=0,pady=60); return
        if not plugins: return
        self._known.update(plugins); self._el.grid_remove()
        sorted_p=sorted(self._known.items(),key=lambda x:x[1].lower())
        stale=set(self._pvars)-set(self._known)
        for cls in stale:
            self._pvars.pop(cls,None)
            rw=self._prows.get(cls)
            if rw: rw.destroy(); self._prows.pop(cls,None)
        for idx,(cls,name) in enumerate(sorted_p):
            if cls in self._prows:
                self._prows[cls].grid(row=idx,column=0,sticky="ew",pady=(0,1))
            else:
                var=tk.BooleanVar(value=cls in _managed_plugins); self._pvars[cls]=var
                bg=BG_ROW if idx%2==0 else BG_TABLE
                row=ctk.CTkFrame(self._sc,fg_color=bg,corner_radius=0)
                row.grid(row=idx,column=0,sticky="ew",pady=(0,1)); row.grid_columnconfigure(1,weight=1)
                self._prows[cls]=row
                ctk.CTkCheckBox(row,text="",variable=var,width=20,height=20,checkbox_width=18,checkbox_height=18,
                    fg_color=ACCENT,hover_color="#388bfd",border_color=BTN_GRAY2,
                    command=lambda c=cls,v=var:self._toggle(c,v)).grid(row=0,column=0,padx=(16,10),pady=10)
                _lbl(row,name,anchor="w").grid(row=0,column=1,sticky="w")
                hint=cls.split(".")[-2] if cls.count(".")>=1 else ""
                if hint: _lbl(row,hint,font=FS,color=TEXT_SEC,anchor="e").grid(row=0,column=2,sticky="e",padx=16)

    def _toggle(self, cls, var):
        if var.get(): _managed_plugins.add(cls)
        else: _managed_plugins.discard(cls)
        cfg.save_managed_plugins(_managed_plugins)


# ── App ───────────────────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__(); self.title("Baby Tank Switcher")
        self.geometry("860x520"); self.minsize(720,420); self.configure(fg_color=BG_DARK)
        self.settings=cfg.load_settings(); self.accounts=cfg.load_accounts()
        self._pages={}; self._alive=True; self._build(); self._nav_to("Account Overview")
        self.bind("<Map>",self._on_restore); self.protocol("WM_DELETE_WINDOW",self._on_close)

    def _on_close(self):
        self._alive=False
        for page in self._pages.values():
            if hasattr(page,"_alive"): page._alive=False
        with _conn_lock:
            for c in _conns.values():
                try: c.close()
                except: pass
            _conns.clear()
        self.destroy()

    def _build(self):
        self.grid_rowconfigure(0,weight=1); self.grid_columnconfigure(1,weight=1)
        sb=ctk.CTkFrame(self,fg_color=BG_SIDE,corner_radius=0,width=180)
        sb.grid(row=0,column=0,sticky="nsew"); sb.grid_propagate(False)
        _lbl(sb,"Navigation",font=("Segoe UI",13,"bold"),color=TEXT_HEAD,anchor="w").pack(fill="x",padx=16,pady=(20,12))
        self._nb={}
        for item in NAV_ITEMS:
            b=ctk.CTkButton(sb,text=item,font=FN,anchor="w",fg_color="transparent",
                hover_color=BG_HOVER,text_color=TEXT_PRI,corner_radius=6,height=38,
                command=lambda i=item:self._nav_to(i))
            b.pack(fill="x",padx=8,pady=2); self._nb[item]=b
        self.content=ctk.CTkFrame(self,fg_color=BG_DARK,corner_radius=0)
        self.content.grid(row=0,column=1,sticky="nsew")
        self.content.grid_rowconfigure(0,weight=1); self.content.grid_columnconfigure(0,weight=1)
        self.overview_page=AccountOverviewPage(self.content,self)
        self.handler_page=AccountHandlerPage(self.content,self)
        self.bot_status_page=BotStatusPage(self.content,self)
        self.plugin_manager_page=PluginManagerPage(self.content,self)
        self.settings_page=SettingsPage(self.content,self)
        self.guide_page=GuidePage(self.content,self)
        self._pages={"Account Overview":self.overview_page,"Account Handler":self.handler_page,
            "Bot Manager":self.bot_status_page,"Plugin Manager":self.plugin_manager_page,
            "Settings":self.settings_page,"Guide":self.guide_page}

    def _nav_to(self, name):
        for n,page in self._pages.items():
            if n!=name: page.grid_forget(); (hasattr(page,"on_hide") and page.on_hide())
        self._pages[name].grid(row=0,column=0,sticky="nsew")
        if hasattr(self._pages[name],"on_show"): self._pages[name].on_show()
        for n,b in self._nb.items(): b.configure(fg_color=BG_HOVER if n==name else "transparent")

    def _on_restore(self, event):
        if event.widget is self: self.after(80,self._do_restore)

    def _do_restore(self):
        try: self.update_idletasks()
        except: pass

    def save(self): cfg.save_accounts(self.accounts)


if __name__ == "__main__":
    if sys.platform != "win32":
        print("This tool is Windows-only."); sys.exit(1)
    App().mainloop()
