#!/usr/bin/env python3
# scripts/zip_logger_backup.py
# Cross-platform friendly: pathlib, forward-slash logs, broader excludes.
# Ubuntu/Windows compatible.

from __future__ import annotations
from pathlib import Path
from datetime import datetime
import hashlib
import zipfile
import os


def _posix(p: str) -> str:
    return p.replace("\\", "/")


# === Project Root ===
# If this file lives in scripts/, project root is one level up.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# === Directories ===
BACKUP_DIR = PROJECT_ROOT / "backups"
SCHEMA_DIR = PROJECT_ROOT / "schema"
SKELETONS_DIR = SCHEMA_DIR / "skeletons"
SKELETON_PATH = SKELETONS_DIR / "project_skeleton.txt"
HASH_LOG = BACKUP_DIR / "hash_log.txt"

BACKUP_DIR.mkdir(parents=True, exist_ok=True)
SKELETONS_DIR.mkdir(parents=True, exist_ok=True)

# === Include / Exclude Rules ===
INCLUDE_EXTENSIONS = {
    ".py",
    ".sql",
    ".js",
    ".css",
    ".img",
    ".txt",
    ".md",
    ".example",
    ".ini",
    ".mako",
}

EXCLUDE_DIRS = {
    "__pycache__",
    ".ruff_cache",
    ".pytest_cache",
    ".mypy_cache",
    ".git",
    ".idea",
    ".vscode",
    "scripts",
    "venv",
    "node_modules",
    BACKUP_DIR.name,  # "backups"
}

EXCLUDE_FILES = {".DS_Store", ".env"}

EXCLUDE_PATTERNS = [
    "-legacy",
    ".tmp",
    ".bak",
    "~$",
    ".log",
    ".pyc",
    ".pyo",
    ".pyd",
    ".DS_Store",
    "Thumbs.db",
]


# === Helpers ===
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def gather_project_files() -> list[Path]:
    """Collect project files while excluding caches, envs, and backups."""
    files: list[Path] = []
    for root, dirs, fnames in os.walk(PROJECT_ROOT):
        # filter directories in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fname in fnames:
            if fname in EXCLUDE_FILES:
                continue
            fpath = Path(root) / fname
            name = fpath.name
            ext = fpath.suffix.lower()

            # exclude by pattern
            if any(pat in name for pat in EXCLUDE_PATTERNS):
                continue

            # include only whitelisted extensions (keeps backups small/clean)
            if ext in INCLUDE_EXTENSIONS:
                files.append(fpath)
    return files


def create_zip_backup(files: list[Path], zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for f in files:
            arc = f.relative_to(PROJECT_ROOT).as_posix()  # forward slash
            zipf.write(f, arcname=arc)


def log_hashes(files: list[Path], zip_name: str) -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    with HASH_LOG.open("a", encoding="utf-8", newline="\n") as logf:
        logf.write(
            f"\n=== Backup: {zip_name} | {datetime.utcnow().isoformat()} UTC ===\n"
        )
        for f in files:
            rel = f.relative_to(PROJECT_ROOT).as_posix()
            logf.write(f"{rel} : {sha256_file(f)}\n")


def generate_project_skeleton(output_path: Path) -> None:
    SKELETONS_DIR.mkdir(parents=True, exist_ok=True)

    exclude_dirs = {
        "venv",
        "__pycache__",
        ".ruff_cache",
        ".pytest_cache",
        ".mypy_cache",
        ".git",
        ".idea",
        ".vscode",
        "node_modules",
        BACKUP_DIR.name,
    }
    exclude_patterns = EXCLUDE_PATTERNS[:]  # reuse patterns

    def _print_tree(start: Path, out, prefix: str = "") -> None:
        entries = sorted(start.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        files = [
            p
            for p in entries
            if p.is_file() and not any(pat in p.name for pat in exclude_patterns)
        ]
        dirs = [p for p in entries if p.is_dir() and p.name not in exclude_dirs]

        # files first
        for i, f in enumerate(files):
            connector = "└── " if (i == len(files) - 1 and not dirs) else "├── "
            out.write(prefix + connector + f.name + "\n")

        # then dirs
        for i, d in enumerate(dirs):
            connector = "└── " if i == len(dirs) - 1 else "├── "
            out.write(prefix + connector + d.name + "/\n")
            new_prefix = prefix + ("    " if i == len(dirs) - 1 else "│   ")
            _print_tree(d, out, new_prefix)

    with output_path.open("w", encoding="utf-8", newline="\n") as out:
        out.write("./\n")
        _print_tree(PROJECT_ROOT, out)


def run_zip_backup() -> None:
    print("[*] Proje ağacı dosyası oluşturuluyor...")
    generate_project_skeleton(SKELETON_PATH)

    print("[*] Dosyalar toplanıyor...")
    files = gather_project_files()

    print(
        f"[+] {_posix(str(SKELETON_PATH))} oluşturuldu ve schema klasörüne kaydedildi."
    )

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    zip_name = f"sigmom_backup_{ts}.zip"
    zip_path = BACKUP_DIR / zip_name

    print("[*] ZIP yedeği oluşturuluyor...")
    create_zip_backup(files, zip_path)

    print("[*] SHA256 log dosyasına yazılıyor...")
    log_hashes(files, zip_name)

    print(f"[✓] Backup tamamlandı: {_posix(str(zip_path))}")


if __name__ == "__main__":
    run_zip_backup()
