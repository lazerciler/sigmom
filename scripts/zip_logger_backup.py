#!/usr/bin/env python3
# scripts/zip_logger_backup.py

import os
import hashlib
import zipfile
from datetime import datetime

# === Proje Dizini Dinamiği ===
# Projenin kök dizinini script'in bulunduğu klasör referans alınarak tespit et
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# === Ayarlar ===
BACKUP_DIR = os.path.join(PROJECT_ROOT, "backups")
SCHEMA_DIR = os.path.join(PROJECT_ROOT, "schema")
SKELETON_PATH = os.path.join(SCHEMA_DIR, "project_skeleton.txt")
HASH_LOG = os.path.join(BACKUP_DIR, "hash_log.txt")

# Yedeklenecek dosya uzantıları
INCLUDE_EXTENSIONS = {".py", ".sql", ".txt", ".md", ".example", ".ini", ".mako"}
# Yedeklenmeyecek klasörler
EXCLUDE_DIRS = {
    "__pycache__",
    ".git",
    ".idea",
    "scripts",
    "venv",
    os.path.basename(BACKUP_DIR),
}
# Yedeklenmeyecek dosyalar
EXCLUDE_FILES = {".DS_Store", ".env"}


# === Yardımcı Fonksiyonlar ===
def get_file_hash(filepath: str) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def gather_project_files() -> list:
    """
    Proje kök dizinindeki dosyaları toplar.
    - EXCLUDE_DIRS içinde tanımlı klasörleri ve EXCLUDE_FILES içindeki dosyaları yoksayar.
    - Gizli dosyalar (dosya adı '.' ile başlayan ve uzantısı olmayan) dahil edilir.
    - INCLUDE_EXTENSIONS içinde listelenen uzantılara sahip dosyalar dahil edilir.
    """
    file_list = []
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            if file in EXCLUDE_FILES:
                continue
            full_path = os.path.join(root, file)
            name, ext = os.path.splitext(file)
            # Gizli dosyalar (uzantısız) dahil edin
            if file.startswith(".") and ext == "":
                file_list.append(full_path)
                continue
            # İzin verilen uzantılar
            if ext.lower() in INCLUDE_EXTENSIONS:
                file_list.append(full_path)
    return file_list


def create_zip_backup(files: list, zip_path: str):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in files:
            arcname = os.path.relpath(file, PROJECT_ROOT)
            zipf.write(file, arcname=arcname)


def log_hashes(files: list, zip_name: str):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    with open(HASH_LOG, "a", encoding="utf-8") as logf:
        logf.write(
            f"\n=== Backup: {zip_name} | {datetime.utcnow().isoformat()} UTC ===\n"
        )
        for file in files:
            rel_path = os.path.relpath(file, PROJECT_ROOT)
            hash_val = get_file_hash(file)
            logf.write(f"{rel_path} : {hash_val}\n")


def generate_project_skeleton(output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    exclude_dirs = {
        "venv",
        "__pycache__",
        ".git",
        ".idea",
        os.path.basename(BACKUP_DIR),
    }
    exclude_patterns = ["-legacy", ".tmp", ".bak", "~$", ".log"]

    with open(output_path, "w", encoding="utf-8") as out:

        def _print_tree(startpath, prefix=""):
            entries = sorted(os.listdir(startpath))
            files = []
            dirs = []

            for entry in entries:
                full_path = os.path.join(startpath, entry)
                if os.path.isdir(full_path) and entry not in exclude_dirs:
                    dirs.append(entry)
                elif os.path.isfile(full_path) and not any(
                    pat in entry for pat in exclude_patterns
                ):
                    files.append(entry)

            for i, file in enumerate(files):
                connector = "└── " if (i == len(files) - 1 and not dirs) else "├── "
                out.write(prefix + connector + file + "\n")

            for i, dir in enumerate(dirs):
                connector = "└── " if i == len(dirs) - 1 else "├── "
                out.write(prefix + connector + dir + "/\n")
                new_prefix = prefix + ("    " if i == len(dirs) - 1 else "│   ")
                _print_tree(os.path.join(startpath, dir), new_prefix)

        out.write("./\n")
        _print_tree(PROJECT_ROOT)


def run_zip_backup():
    print("[*] Proje ağacı dosyası oluşturuluyor...")
    generate_project_skeleton(SKELETON_PATH)

    print("[*] Dosyalar toplanıyor...")
    files = gather_project_files()

    print(f"[+] {SKELETON_PATH} oluşturuldu ve schema klasörüne kaydedildi.")

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    zip_name = f"sigmom_backup_{timestamp}.zip"
    zip_path = os.path.join(BACKUP_DIR, zip_name)

    print("[*] ZIP yedeği oluşturuluyor...")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    create_zip_backup(files, zip_path)

    print("[*] SHA256 log dosyasına yazılıyor...")
    log_hashes(files, zip_name)

    print(f"[✓] Backup tamamlandı: {zip_path}")


if __name__ == "__main__":
    run_zip_backup()
