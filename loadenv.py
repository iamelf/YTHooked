"""Auto-load key=value pairs from environment.env into os.environ.

Imported by the worker scripts so `python3 push_to_supabase.py` just works
without prefixing secrets on the command line. Existing env vars win, so you
can still override per-run. Never commit environment.env (it's gitignored).
"""
import os
from pathlib import Path


def load_env(path="environment.env"):
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v


load_env()
