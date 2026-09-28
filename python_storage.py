"""Local data location and verified, non-destructive directory migration."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


CONFIG_NAME = "storage_config.json"


def _local_path(path: Path) -> Path:
    resolved = Path(path).resolve()
    if os.name == "nt":
        if str(resolved).startswith("\\\\"):
            raise ValueError("数据位置只能选择本地磁盘或U盘，不能使用网络共享。")
        root = Path(resolved.anchor)
        if ctypes.windll.kernel32.GetDriveTypeW(str(root)) == 4:
            raise ValueError("数据位置不能使用映射的网络驱动器。")
    return resolved


def configured_directory(program_directory: Path) -> Path:
    base = _local_path(program_directory)
    config = base / CONFIG_NAME
    if not config.exists():
        return base / "data"
    try:
        record = json.loads(config.read_text(encoding="utf-8-sig"))
        if record.get("Version") != 1 or not isinstance(record.get("DataDirectory"), str):
            raise ValueError("保存位置配置格式不正确。")
        raw = Path(record["DataDirectory"])
        if not record["DataDirectory"].strip():
            raise ValueError("保存位置为空。")
        chosen = _local_path(raw if raw.is_absolute() else base / raw)
        if not chosen.is_dir() or not any((chosen / name).is_file() for name in ("data_python.json", "data.json")):
            raise FileNotFoundError(f"指定的数据目录不存在或缺少数据文件：{chosen}")
        return chosen
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise RuntimeError(f"无法读取指定的数据保存位置。原始数据不会被替换。\n{exc}") from exc


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _files(directory: Path) -> list[Path]:
    entries = list(directory.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise ValueError("数据目录包含链接文件或链接文件夹，不能作为本地数据迁移。")
    return sorted(path.relative_to(directory) for path in entries if path.is_file())


def _write_config(config: Path, value: str) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False,
                                         dir=config.parent, prefix="storage-", suffix=".tmp") as stream:
            temporary = Path(stream.name)
            json.dump({"Version": 1, "DataDirectory": value}, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, config)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def migrate_directory(program_directory: Path, source: Path, destination: Path) -> Path:
    """Copy, verify, then select a new empty directory. The source is retained."""
    base, source, destination = map(_local_path, (program_directory, source, destination))
    if not source.is_dir() or not (source / "data_python.json").is_file():
        raise ValueError("当前数据尚未保存，或数据目录不存在。")
    if destination == source or destination in source.parents or source in destination.parents:
        raise ValueError("新位置不能是当前数据目录或其上级、下级目录。")
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError("请选择一个空文件夹，避免覆盖已有数据。")
    config = base / CONFIG_NAME
    previous_config = config.read_bytes() if config.exists() else None
    expected = _files(source)
    if not destination.exists():
        destination.mkdir(parents=True)
    shutil.copytree(source, destination, dirs_exist_ok=True)
    if expected != _files(destination) or any(_digest(source / name) != _digest(destination / name) for name in expected):
        raise IOError("新位置的文件校验失败，原数据和原保存位置仍然有效。")
    # Load the copied data before making it the active location.
    import python_core
    python_core.DataStore(destination)
    try:
        value = str(destination.relative_to(base)) if destination.is_relative_to(base) else str(destination)
        _write_config(config, value)
    except Exception:
        if previous_config is None:
            config.unlink(missing_ok=True)
        else:
            config.write_bytes(previous_config)
        raise
    return destination
