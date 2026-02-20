"""
switcher.py - Core logic: save/switch credentials, launch, kill.

Process protection (optional, requires admin):
  When enabled, launched Java processes are hardened against detection:
  1. Launched with CREATE_BREAKAWAY_FROM_JOB so they're detached from any
     job object Baby Tank Switcher itself may be in (e.g. if run from a
     terminal that uses job objects).
  2. A restrictive DACL is applied immediately after launch — external
     processes (including the Jagex client) are denied PROCESS_VM_READ and
     PROCESS_QUERY_INFORMATION so they cannot inspect the process.
  3. The parent-process relationship is broken by re-assigning the process
     to a new Job Object, making it appear to have been spawned independently.
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

# Access rights
PROCESS_ALL_ACCESS              = 0x1FFFFF
PROCESS_QUERY_INFORMATION       = 0x0400
PROCESS_VM_READ                 = 0x0010
PROCESS_TERMINATE               = 0x0001
PROCESS_SUSPEND_RESUME          = 0x0800

# CreateProcess flags
CREATE_NO_WINDOW                = 0x08000000
CREATE_SUSPENDED                = 0x00000004
CREATE_BREAKAWAY_FROM_JOB       = 0x01000000

# Security descriptor / ACL
SE_KERNEL_OBJECT                = 6
DACL_SECURITY_INFORMATION       = 0x00000004
OBJECT_INHERIT_ACE              = 0x01
CONTAINER_INHERIT_ACE           = 0x02
ACCESS_DENIED_ACE_TYPE          = 0x01
SECURITY_DESCRIPTOR_REVISION    = 1
ACL_REVISION                    = 2

# Job object
JobObjectBasicUIRestrictions    = 4
JOB_OBJECT_UILIMIT_HANDLES      = 0x00000001

# Token elevation
TOKEN_QUERY                     = 0x0008
TokenElevation                  = 20

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
    """Return True if the current process is running with admin privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


# ── Process protection ─────────────────────────────────────────────────────────

def _apply_process_protection(pid: int) -> bool:
    """
    Apply three layers of protection to a newly launched process:

    1. DACL hardening — deny PROCESS_VM_READ and PROCESS_QUERY_INFORMATION
       to everyone except SYSTEM and the process owner. This stops the Jagex
       client from opening a handle to inspect our process.

    2. Job object isolation — assign the process to a fresh Job Object with
       UI handle restrictions, breaking the inherited job context and making
       the process look independently spawned.

    3. The process was already launched with CREATE_BREAKAWAY_FROM_JOB which
       detaches it from any job object Baby Tank Switcher is running inside
       (common when launched from terminals or CI environments).

    Returns True on full success, False if any step failed (non-fatal —
    the process still runs, just without protection).
    """
    k32    = ctypes.windll.kernel32
    advapi = ctypes.windll.advapi32

    h_process = k32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h_process:
        return False

    success = True

    try:
        # ── Step 1: Build a restrictive DACL ──────────────────────────────────
        # Create an empty (deny-all) DACL then set it on the process object.
        # We create a new security descriptor with an empty ACL — this effectively
        # denies all access to any principal not explicitly granted (i.e. SYSTEM
        # still works via kernel bypass, but userland Jagex code cannot query us).

        # Allocate a SECURITY_DESCRIPTOR
        sd = ctypes.create_string_buffer(256)
        if not advapi.InitializeSecurityDescriptor(sd, SECURITY_DESCRIPTOR_REVISION):
            success = False
        else:
            # Allocate an empty ACL (minimum size: header only)
            acl_size = 8  # sizeof(ACL)
            acl_buf = ctypes.create_string_buffer(acl_size)
            if not advapi.InitializeAcl(acl_buf, acl_size, ACL_REVISION):
                success = False
            else:
                # Attach the empty DACL to our security descriptor
                if not advapi.SetSecurityDescriptorDacl(sd, True, acl_buf, False):
                    success = False
                else:
                    # Apply the security descriptor to the process kernel object
                    # SetKernelObjectSecurity is simpler than SetSecurityInfo for this
                    if not k32.SetKernelObjectSecurity(
                        h_process, DACL_SECURITY_INFORMATION, sd
                    ):
                        success = False

        # ── Step 2: Job object isolation ──────────────────────────────────────
        # Create a new Job Object and assign the process to it.
        # This re-parents the job context so the process no longer looks like
        # it's in Baby Tank Switcher's process tree.
        h_job = k32.CreateJobObjectW(None, None)
        if h_job:
            # Apply UI restrictions to the job — limits handle inheritance
            restrictions = JOBOBJECT_BASIC_UI_RESTRICTIONS()
            restrictions.UIRestrictionsClass = JOB_OBJECT_UILIMIT_HANDLES
            k32.SetInformationJobObject(
                h_job,
                JobObjectBasicUIRestrictions,
                ctypes.byref(restrictions),
                ctypes.sizeof(restrictions)
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


def launch(account: Account, settings: Settings,
           protect_process: bool = False) -> int:
    """
    Switch credentials then launch the jar. Returns the PID.

    protect_process: if True (and running as admin), applies Windows process
    hardening to make the child process harder for Jagex to detect/inspect.
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

    # Always use CREATE_BREAKAWAY_FROM_JOB so the child is not in our job tree.
    # CREATE_NO_WINDOW keeps it backgrounded.
    creation_flags = subprocess.CREATE_NO_WINDOW | CREATE_BREAKAWAY_FROM_JOB

    proc = subprocess.Popen(
        cmd,
        cwd=str(jar.parent),
        creationflags=creation_flags,
    )

    pid = proc.pid

    # Apply additional hardening if requested and we have admin rights
    if protect_process:
        if is_admin():
            _apply_process_protection(pid)
        # If not admin, silently skip — process still launched fine

    ps_proc = psutil.Process(pid)
    _running[account.id] = ps_proc
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
