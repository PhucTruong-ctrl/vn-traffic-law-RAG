---
name: block-truncated-python-module-write
description: "Block writes that replace query modules with placeholder or truncated source"
condition: "query_understanding\\.py[\\s\\S]{0,500}Preserve current module"
scope: "tool:write(*.py)"
---

Do not overwrite existing Python modules with placeholder or reconstructed content. Re-read complete file, apply a surgical edit, then run `python -m py_compile` before continuing. If recovery is needed, restore the last valid committed version first; never write truncated source.