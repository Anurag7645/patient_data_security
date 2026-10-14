#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path


def _ensure_venv():
    """Ensure commands run within the project's virtualenv if available."""
    base_dir = Path(__file__).resolve().parent
    venv_dir = base_dir / "venv"
    venv_python = venv_dir / "bin" / "python"

    if venv_python.exists() and not sys.prefix.startswith(str(venv_dir)):
        try:
            os.execv(str(venv_python), [str(venv_python)] + sys.argv)
        except OSError:
            pass


def main():
    """Run administrative tasks."""
    _ensure_venv()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'secure_health.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()

