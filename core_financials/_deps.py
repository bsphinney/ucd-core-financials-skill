"""Install missing Python packages (the only network use, and only when a package is absent)."""
import importlib
import subprocess
import sys

PIP_NAMES = {"yaml": "PyYAML"}


def ensure(pkgs):
    missing = []
    for mod in pkgs:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(PIP_NAMES.get(mod, mod))
    if not missing:
        return
    base = [sys.executable, "-m", "pip", "install", "--quiet"]
    for extra in (["--user"], ["--break-system-packages"], []):
        if subprocess.run(base + extra + missing).returncode == 0:
            return
    raise RuntimeError(f"Could not install: {', '.join(missing)}")
