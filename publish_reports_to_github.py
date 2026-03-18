from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


# =====================================
# PFADE ANPASSEN
# =====================================

BASE_DIR = Path.home() / "Documents" / "TSI Listen"

# Quellordner deiner fertigen Reports
NASDAQ_SOURCE_DIR = BASE_DIR / "HTML_Report"
SP500_SOURCE_DIR = BASE_DIR / "SP500" / "HTML_Report"
HDAX_SOURCE_DIR = BASE_DIR / "Hdax" / "HTML_Report"

# Lokaler geklonter GitHub-Repo-Ordner deiner Website
GITHUB_REPO_DIR = Path.home() / "Documents" / "tsi-report"

# Archivordner innerhalb des GitHub-Repos
ARCHIVE_DIR = GITHUB_REPO_DIR / "_archive"


# =====================================
# REPORT-KONFIGURATION
# =====================================

REPORTS = [
    {
        "label": "Nasdaq 100",
        "source_dir": NASDAQ_SOURCE_DIR,
        "source_pattern": "TSI_AllInOne_KW*_REPORT.html",
        "target_name": "ndq100.html",
        "archive_prefix": "ndq100",
    },
    {
        "label": "S&P 500",
        "source_dir": SP500_SOURCE_DIR,
        "source_pattern": "TSI_AllInOne_KW*_REPORT.html",
        "target_name": "sp500.html",
        "archive_prefix": "sp500",
    },
    {
        "label": "HDAX",
        "source_dir": HDAX_SOURCE_DIR,
        "source_pattern": "TSI_AllInOne_KW*_REPORT.html",
        "target_name": "hdax.html",
        "archive_prefix": "hdax",
    },
]


# =====================================
# HELPERS
# =====================================

def _run_git_command(args: list[str], repo_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=repo_dir,
        check=False,
        capture_output=True,
        text=True,
    )


def _ensure_repo_ready(repo_dir: Path) -> None:
    if not repo_dir.exists():
        raise RuntimeError(f"GitHub-Repo-Ordner nicht gefunden: {repo_dir}")
    if not (repo_dir / ".git").exists():
        raise RuntimeError(f"Kein Git-Repo gefunden unter: {repo_dir}")


def _extract_week_from_filename(filename: str) -> int | None:
    match = re.search(r"KW[_ ]?(\d+)", filename, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _find_latest_file(folder: Path, pattern: str) -> Path | None:
    files = [p for p in folder.glob(pattern) if p.is_file()]
    if not files:
        return None

    def sort_key(p: Path) -> tuple[int, float]:
        week = _extract_week_from_filename(p.name)
        return (week if week is not None else -1, p.stat().st_mtime)

    return max(files, key=sort_key)


def _archive_existing_target(target_file: Path, archive_prefix: str, new_report_week: int | None) -> Path | None:
    if not target_file.exists() or not target_file.is_file():
        return None

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    if new_report_week is not None:
        archive_week = 52 if new_report_week <= 1 else new_report_week - 1
        archive_name = f"{archive_prefix}_KW_{archive_week}.html"
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"{archive_prefix}_{timestamp}.html"

    archive_path = ARCHIVE_DIR / archive_name

    if archive_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = ARCHIVE_DIR / f"{archive_path.stem}_{timestamp}{archive_path.suffix}"

    shutil.copy2(target_file, archive_path)
    return archive_path


def _copy_report(source_file: Path, target_file: Path) -> None:
    target_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_file, target_file)


def _git_commit_and_push(repo_dir: Path, changed_paths: list[str], commit_message: str) -> None:
    add_result = _run_git_command(["git", "add", *changed_paths], repo_dir)
    if add_result.returncode != 0:
        raise RuntimeError(f"git add fehlgeschlagen:\n{add_result.stderr}")

    status_result = _run_git_command(["git", "status", "--porcelain"], repo_dir)
    if status_result.returncode != 0:
        raise RuntimeError(f"git status fehlgeschlagen:\n{status_result.stderr}")

    if not status_result.stdout.strip():
        print("Keine Git-Änderungen erkannt. Kein Commit/Push nötig.")
        return

    commit_result = _run_git_command(["git", "commit", "-m", commit_message], repo_dir)
    if commit_result.returncode != 0:
        raise RuntimeError(f"git commit fehlgeschlagen:\n{commit_result.stderr}")

    push_result = _run_git_command(["git", "push"], repo_dir)
    if push_result.returncode != 0:
        stderr_lower = (push_result.stderr or "").lower()

        if "fetch first" in stderr_lower or "failed to push some refs" in stderr_lower:
            pull_result = _run_git_command(["git", "pull", "--rebase", "origin", "main"], repo_dir)
            if pull_result.returncode != 0:
                raise RuntimeError(f"git pull --rebase fehlgeschlagen:\n{pull_result.stderr}")

            push_result = _run_git_command(["git", "push"], repo_dir)

        if push_result.returncode != 0:
            raise RuntimeError(f"git push fehlgeschlagen:\n{push_result.stderr}")

    print("GitHub-Push erfolgreich.")
    if commit_result.stdout.strip():
        print(commit_result.stdout.strip())
    if push_result.stdout.strip():
        print(push_result.stdout.strip())


def _build_commit_message(source_reports: list[Path]) -> str:
    weeks = []
    for p in source_reports:
        week = _extract_week_from_filename(p.name)
        if week is not None:
            weeks.append(week)

    if weeks:
        week_label = f"KW {max(weeks)}"
    else:
        week_label = datetime.now().strftime("%Y-%m-%d")

    return f"Update HTML reports {week_label}"


# =====================================
# MAIN LOGIK
# =====================================

def publish_reports() -> None:
    _ensure_repo_ready(GITHUB_REPO_DIR)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    changed_paths: list[str] = []
    used_source_reports: list[Path] = []

    print(f"GitHub-Repo: {GITHUB_REPO_DIR}")
    print()

    for report_cfg in REPORTS:
        label = report_cfg["label"]
        source_dir = report_cfg["source_dir"]
        source_pattern = report_cfg["source_pattern"]
        target_name = report_cfg["target_name"]
        archive_prefix = report_cfg["archive_prefix"]

        source_file = _find_latest_file(source_dir, source_pattern)

        if source_file is None:
            print(f"Übersprungen: keine Quelldatei gefunden für {label} in {source_dir}")
            print()
            continue

        target_file = GITHUB_REPO_DIR / target_name
        source_week = _extract_week_from_filename(source_file.name)

        archived_file = _archive_existing_target(
            target_file=target_file,
            archive_prefix=archive_prefix,
            new_report_week=source_week,
        )

        _copy_report(source_file, target_file)

        print(f"{label}:")
        print(f"  Quelle:      {source_file}")
        print(f"  Ziel:        {target_file}")

        if archived_file is not None:
            print(f"  Archiviert:  {archived_file}")

        changed_paths.append(target_name)
        used_source_reports.append(source_file)

        if archived_file is not None:
            changed_paths.append(f"{ARCHIVE_DIR.name}/{archived_file.name}")

        print()

    if not changed_paths:
        print("Keine Reports gefunden. Nichts zu tun.")
        return

    commit_message = _build_commit_message(used_source_reports)
    _git_commit_and_push(
        repo_dir=GITHUB_REPO_DIR,
        changed_paths=changed_paths,
        commit_message=commit_message,
    )


def main() -> None:
    publish_reports()


if __name__ == "__main__":
    main()