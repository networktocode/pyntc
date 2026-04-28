"""Generate code reference pages."""

from pathlib import Path

import mkdocs_gen_files

EXCLUDE_PATHS = {
    "pyntc/devices/pynxos",  # Exclude vendored package pynxos
}

for file_path in Path("pyntc").rglob("*.py"):
    if any(str(file_path).startswith(excluded) for excluded in EXCLUDE_PATHS):
        continue
    module_path = file_path.with_suffix("")
    doc_path = file_path.with_suffix(".md")
    full_doc_path = Path("code-reference", doc_path)

    parts = list(module_path.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]

    with mkdocs_gen_files.open(full_doc_path, "w") as fd:
        IDENTIFIER = ".".join(parts)
        print(f"::: {IDENTIFIER}", file=fd)

    mkdocs_gen_files.set_edit_path(full_doc_path, file_path)
