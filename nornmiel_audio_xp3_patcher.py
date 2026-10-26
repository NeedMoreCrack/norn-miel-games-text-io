#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch selected looping SEs and replay-exit audio in a KiriKiri XP3 archive."""

from __future__ import annotations

import codecs
import filecmp
import json
import os
import re
import shutil
import subprocess
import sys
import stat
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath


PACKER_NAMES = ("xp3-pack-unpack.exe", "pack-unpack.exe")
PACKER_REPOSITORY = "lxl66566/xp3-pack-unpack"
PACKER_ASSET_NAME = "xp3-pack-unpack-x86_64-pc-windows-msvc.zip"
PACKER_API_BASE = f"https://api.github.com/repos/{PACKER_REPOSITORY}"
TARGET_SE_NAMES = ("se904", "se905")
STOP_AUDIO_LINES = (
    "@stopse buf=0",
    "@stopse buf=1",
    "@stopse buf=2",
    '@eval exp="tf.isPlayVoice=false"',
)
STOP_PREVIOUS_VOICE_LINE = '@stopse buf=0 cond="!tf.isPlayVoice"'
PAUSE_REPLAY_AUDIO_LINE = (
    '@eval exp="tf.sceneAudioPaused0=kag.se[0].paused; '
    'tf.sceneAudioPaused1=kag.se[1].paused; '
    'tf.sceneAudioPaused2=kag.se[2].paused; '
    'kag.se[0].paused=true; kag.se[1].paused=true; kag.se[2].paused=true" '
    'cond="tf.scene_mode"'
)
RESUME_REPLAY_AUDIO_LINE = (
    '@eval exp="kag.se[0].paused=tf.sceneAudioPaused0; '
    'kag.se[1].paused=tf.sceneAudioPaused1; '
    'kag.se[2].paused=tf.sceneAudioPaused2" cond="tf.scene_mode"'
)

STORAGE_PATTERN = re.compile(
    r"\bstorage\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|([^\s\]]+))",
    re.IGNORECASE,
)
LOOP_PATTERN = re.compile(
    r"(\bloop\s*=\s*)(\"[^\"]*\"|'[^']*'|[^\s\]]+)",
    re.IGNORECASE,
)
ACTIVE_AUDIO_TAG_PATTERN = re.compile(r"^\s*(?:@|\[)\s*(SE|playse)\b", re.IGNORECASE)
SE_MACRO_PATTERN = re.compile(
    r"^\s*@macro\s+.*\bname\s*=\s*(?:\"SE\"|'SE'|SE)(?:\s|$)",
    re.IGNORECASE,
)
NAME_MACRO_PATTERN = re.compile(
    r"^\s*@macro\s+.*\bname\s*=\s*(?:\"name\"|'name'|name)(?:\s|$)",
    re.IGNORECASE,
)
END_MACRO_PATTERN = re.compile(r"^\s*@endmacro\b", re.IGNORECASE)
PLAYSE_PATTERN = re.compile(r"^\s*@playse\b", re.IGNORECASE)
STOP_VOICE_PATTERN = re.compile(
    r"^\s*@stopse\b.*\bbuf\s*=\s*(?:\"0\"|'0'|0)(?:\s|$)", re.IGNORECASE
)
RETURN_LABEL_PATTERN = re.compile(r"^\s*\*return\s*$", re.IGNORECASE)
OPTION_LABEL_PATTERN = re.compile(r"^\s*\*option\s*$", re.IGNORECASE)
RET_LABEL_PATTERN = re.compile(r"^\s*\*ret\s*$", re.IGNORECASE)
ANY_LABEL_PATTERN = re.compile(r"^\s*\*[^|\s]+", re.IGNORECASE)


class PatchError(Exception):
    """A user-correctable patching error."""


@dataclass(frozen=True)
class TextFile:
    text: str
    encoding: str
    bom: bytes


@dataclass(frozen=True)
class ScriptSet:
    root: Path
    scenario: Path
    macro: Path
    scene_mode: Path
    sub: Path


@dataclass(frozen=True)
class ScenarioResult:
    text: str
    counts: dict[str, int]
    changed: int
    macro_calls: int


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    while True:
        answer = input(prompt + suffix).strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes", "是"}:
            return True
        if answer in {"n", "no", "否"}:
            return False
        print("請輸入 y 或 n。")


def find_game_directory() -> Path:
    script_directory = Path(__file__).resolve().parent
    candidates = []
    for directory in (Path.cwd().resolve(), script_directory):
        if directory not in candidates:
            candidates.append(directory)

    for directory in candidates:
        # The packer can be installed automatically, so its absence must not
        # prevent detecting an otherwise valid game directory.
        if any(path.is_file() for path in directory.glob("*.xp3")):
            return directory

    print("目前資料夾與腳本資料夾都找不到 XP3。")
    entered = input("請輸入遊戲啟動目錄的完整路徑（直接 Enter 取消）：").strip().strip('"')
    if not entered:
        raise PatchError("操作已取消。")
    directory = Path(entered).expanduser().resolve()
    if not directory.is_dir():
        raise PatchError(f"資料夾不存在：{directory}")
    return directory


def find_packer(game_directory: Path) -> Path:
    for directory in dict.fromkeys(
            (game_directory.resolve(), Path.cwd().resolve(), Path(__file__).resolve().parent)
    ):
        for name in PACKER_NAMES:
            path = directory / name
            if path.is_file():
                return path
    print("找不到打包器，將自動下載 Windows x64 版本。")
    return download_packer(Path.cwd().resolve())


def github_json(url: str) -> object:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "NornMiel-Audio-Patch", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def asset_in_release(release: object) -> dict | None:
    if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
        return None
    for asset in release.get("assets", []):
        if asset.get("name") == PACKER_ASSET_NAME and asset.get("state", "uploaded") == "uploaded":
            return {**asset, "release_tag": release.get("tag_name", "未知版本")}
    return None


def resolve_packer_asset() -> dict:
    # Prefer Latest; if it does not publish this asset, find the newest matching
    # published release in GitHub's release listing instead of guessing a tag.
    try:
        release = github_json(PACKER_API_BASE + "/releases/latest")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    else:
        asset = asset_in_release(release)
        if asset:
            return asset
    page = 1
    while True:
        releases = github_json(f"{PACKER_API_BASE}/releases?per_page=100&page={page}")
        if not isinstance(releases, list):
            raise PatchError("GitHub 回傳的 Release 清單格式不正確。")
        if not releases:
            break
        for release in releases:
            asset = asset_in_release(release)
            if asset:
                return asset
        if len(releases) < 100:
            break
        page += 1
    raise PatchError(f"此專案的正式 Release 中找不到附件：{PACKER_ASSET_NAME}")


def safe_zip_path(info: zipfile.ZipInfo) -> Path:
    normalized = info.filename.replace("\\", "/")
    member = PurePosixPath(normalized)
    if (member.is_absolute() or ".." in member.parts or ":" in normalized
            or stat.S_ISLNK(info.external_attr >> 16)):
        raise PatchError(f"ZIP 含有不允許的路徑：{info.filename}")
    return Path(*member.parts)


def install_packer_zip(zip_path: Path, destination: Path) -> Path:
    # Validate and extract into staging first. Do not overwrite an unrelated
    # README or another existing file in the user's current directory.
    destination = destination.resolve()
    with tempfile.TemporaryDirectory(prefix=".xp3_tool_extract_", dir=destination) as staging_name:
        staging = Path(staging_name)
        with zipfile.ZipFile(zip_path) as archive:
            files = []
            seen = set()
            for info in archive.infolist():
                relative = safe_zip_path(info)
                if info.is_dir():
                    continue
                key = relative.as_posix().casefold()
                if key in seen or not relative.name:
                    raise PatchError("ZIP 包含重複或無效的檔案路徑。")
                seen.add(key)
                target = destination / relative
                if destination not in target.resolve().parents or target.is_symlink():
                    raise PatchError(f"解壓縮路徑超出目前資料夾或為連結：{relative}")
                staged = staging / relative
                staged.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, staged.open("xb") as output:
                    shutil.copyfileobj(source, output)
                files.append(relative)
        executables = [r for r in files if r.name.lower() in PACKER_NAMES]
        if len(executables) != 1:
            raise PatchError("ZIP 中無法唯一找到 xp3-pack-unpack.exe 或 pack-unpack.exe。")
        if (staging / executables[0]).stat().st_size == 0:
            raise PatchError("ZIP 中的打包器是空檔案。")
        for relative in files:
            target = destination / relative
            if target.exists() and (not target.is_file() or not filecmp.cmp(staging / relative, target, shallow=False)):
                raise PatchError(f"解壓縮會覆蓋內容不同的既有檔案，已停止：{target}")
        for relative in files:
            target = destination / relative
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                with (staging / relative).open("rb") as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
        return destination / executables[0]


def download_packer(destination: Path) -> Path:
    destination = destination.resolve()
    zip_path = destination / PACKER_ASSET_NAME
    if zip_path.exists():
        raise PatchError(f"目前已有同名 ZIP，請先移走或重新命名後再執行：{zip_path}")
    partial = None
    try:
        print(f"正在查詢 GitHub Release：{PACKER_REPOSITORY}")
        asset = resolve_packer_asset()
        url = asset.get("browser_download_url", "")
        if not url.startswith(f"https://github.com/{PACKER_REPOSITORY}/releases/download/"):
            raise PatchError("GitHub 回傳了非預期的附件下載網址。")
        print(f"版本：{asset['release_tag']}")
        print(f"正在下載：{PACKER_ASSET_NAME}")
        print(f"下載與解壓縮目錄：{destination}")
        fd, temporary_name = tempfile.mkstemp(prefix=".xp3_tool_", suffix=".download", dir=destination)
        partial = Path(temporary_name)
        request = urllib.request.Request(url, headers={"User-Agent": "NornMiel-Audio-Patch"})
        with os.fdopen(fd, "wb") as output:
            with urllib.request.urlopen(request, timeout=60) as response:
                shutil.copyfileobj(response, output)
            output.flush()
            os.fsync(output.fileno())
        expected = asset.get("size")
        if partial.stat().st_size == 0 or (isinstance(expected, int) and partial.stat().st_size != expected):
            raise PatchError("附件下載不完整，檔案大小與 GitHub 資訊不符。")
        # Exclusive copy avoids overwriting a ZIP created by another process.
        try:
            with partial.open("rb") as source, zip_path.open("xb") as output:
                shutil.copyfileobj(source, output)
        except FileExistsError as exc:
            raise PatchError(f"同名 ZIP 已出現，請勿同時啟動多支程式：{zip_path}") from exc
        print("下載完成，正在解壓縮……")
        packer = install_packer_zip(zip_path, destination)
        zip_path.unlink()
        print(f"解壓縮完成：{packer}")
        print(f"已刪除下載的 ZIP：{PACKER_ASSET_NAME}")
        return packer
    except urllib.error.HTTPError as exc:
        raise PatchError(f"GitHub 下載失敗：HTTP {exc.code}。請檢查連線或 API 用量限制後重試。") from exc
    except urllib.error.URLError as exc:
        raise PatchError(f"無法連線至 GitHub：{exc.reason}") from exc
    except (zipfile.BadZipFile, RuntimeError, ValueError) as exc:
        raise PatchError(f"無法解壓縮下載附件：{exc}；若 ZIP 已下載，會保留供檢查。") from exc
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)


def choose_archive(game_directory: Path) -> Path:
    archives = sorted(
        (path for path in game_directory.glob("*.xp3") if path.is_file()),
        key=lambda path: path.name.lower(),
    )
    if not archives:
        raise PatchError("遊戲啟動目錄中找不到 .xp3 檔案。")

    preferred = game_directory / "data.xp3"
    if preferred in archives:
        print(f"自動選擇：{preferred.name}")
        return preferred
    if len(archives) == 1:
        print(f"自動選擇：{archives[0].name}")
        return archives[0]

    print("找到多個 XP3，請選擇要修改的檔案：")
    for index, archive in enumerate(archives, start=1):
        print(f"{index}. {archive.name}（{format_size(archive.stat().st_size)}）")
    while True:
        answer = input("請輸入編號（直接 Enter 取消）：").strip()
        if not answer:
            raise PatchError("操作已取消。")
        try:
            return archives[int(answer) - 1]
        except (ValueError, IndexError):
            print("請輸入有效的編號。")


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def decode_script(path: Path) -> TextFile:
    data = path.read_bytes()
    if data.startswith(codecs.BOM_UTF16_LE):
        return TextFile(data[2:].decode("utf-16-le"), "utf-16-le", codecs.BOM_UTF16_LE)
    if data.startswith(codecs.BOM_UTF16_BE):
        return TextFile(data[2:].decode("utf-16-be"), "utf-16-be", codecs.BOM_UTF16_BE)
    if data.startswith(codecs.BOM_UTF8):
        return TextFile(data[3:].decode("utf-8"), "utf-8", codecs.BOM_UTF8)
    try:
        return TextFile(data.decode("utf-8"), "utf-8", b"")
    except UnicodeDecodeError:
        pass
    try:
        return TextFile(data.decode("cp932"), "cp932", b"")
    except UnicodeDecodeError as exc:
        raise PatchError(f"無法判斷腳本編碼：{path}") from exc


def encode_script(document: TextFile, text: str) -> bytes:
    try:
        return document.bom + text.encode(document.encoding)
    except UnicodeEncodeError as exc:
        raise PatchError(f"無法使用原始編碼 {document.encoding} 寫回腳本。") from exc


def write_bytes_atomic(path: Path, data: bytes) -> None:
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=path.name + ".",
                suffix=".tmp",
                dir=path.parent,
                delete=False,
        ) as stream:
            temporary_name = stream.name
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def split_line_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith(("\n", "\r")):
        return line[:-1], line[-1]
    return line, ""


def storage_name(line: str) -> str | None:
    match = STORAGE_PATTERN.search(line)
    if not match:
        return None
    value = next(group for group in match.groups() if group is not None)
    normalized = value.replace("\\", "/").rsplit("/", 1)[-1]
    return normalized.rsplit(".", 1)[0].lower()


def quoted_value_like(old_value: str, new_value: str) -> str:
    if len(old_value) >= 2 and old_value[0] == old_value[-1] and old_value[0] in "\"'":
        return old_value[0] + new_value + old_value[-1]
    return new_value


def set_or_add_attribute(line: str, name_pattern: re.Pattern[str], value: str) -> tuple[str, bool]:
    core, ending = split_line_ending(line)
    match = name_pattern.search(core)
    if match:
        replacement_value = quoted_value_like(match.group(2), value)
        replacement = match.group(1) + replacement_value
        updated = core[: match.start()] + replacement + core[match.end() :]
        return updated + ending, updated != core

    closing_bracket = core.rfind("]") if core.lstrip().startswith("[") else -1
    if closing_bracket >= 0:
        updated = core[:closing_bracket].rstrip() + f" loop={value}" + core[closing_bracket:]
    else:
        updated = core.rstrip() + f" loop={value}"
    return updated + ending, True


def patch_scenario_text(text: str) -> ScenarioResult:
    lines = text.splitlines(keepends=True)
    counts = {name: 0 for name in TARGET_SE_NAMES}
    changed = 0
    macro_calls = 0

    for index, line in enumerate(lines):
        core, _ = split_line_ending(line)
        if core.lstrip().startswith(";"):
            continue
        tag_match = ACTIVE_AUDIO_TAG_PATTERN.match(core)
        if not tag_match:
            continue
        name = storage_name(core)
        if name not in counts:
            continue
        counts[name] += 1
        if tag_match.group(1).lower() == "se":
            macro_calls += 1
        updated, was_changed = set_or_add_attribute(line, LOOP_PATTERN, "true")
        if was_changed:
            lines[index] = updated
            changed += 1

    missing = [name for name, count in counts.items() if count == 0]
    if missing:
        raise PatchError("scenario.ks 找不到目標音效：" + ", ".join(missing))
    return ScenarioResult("".join(lines), counts, changed, macro_calls)


def patch_macro_text(text: str, required: bool) -> tuple[str, bool]:
    lines = text.splitlines(keepends=True)
    macro_starts = [
        index for index, line in enumerate(lines) if SE_MACRO_PATTERN.match(split_line_ending(line)[0])
    ]
    if not macro_starts:
        if required:
            raise PatchError('macro.ks 找不到 @macro name="SE"。')
        return text, False
    if len(macro_starts) != 1:
        raise PatchError('macro.ks 找到多個名為 "SE" 的巨集，為避免改錯已停止。')

    start = macro_starts[0]
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if END_MACRO_PATTERN.match(split_line_ending(lines[index])[0])
        ),
        None,
    )
    if end is None:
        raise PatchError('macro.ks 的 "SE" 巨集缺少 @endmacro。')

    playse_lines = [
        index
        for index in range(start + 1, end)
        if PLAYSE_PATTERN.match(split_line_ending(lines[index])[0])
    ]
    if len(playse_lines) != 1:
        raise PatchError('macro.ks 的 "SE" 巨集中無法唯一確定 @playse 指令。')

    index = playse_lines[0]
    updated, changed = set_or_add_attribute(lines[index], LOOP_PATTERN, "%loop|false")
    if changed:
        lines[index] = updated
    return "".join(lines), changed


def patch_name_voice_stop_text(text: str) -> tuple[str, bool]:
    lines = text.splitlines(keepends=True)
    macro_starts = [
        index
        for index, line in enumerate(lines)
        if NAME_MACRO_PATTERN.match(split_line_ending(line)[0])
    ]
    if len(macro_starts) != 1:
        raise PatchError(
            f'macro.ks 預期只有一個名為 "name" 的巨集，實際找到 {len(macro_starts)} 個。'
        )

    start = macro_starts[0]
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if END_MACRO_PATTERN.match(split_line_ending(lines[index])[0])
        ),
        None,
    )
    if end is None:
        raise PatchError('macro.ks 的 "name" 巨集缺少 @endmacro。')
    stop_lines = [
        index
        for index in range(start + 1, end)
        if STOP_VOICE_PATTERN.match(split_line_ending(lines[index])[0])
    ]
    if len(stop_lines) > 1:
        raise PatchError('macro.ks 的 "name" 巨集中找到多個 buf=0 停止指令。')
    if stop_lines:
        index = stop_lines[0]
        core, ending = split_line_ending(lines[index])
        if core.strip() == STOP_PREVIOUS_VOICE_LINE:
            return text, False
        # Upgrade the earlier unconditional patch, which stopped a newly started @PV.
        indentation = core[: len(core) - len(core.lstrip())]
        lines[index] = indentation + STOP_PREVIOUS_VOICE_LINE + ending
        return "".join(lines), True

    _, ending = split_line_ending(lines[start])
    lines.insert(start + 1, STOP_PREVIOUS_VOICE_LINE + (ending or "\r\n"))
    return "".join(lines), True


def patch_scene_mode_text(text: str) -> tuple[str, int]:
    lines = text.splitlines(keepends=True)
    labels = [
        index
        for index, line in enumerate(lines)
        if RETURN_LABEL_PATTERN.match(split_line_ending(line)[0])
    ]
    if len(labels) != 1:
        raise PatchError(
            f"scenemode.ks 預期只有一個 *return，實際找到 {len(labels)} 個。"
        )

    label_index = labels[0]
    _, label_ending = split_line_ending(lines[label_index])
    ending = label_ending or "\r\n"
    window_end = min(label_index + 16, len(lines))
    existing_window = {
        split_line_ending(line)[0].strip().lower() for line in lines[label_index + 1 : window_end]
    }
    missing = [line for line in STOP_AUDIO_LINES if line.lower() not in existing_window]
    if missing:
        lines[label_index + 1 : label_index + 1] = [line + ending for line in missing]
    return "".join(lines), len(missing)


def patch_sub_text(text: str) -> tuple[str, bool, bool]:
    lines = text.splitlines(keepends=True)

    option_labels = [
        index
        for index, line in enumerate(lines)
        if OPTION_LABEL_PATTERN.match(split_line_ending(line)[0])
    ]
    if len(option_labels) != 1:
        raise PatchError(
            f"sub.ks 預期只有一個 *option，實際找到 {len(option_labels)} 個。"
        )
    option_index = option_labels[0]
    next_label = next(
        (
            index
            for index in range(option_index + 1, len(lines))
            if ANY_LABEL_PATTERN.match(split_line_ending(lines[index])[0])
        ),
        len(lines),
    )
    pause_exists = any(
        split_line_ending(line)[0].strip() == PAUSE_REPLAY_AUDIO_LINE
        for line in lines[option_index + 1 : next_label]
    )
    pause_inserted = not pause_exists
    if pause_inserted:
        _, ending = split_line_ending(lines[option_index])
        lines.insert(option_index + 1, PAUSE_REPLAY_AUDIO_LINE + (ending or "\r\n"))

    # Recalculate positions because inserting the pause line shifts later labels.
    ret_labels = [
        index
        for index, line in enumerate(lines)
        if RET_LABEL_PATTERN.match(split_line_ending(line)[0])
    ]
    if len(ret_labels) != 1:
        raise PatchError(f"sub.ks 預期只有一個 *ret，實際找到 {len(ret_labels)} 個。")
    ret_index = ret_labels[0]
    ret_end = next(
        (
            index
            for index in range(ret_index + 1, len(lines))
            if ANY_LABEL_PATTERN.match(split_line_ending(lines[index])[0])
        ),
        len(lines),
    )
    resume_exists = any(
        split_line_ending(line)[0].strip() == RESUME_REPLAY_AUDIO_LINE
        for line in lines[ret_index + 1 : ret_end]
    )
    resume_inserted = not resume_exists
    if resume_inserted:
        return_lines = [
            index
            for index in range(ret_index + 1, ret_end)
            if re.match(r"^\s*@return\b", split_line_ending(lines[index])[0], re.IGNORECASE)
        ]
        if len(return_lines) != 1:
            raise PatchError(
                f"sub.ks 的 *ret 區段預期只有一個 @return，實際找到 {len(return_lines)} 個。"
            )
        return_index = return_lines[0]
        _, ending = split_line_ending(lines[return_index])
        lines.insert(return_index, RESUME_REPLAY_AUDIO_LINE + (ending or "\r\n"))

    return "".join(lines), pause_inserted, resume_inserted


def find_script_set(extracted_directory: Path) -> ScriptSet:
    matches: list[ScriptSet] = []
    for scenario in extracted_directory.rglob("scenario.ks"):
        directory = scenario.parent
        macro = directory / "macro.ks"
        scene_mode = directory / "scenemode.ks"
        sub = directory / "sub.ks"
        if macro.is_file() and scene_mode.is_file() and sub.is_file():
            matches.append(ScriptSet(directory.parent, scenario, macro, scene_mode, sub))

    if not matches:
        raise PatchError(
            "解包內容中找不到同時包含 scenario.ks、macro.ks、scenemode.ks、sub.ks 的 scenario 資料夾。"
        )
    if len(matches) != 1:
        locations = "\n".join(f"- {item.scenario.parent}" for item in matches)
        raise PatchError("找到多組候選腳本，為避免改錯已停止：\n" + locations)
    return matches[0]


def apply_script_patches(
        scripts: ScriptSet,
) -> tuple[ScenarioResult, bool, bool, int, bool, bool]:
    scenario_document = decode_script(scripts.scenario)
    macro_document = decode_script(scripts.macro)
    scene_document = decode_script(scripts.scene_mode)
    sub_document = decode_script(scripts.sub)

    scenario_result = patch_scenario_text(scenario_document.text)
    macro_text, macro_changed = patch_macro_text(
        macro_document.text, required=scenario_result.macro_calls > 0
    )
    macro_text, voice_stop_inserted = patch_name_voice_stop_text(macro_text)
    scene_text, scene_inserted = patch_scene_mode_text(scene_document.text)
    sub_text, pause_inserted, resume_inserted = patch_sub_text(sub_document.text)

    write_bytes_atomic(scripts.scenario, encode_script(scenario_document, scenario_result.text))
    write_bytes_atomic(scripts.macro, encode_script(macro_document, macro_text))
    write_bytes_atomic(scripts.scene_mode, encode_script(scene_document, scene_text))
    write_bytes_atomic(scripts.sub, encode_script(sub_document, sub_text))
    return (
        scenario_result,
        macro_changed,
        voice_stop_inserted,
        scene_inserted,
        pause_inserted,
        resume_inserted,
    )


def verify_script_patches(scripts: ScriptSet) -> ScenarioResult:
    scenario_document = decode_script(scripts.scenario)
    macro_document = decode_script(scripts.macro)
    scene_document = decode_script(scripts.scene_mode)
    sub_document = decode_script(scripts.sub)

    scenario_result = patch_scenario_text(scenario_document.text)
    macro_text, _ = patch_macro_text(
        macro_document.text, required=scenario_result.macro_calls > 0
    )
    macro_text, _ = patch_name_voice_stop_text(macro_text)
    scene_text, _ = patch_scene_mode_text(scene_document.text)
    sub_text, _, _ = patch_sub_text(sub_document.text)

    if scenario_result.text != scenario_document.text:
        raise PatchError("驗證失敗：scenario.ks 仍有未完成的循環音效修改。")
    if macro_text != macro_document.text:
        raise PatchError("驗證失敗：macro.ks 的 loop 或換句停止語音修改不完整。")
    if scene_text != scene_document.text:
        raise PatchError("驗證失敗：scenemode.ks 的停止音效指令不完整。")
    if sub_text != sub_document.text:
        raise PatchError("驗證失敗：sub.ks 的設定介面暫停／恢復音效修改不完整。")
    return scenario_result


def run_packer(command: list[str], working_directory: Path, description: str) -> None:
    print(f"\n{description}……")
    print("執行：" + subprocess.list2cmdline(command))
    try:
        result = subprocess.run(command, cwd=working_directory, check=False)
    except OSError as exc:
        raise PatchError(f"無法啟動打包器：{exc}") from exc
    if result.returncode != 0:
        raise PatchError(f"{description}失敗，程式結束代碼：{result.returncode}")


def next_backup_path(archive: Path) -> Path:
    first = archive.with_name(archive.name + ".bak")
    if not first.exists():
        return first
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = archive.with_name(f"{archive.name}.{stamp}.bak")
    number = 1
    while candidate.exists():
        candidate = archive.with_name(f"{archive.name}.{stamp}-{number}.bak")
        number += 1
    return candidate


def patch_archive(game_directory: Path, packer: Path, archive: Path) -> None:
    archive_size = archive.stat().st_size
    free_space = shutil.disk_usage(game_directory).free
    print("\n即將處理：")
    print(f"遊戲目錄：{game_directory}")
    print(f"打包器：{packer.name}")
    print(f"XP3：{archive.name}（{format_size(archive_size)}）")
    print(f"可用空間：{format_size(free_space)}")
    if free_space < archive_size * 3:
        print("警告：可用空間少於 XP3 大小的三倍，解包及驗證可能失敗。")
    if not ask_yes_no("是否開始自動解包、修改及重新封包？"):
        raise PatchError("操作已取消。")

    work_directory = Path(
        tempfile.mkdtemp(prefix=".nornmiel_audio_patch_", dir=game_directory)
    ).resolve()
    extracted = work_directory / "extracted"
    packed_archive = work_directory / (archive.stem + ".patched.xp3")
    verified_directory = work_directory / "verified"
    completed = False

    try:
        run_packer(
            [str(packer), "unpack", str(archive), str(extracted)],
            work_directory,
            "解包 XP3",
        )
        scripts = find_script_set(extracted)
        print(f"找到腳本目錄：{scripts.scenario.parent}")

        (
            scenario_result,
            macro_changed,
            voice_stop_inserted,
            scene_inserted,
            pause_inserted,
            resume_inserted,
        ) = apply_script_patches(scripts)
        counts = "、".join(
            f"{name}={scenario_result.counts[name]}" for name in TARGET_SE_NAMES
        )
        print(f"音效命中：{counts}")
        print(f"scenario.ks 實際修改：{scenario_result.changed} 行")
        print(f"macro.ks：{'已修改' if macro_changed else '原本已符合'}")
        print(
            "換到下一句停止人物語音："
            + ("已加入" if voice_stop_inserted else "原本已符合")
        )
        print(
            f"scenemode.ks："
            f"{'加入 ' + str(scene_inserted) + ' 行' if scene_inserted else '原本已符合'}"
        )
        print(
            "回想設定介面暫停／恢復音效："
            + (
                "已加入"
                if pause_inserted or resume_inserted
                else "原本已符合"
            )
        )
        verify_script_patches(scripts)

        run_packer(
            [str(packer), "pack", str(scripts.root), str(packed_archive)],
            work_directory,
            "重新封包 XP3",
        )
        if not packed_archive.is_file() or packed_archive.stat().st_size == 0:
            raise PatchError("打包器沒有產生有效的新 XP3。")
        print(f"新封包大小：{format_size(packed_archive.stat().st_size)}")

        if ask_yes_no("是否重新解開新封包進行完整驗證？", default=True):
            run_packer(
                [str(packer), "unpack", str(packed_archive), str(verified_directory)],
                work_directory,
                "驗證新 XP3",
            )
            verified_scripts = find_script_set(verified_directory)
            verified_result = verify_script_patches(verified_scripts)
            verified_counts = "、".join(
                f"{name}={verified_result.counts[name]}" for name in TARGET_SE_NAMES
            )
            print(f"完整驗證通過：{verified_counts}")

        backup = next_backup_path(archive)
        print(f"\n正在備份原始封包：{backup.name}")
        shutil.copy2(archive, backup)
        if backup.stat().st_size != archive_size:
            raise PatchError("備份檔大小不符，已停止替換原始 XP3。")

        os.replace(packed_archive, archive)
        completed = True
        print("\n處理完成")
        print(f"已更新：{archive}")
        print(f"原始備份：{backup}")
    finally:
        try:
            shutil.rmtree(work_directory)
        except OSError as exc:
            print(f"警告：無法清理工作目錄 {work_directory}：{exc}", file=sys.stderr)
        if not completed:
            print("原始 XP3 沒有被替換。", file=sys.stderr)


def main() -> int:
    print("NornMiel XP3 音效自動修補工具")
    print("目標：se904、se905 循環；換句停止語音；回想設定介面暫停音效；離開回想停止音效")
    game_directory = find_game_directory()
    packer = find_packer(game_directory)
    archive = choose_archive(game_directory)
    patch_archive(game_directory, packer, archive)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PatchError, OSError) as exc:
        print(f"\n錯誤：{exc}", file=sys.stderr)
        raise SystemExit(1)
