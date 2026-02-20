"""
generate_version_info.py
Called by the GitHub Actions build workflow.
Usage: python generate_version_info.py 1.2.3
"""
import os
import stat
import sys
import tempfile
import shutil

version = sys.argv[1] if len(sys.argv) > 1 else "0.0.0"

parts = version.split(".")
while len(parts) < 4:
    parts.append("0")

v_tuple = ", ".join(parts[:4])

# Build the content using % formatting to avoid f-string brace escaping issues entirely
content = """\
# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(%s),
    prodvers=(%s),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'BabyTank Projects'),
         StringStruct(u'FileDescription', u'Baby Tank Switcher'),
         StringStruct(u'FileVersion', u'%s'),
         StringStruct(u'InternalName', u'BabyTankSwitcher'),
         StringStruct(u'LegalCopyright', u''),
         StringStruct(u'OriginalFilename', u'BabyTankSwitcher.exe'),
         StringStruct(u'ProductName', u'Baby Tank Switcher'),
         StringStruct(u'ProductVersion', u'%s')])
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
""" % (v_tuple, v_tuple, version, version)

script_dir = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(script_dir, "version_info.txt")

if os.path.exists(out):
    try:
        os.chmod(out, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass

try:
    fd, tmp_path = tempfile.mkstemp(dir=script_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
    except Exception:
        os.close(fd)
        raise
    shutil.move(tmp_path, out)
except Exception as e:
    print(f"ERROR: Could not write {out}: {e}")
    sys.exit(1)

print(f"Generated version_info.txt for version {version}")
