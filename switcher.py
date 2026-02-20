"""
switcher.py - Core logic: save/switch credentials, launch, kill.

Process protection (optional, requires admin):
  When enabled, launched Java processes are hardened against detection:
  1. Launched with CREATE_BREAKAWAY_FROM_JOB so they're detached from any
     job object Baby Tank Switcher itself may be in.
  2. A restrictive DACL is applied — external processes are denied
     PROCESS_VM_READ and PROCESS_QUERY_INFORMATION so they cannot inspect
     the process. Baby Tank Switcher itself retains full access via an
     explicit ACE so it can still track/kill the process.
  3. The parent-process relationship is broken by re-assigning the process
     to a new Job Object.
"""

import ctypes
import ctypes.wintypes as wt
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

# ── Windows API constants ──────────────────────────────────────────────────────

PROCESS_ALL_ACCESS              = 0x1FFFFF
PROCESS_QUERY_INFORMATION       = 0x0400
PROCESS_VM_READ                 = 0x0010
PROCESS_TERMINATE               = 0x0001
PROCESS_SUSPEND_RESUME          = 0x0800

CREATE_NO_WINDOW                = 0x08000000
CREATE_SUSPENDED                = 0x00000004
CREATE_BREAKAWAY_FROM_JOB       = 0x01000000

SE_KERNEL_OBJECT                = 6
DACL_SECURITY_INFORMATION       = 0x00000004
SECURITY_DESCRIPTOR_REVISION    = 1
ACL_REVISION                    = 2

# ACE types / flags
ACCESS_ALLOWED_ACE_TYPE         = 0x00
ACCESS_DENIED_ACE_TYPE          = 0x01
OBJECT_INHERIT_ACE              = 0x01
CONTAINER_INHERIT_ACE           = 0x02

# Specific deny mask for external processes
DENY_MASK = PROCESS_VM_READ | PROCESS_QUERY_INFORMATION

# Job object
JobObjectBasicUIRestrictions    = 4
JOB_OBJECT_UILIMIT_HANDLES      = 0x00000001

# Token / SID
TOKEN_QUERY                     = 0x0008
TokenUser                       = 1

# Well-known SID for "Everyone" (World)
SECURITY_WORLD_SID_AUTHORITY    = (0, 0, 0, 0, 0, 1)
SECURITY_WORLD_RID              = 0

# ── Structures ─────────────────────────────────────────────────────────────────

class STARTUPINFO(ctypes.Structure):
    _fields_ = [
        ("cb",              wt.DWORD),
        ("lpReserved",      wt.LPWSTR),
        ("lpDesktop",       wt.LPWSTR),
        ("lpTitle",         wt.LPWSTR),
        ("dwX",             wt.DWORD),
        ("dwY",             wt.DWORD),
        ("dwXSize",         wt.DWORD),
        ("dwYSize",         wt.DWORD),
        ("dwXCountChars",   wt.DWORD),
        ("dwYCountChars",   wt.DWORD),
        ("dwFillAttribute", wt.DWORD),
        ("dwFlags",         wt.DWORD),
        ("wShowWindow",     wt.WORD),
        ("cbReserved2",     wt.WORD),
        ("lpReserved2",     ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput",       wt.HANDLE),
        ("hStdOutput",      wt.HANDLE),
        ("hStdError",       wt.HANDLE),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess",    wt.HANDLE),
        ("hThread",     wt.HANDLE),
        ("dwProcessId", wt.DWORD),
        ("dwThreadId",  wt.DWORD),
    ]


class JOBOBJECT_BASIC_UI_RESTRICTIONS(ctypes.Structure):
    _fields_ = [("UIRestrictionsClass", wt.DWORD)]


# ── Admin check ────────────────────────────────────────────────────────────────

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


# ── Get current process SID ────────────────────────────────────────────────────

def _get_current_user_sid():
    """
    Return a PSID (ctypes pointer) for the current user's SID,
    or None on failure. Caller must free with LocalFree().
    """
    advapi = ctypes.windll.advapi32
    k32    = ctypes.windll.kernel32

    token = wt.HANDLE()
    if not k32.OpenProcessToken(k32.GetCurrentProcess(), TOKEN_QUERY,
                                ctypes.byref(token)):
        return None

    # Get required buffer size
    needed = wt.DWORD(0)
    advapi.GetTokenInformation(token, TokenUser, None, 0, ctypes.byref(needed))
    buf = ctypes.create_string_buffer(needed.value)
    ok  = advapi.GetTokenInformation(token, TokenUser, buf, needed, ctypes.byref(needed))
    k32.CloseHandle(token)
    if not ok:
        return None

    # TOKEN_USER starts with a SID_AND_ATTRIBUTES; first field is the SID pointer
    sid_ptr = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]

    # Duplicate the SID so it survives beyond buf's lifetime
    sid_len = advapi.GetLengthSid(sid_ptr)
    sid_copy = ctypes.create_string_buffer(sid_len)
    advapi.CopySid(sid_len, sid_copy, sid_ptr)
    return sid_copy


def _get_everyone_sid():
    """Return a ctypes buffer containing the well-known Everyone SID."""
    advapi = ctypes.windll.advapi32
    sia    = (ctypes.c_byte * 6)(0, 0, 0, 0, 0, 1)   # SECURITY_WORLD_SID_AUTHORITY
    sid    = ctypes.c_void_p()
    advapi.AllocateAndInitializeSid(
        ctypes.byref(sia), 1,
        SECURITY_WORLD_RID, 0, 0, 0, 0, 0, 0, 0,
        ctypes.byref(sid))
    return sid


# ── Process protection ─────────────────────────────────────────────────────────

def _apply_process_protection(pid: int) -> bool:
    """
    Apply two layers of protection to a newly launched process.

    Layer 1 — DACL with two ACEs:
      • DENY  Everyone   PROCESS_VM_READ | PROCESS_QUERY_INFORMATION
      • ALLOW current user  PROCESS_ALL_ACCESS
    This stops Jagex from peeking into the process while Baby Tank Switcher
    retains full control so it can still kill / track the process.

    Layer 2 — Job object isolation (re-parent).

    Returns True on full success; False if any step failed (non-fatal).
    """
    k32    = ctypes.windll.kernel32
    advapi = ctypes.windll.advapi32

    h_process = k32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h_process:
        return False

    success = True

    try:
        # ── Build a DACL with explicit ACEs ───────────────────────────────────
        #
        # We use SetSecurityInfo (advapi32) rather than SetKernelObjectSecurity
        # because it handles DACL_SECURITY_INFORMATION cleanly and lets us
        # supply a proper ACL built with Add*Ace helpers.
        #
        # ACL layout (order matters — deny before allow):
        #   [0] ACCESS_DENIED  Everyone  (VM_READ | QUERY_INFORMATION)
        #   [1] ACCESS_ALLOWED CurrentUser (ALL_ACCESS)
        #
        # Sizes:
        #   ACL header  = 8 bytes
        #   ACCESS_DENIED_ACE  header (4) + mask (4) + SID (variable)
        #   ACCESS_ALLOWED_ACE header (4) + mask (4) + SID (variable)

        everyone_sid = _get_everyone_sid()
        user_sid_buf = _get_current_user_sid()

        if everyone_sid and user_sid_buf:
            everyone_len = advapi.GetLengthSid(everyone_sid)
            user_len     = advapi.GetLengthSid(user_sid_buf)

            # Each ACE = 8-byte header+mask + SID bytes
            acl_size = 8 + (8 + everyone_len) + (8 + user_len)
            acl_buf  = ctypes.create_string_buffer(acl_size)

            if advapi.InitializeAcl(acl_buf, acl_size, ACL_REVISION):
                # Deny Everyone first
                advapi.AddAccessDeniedAce(acl_buf, ACL_REVISION,
                                          DENY_MASK, everyone_sid)
                # Allow current user everything
                advapi.AddAccessAllowedAce(acl_buf, ACL_REVISION,
                                           PROCESS_ALL_ACCESS, user_sid_buf)

                # SECURITY_INFORMATION flag 4 = DACL_SECURITY_INFORMATION
                ret = advapi.SetSecurityInfo(
                    h_process,
                    SE_KERNEL_OBJECT,
                    DACL_SECURITY_INFORMATION,
                    None,         # owner SID  (unchanged)
                    None,         # group SID  (unchanged)
                    acl_buf,      # new DACL
                    None,         # SACL       (unchanged)
                )
                if ret != 0:   # 0 == ERROR_SUCCESS
                    success = False
            else:
                success = False

            # Free the Everyone SID allocated by AllocateAndInitializeSid
            advapi.FreeSid(everyone_sid)
        else:
            success = False

        # ── Job object isolation ───────────────────────────────────────────────
        h_job = k32.CreateJobObjectW(None, None)
        if h_job:
            restrictions = JOBOBJECT_BASIC_UI_RESTRICTIONS()
            restrictions.UIRestrictionsClass = JOB_OBJECT_UILIMIT_HANDLES
            k32.SetInformationJobObject(
                h_job,
                JobObjectBasicUIRestrictions,
                ctypes.byref(restrictions),
                ctypes.sizeof(restrictions),
            )
            if not k32.AssignProcessToJobObject(h_job, h_process):
                success = False
            k32.CloseHandle(h_job)
        else:
            success = False

    finally:
        k32.CloseHandle(h_process)

    return success


# ── Public API ─────────────────────────────────────────────────────────────────

def get_active_credentials_path(settings: Settings) -> Path:
    return Path(settings.runelite_folder) / CREDENTIALS_FILENAME


def credentials_exist(settings: Settings) -> bool:
    return get_active_credentials_path(settings).exists()


def import_current_credentials(account: Account, settings: Settings) -> None:
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


def launch(account: Account, settings: Settings,
           protect_process: bool = False) -> int:
    """
    Switch credentials then launch the jar. Returns the PID.
    """
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
    if account.client_args.developer_mode and "-ea" not in jvm_args:
        jvm_args.append("-ea")
    cmd += jvm_args
    cmd += ["-jar", str(jar)]
    cmd += account.client_args.build_args()

    creation_flags = subprocess.CREATE_NO_WINDOW | CREATE_BREAKAWAY_FROM_JOB

    proc = subprocess.Popen(
        cmd,
        cwd=str(jar.parent),
        creationflags=creation_flags,
    )

    pid = proc.pid

    # Apply additional hardening AFTER registering the process so that even if
    # protection partially fails, we still track the PID correctly.
    ps_proc = psutil.Process(pid)
    _running[account.id] = ps_proc

    if protect_process and is_admin():
        _apply_process_protection(pid)
        # Re-open psutil handle after DACL change — the handle psutil cached
        # internally was opened before the DACL was applied so it remains valid,
        # but create a fresh one to be safe.
        try:
            _running[account.id] = psutil.Process(pid)
        except psutil.NoSuchProcess:
            pass

    return pid


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
