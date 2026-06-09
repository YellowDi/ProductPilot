"""Build the ProductPilot desktop app with PyInstaller."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


APP_NAME = "ProductPilot"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINT = PROJECT_ROOT / "product_pilot" / "desktop" / "main.py"
RELEASE_ROOT = PROJECT_ROOT / "release"
BUILD_ROOT = PROJECT_ROOT / "build" / "pyinstaller"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tag = platform_tag()
    dist_dir = args.dist_dir or RELEASE_ROOT / tag
    work_dir = BUILD_ROOT / tag
    spec_dir = BUILD_ROOT / "specs"

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        APP_NAME,
        "--paths",
        str(PROJECT_ROOT),
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
        "--collect-all",
        "playwright",
        str(ENTRY_POINT),
    ]
    env = os.environ.copy()
    env.setdefault("PYINSTALLER_CONFIG_DIR", str(BUILD_ROOT / "config"))
    subprocess.run(command, cwd=PROJECT_ROOT, check=True, env=env)

    app_path = packaged_app_path(dist_dir)
    print(f"Built: {app_path}")
    if args.archive:
        archive_path = archive_app(app_path, tag)
        print(f"Archive: {archive_path}")
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dist-dir",
        type=Path,
        help="Output directory. Defaults to release/<platform>-<arch>.",
    )
    parser.add_argument(
        "--no-archive",
        action="store_false",
        dest="archive",
        help="Skip creating a zip archive next to release outputs.",
    )
    parser.set_defaults(archive=True)
    return parser.parse_args(argv)


def platform_tag() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch_aliases = {
        "amd64": "x64",
        "x86_64": "x64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    return f"{system}-{arch_aliases.get(machine, machine)}"


def packaged_app_path(dist_dir: Path) -> Path:
    if platform.system() == "Darwin":
        return dist_dir / f"{APP_NAME}.app"
    if platform.system() == "Windows":
        return dist_dir / APP_NAME / f"{APP_NAME}.exe"
    return dist_dir / APP_NAME / APP_NAME


def archive_app(app_path: Path, platform_name: str) -> Path:
    archive_path = RELEASE_ROOT / f"{APP_NAME}-{platform_name}.zip"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        archive_path.unlink()

    if platform.system() == "Darwin" and shutil.which("ditto"):
        subprocess.run(
            [
                "ditto",
                "-c",
                "-k",
                "--sequesterRsrc",
                "--keepParent",
                str(app_path),
                str(archive_path),
            ],
            check=True,
        )
        return archive_path

    shutil.make_archive(
        str(archive_path.with_suffix("")),
        "zip",
        root_dir=app_path.parent,
        base_dir=app_path.name,
    )
    return archive_path


if __name__ == "__main__":
    raise SystemExit(main())
