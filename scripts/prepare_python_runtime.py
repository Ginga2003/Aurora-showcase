from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT_DIR / ".release"
CACHE_DIR = RELEASE_DIR / "cache"
RUNTIME_DIR = RELEASE_DIR / "python"
PYTHON_VERSION = os.environ.get(
    "AURORA_RELEASE_PYTHON_VERSION",
    f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
)
EMBED_URL = os.environ.get(
    "AURORA_RELEASE_PYTHON_URL",
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip",
)
EMBED_ZIP = CACHE_DIR / f"python-{PYTHON_VERSION}-embed-amd64.zip"


def download_embed_python() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if EMBED_ZIP.exists():
        print(f"Using cached {EMBED_ZIP}")
        return
    print(f"Downloading {EMBED_URL}")
    urllib.request.urlretrieve(EMBED_URL, EMBED_ZIP)


def extract_embed_python() -> None:
    shutil.rmtree(RUNTIME_DIR, ignore_errors=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(EMBED_ZIP) as archive:
        archive.extractall(RUNTIME_DIR)


def patch_python_path() -> None:
    pth_files = list(RUNTIME_DIR.glob("python*._pth"))
    if not pth_files:
        raise RuntimeError("Could not find the embeddable Python ._pth file.")

    pth_file = pth_files[0]
    existing_lines = pth_file.read_text(encoding="utf-8").splitlines()
    cleaned_lines = []
    for line in existing_lines:
        if line.strip() in {"#import site", "import site"}:
            continue
        cleaned_lines.append(line)

    required_lines = [".", "../app", "Lib/site-packages", "import site"]
    normalized = {line.strip() for line in cleaned_lines}
    for line in required_lines:
        if line not in normalized:
            cleaned_lines.append(line)

    pth_file.write_text("\n".join(cleaned_lines) + "\n", encoding="utf-8")


def install_python_dependencies() -> None:
    site_packages = RUNTIME_DIR / "Lib" / "site-packages"
    shutil.rmtree(site_packages, ignore_errors=True)
    site_packages.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--only-binary=:all:",
            "--target",
            str(site_packages),
            "-r",
            str(ROOT_DIR / "requirements.txt"),
        ]
    )


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Aurora Showcase release packaging currently targets Windows.")

    download_embed_python()
    extract_embed_python()
    patch_python_path()
    install_python_dependencies()
    print(f"Python runtime prepared at {RUNTIME_DIR}")


if __name__ == "__main__":
    main()
