"""
generate_version_info.py
Called by the GitHub Actions build workflow.
Usage: python generate_version_info.py 1.2.3
"""
import sys

version = sys.argv[1] if len(sys.argv) > 1 else "0.0.0"

parts = version.split(".")
while len(parts) < 4:
    parts.append("0")

# tuple form for FixedFileInfo e.g. (1, 2, 3, 0)
v_tuple = ", ".join(parts[:4])

content = (
    "# UTF-8\n"
    "VSVersionInfo(\n"
    "  ffi=FixedFileInfo(\n"
    f"    filevers=({v_tuple}),\n"
    f"    prodvers=({v_tuple}),\n"
    "    mask=0x3f,\n"
    "    flags=0x0,\n"
    "    OS=0x40004,\n"
    "    fileType=0x1,\n"
    "    subtype=0x0,\n"
    "    date=(0, 0)\n"
    "  ),\n"
    "  kids=[\n"
    "    StringFileInfo([\n"
    "      StringTable(\n"
    "        u'040904B0',\n"
    "        [StringStruct(u'CompanyName', u'BabyTank Projects'),\n"
    "         StringStruct(u'FileDescription', u'Baby Tank Switcher'),\n"
    f"         StringStruct(u'FileVersion', u'{version}'),\n"
    "         StringStruct(u'InternalName', u'BabyTankSwitcher'),\n"
    "         StringStruct(u'LegalCopyright', u''),\n"
    "         StringStruct(u'OriginalFilename', u'BabyTankSwitcher.exe'),\n"
    "         StringStruct(u'ProductName', u'Baby Tank Switcher'),\n"
    f"         StringStruct(u'ProductVersion', u'{version}')])\n"
    "    ]),\n"
    "    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])\n"
    "  ]\n"
    ")\n"
)

with open("version_info.txt", "w") as f:
    f.write(content)

print(f"Generated version_info.txt for version {version}")
