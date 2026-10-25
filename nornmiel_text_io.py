#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract and apply KiriKiri/KAG scenario translations through TSV files."""

from __future__ import annotations

import codecs
import csv
import hashlib
import os
import re
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path


SCENARIO_FILENAME = "scenario.ks"
TSV_PATTERN = re.compile(r"^Translation-(\d+)\.tsv$", re.IGNORECASE)
NAME_PATTERN = re.compile(r'^\s*@name\b.*?\bchara\s*=\s*"([^"]*)"', re.IGNORECASE)
INLINE_TAG_PATTERN = re.compile(r"\[[^\]\r\n]*\]")
LEADING_SPACE_PATTERN = re.compile(r"^[ \t\u3000]*")
BATCH_SIZE = 50
FIELDNAMES = (
    "id",
    "line_no",
    "speaker",
    "source_text",
    "translated_text",
    "source_hash",
)


class TranslationError(Exception):
    """An expected, user-correctable translation data error."""


def detect_and_decode(path: Path) -> tuple[str, str]:
    """Decode a script and return (text, detected encoding label)."""
    data = path.read_bytes()

    if data.startswith(codecs.BOM_UTF16_LE):
        return data[len(codecs.BOM_UTF16_LE) :].decode("utf-16-le"), "UTF-16 LE BOM"
    if data.startswith(codecs.BOM_UTF16_BE):
        return data[len(codecs.BOM_UTF16_BE) :].decode("utf-16-be"), "UTF-16 BE BOM"
    if data.startswith(codecs.BOM_UTF8):
        return data.decode("utf-8-sig"), "UTF-8 BOM"

    try:
        return data.decode("utf-8"), "UTF-8（無 BOM）"
    except UnicodeDecodeError:
        pass

    try:
        return data.decode("cp932"), "CP932 / Shift-JIS"
    except UnicodeDecodeError as exc:
        raise TranslationError(
            f"無法判斷 {path.name} 的編碼；支援 UTF-16、UTF-8 與 CP932。"
        ) from exc


def content_without_line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return line[:-2]
    if line.endswith(("\r", "\n")):
        return line[:-1]
    return line


def line_ending_of(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    if line.endswith("\r"):
        return "\r"
    return ""


def source_hash(line_no: int, speaker: str, source_text: str) -> str:
    payload = f"{line_no}\0{speaker}\0{source_text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def translation_files(directory: Path) -> list[Path]:
    matches: list[tuple[int, Path]] = []
    for path in directory.iterdir():
        match = TSV_PATTERN.match(path.name) if path.is_file() else None
        if match:
            matches.append((int(match.group(1)), path))
    return [path for _, path in sorted(matches, key=lambda item: (item[0], item[1].name))]


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


def resolve_scenario(directory: Path) -> Path:
    scenario = directory / SCENARIO_FILENAME
    if scenario.is_file():
        return scenario

    print(f"目前資料夾找不到 {SCENARIO_FILENAME}：{directory}")
    entered = input("請輸入 scenario.ks 的完整路徑（直接 Enter 取消）：").strip().strip('"')
    if not entered:
        raise TranslationError("操作已取消。")
    scenario = Path(entered).expanduser()
    if not scenario.is_file():
        raise TranslationError(f"檔案不存在：{scenario}")
    return scenario.resolve()


def extract_records(scenario: Path) -> tuple[list[dict[str, str]], str]:
    text, encoding = detect_and_decode(scenario)
    lines = text.splitlines(keepends=True)
    records: list[dict[str, str]] = []

    for index, line in enumerate(lines):
        match = NAME_PATTERN.match(content_without_line_ending(line))
        if not match:
            continue
        if index + 1 >= len(lines):
            raise TranslationError(f"第 {index + 1} 行的 @name 後面沒有文本行。")

        line_no = index + 2  # index is zero-based; the extracted line is the next line.
        speaker = match.group(1)
        source = content_without_line_ending(lines[index + 1])
        records.append(
            {
                "id": f"T{len(records) + 1:06d}",
                "line_no": str(line_no),
                "speaker": speaker,
                "source_text": source,
                "translated_text": "",
                "source_hash": source_hash(line_no, speaker, source),
            }
        )

    if not records:
        raise TranslationError("沒有找到任何 @name 及其下一行文本。")
    return records, encoding


def write_translation_batches(records: list[dict[str, str]], directory: Path) -> int:
    existing = translation_files(directory)
    if existing:
        print(f"找到 {len(existing)} 個既有的 Translation-*.tsv。")
        if not ask_yes_no("重新提取會覆蓋這批 TSV，是否繼續？"):
            raise TranslationError("操作已取消，沒有變更任何 TSV。")
        for path in existing:
            path.unlink()

    file_count = 0
    for offset in range(0, len(records), BATCH_SIZE):
        file_count += 1
        output = directory / f"Translation-{file_count:03d}.tsv"
        with output.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=FIELDNAMES,
                delimiter="\t",
                lineterminator="\n",
                quoting=csv.QUOTE_MINIMAL,
            )
            writer.writeheader()
            writer.writerows(records[offset : offset + BATCH_SIZE])
    return file_count


def extract_mode(scenario: Path) -> None:
    records, encoding = extract_records(scenario)
    count = write_translation_batches(records, scenario.parent)
    print("\n提取完成")
    print(f"來源：{scenario}")
    print(f"偵測編碼：{encoding}")
    print(f"文本數量：{len(records)}")
    print(f"TSV 數量：{count}（每個最多 {BATCH_SIZE} 筆）")
    print("TSV 編碼：UTF-8 BOM")


def load_translation_rows(directory: Path) -> tuple[list[dict[str, str]], list[Path]]:
    files = translation_files(directory)
    if not files:
        raise TranslationError(f"{directory} 中找不到 Translation-*.tsv。")

    rows: list[dict[str, str]] = []
    for path in files:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream, delimiter="\t")
                missing = [name for name in FIELDNAMES if name not in (reader.fieldnames or [])]
                if missing:
                    raise TranslationError(
                        f"{path.name} 缺少欄位：{', '.join(missing)}"
                    )
                for row_index, row in enumerate(reader, start=2):
                    row["_file"] = path.name
                    row["_row"] = str(row_index)
                    rows.append(row)
        except UnicodeDecodeError as exc:
            raise TranslationError(f"{path.name} 不是有效的 UTF-8 TSV。") from exc
    return rows, files


def format_row_location(row: dict[str, str]) -> str:
    return f"{row.get('_file', '?')} 第 {row.get('_row', '?')} 列"


def prepare_replacements(
    rows: list[dict[str, str]], lines: list[str]
) -> tuple[dict[int, str], int, list[str]]:
    replacements: dict[int, str] = {}
    skipped = 0
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_lines: set[int] = set()

    for row in rows:
        location = format_row_location(row)
        record_id = (row.get("id") or "").strip()
        if not record_id:
            errors.append(f"{location}：id 為空。")
        elif record_id in seen_ids:
            errors.append(f"{location}：id {record_id} 重複。")
        else:
            seen_ids.add(record_id)

        try:
            line_no = int((row.get("line_no") or "").strip())
        except ValueError:
            errors.append(f"{location}：line_no 不是整數。")
            continue

        if line_no in seen_lines:
            errors.append(f"{location}：scenario.ks 第 {line_no} 行被重複指定。")
            continue
        seen_lines.add(line_no)

        if not 1 <= line_no <= len(lines):
            errors.append(f"{location}：第 {line_no} 行超出 scenario.ks 範圍。")
            continue

        source = row.get("source_text") or ""
        speaker = row.get("speaker") or ""
        expected_hash = source_hash(line_no, speaker, source)
        if (row.get("source_hash") or "").strip().lower() != expected_hash:
            errors.append(f"{location}：source_hash 不符，原文欄位可能被修改。")
            continue

        current = content_without_line_ending(lines[line_no - 1])
        if current != source:
            errors.append(f"{location}：scenario.ks 第 {line_no} 行已不是 TSV 中的原文。")
            continue

        # Confirm that this is still the line immediately following the matching @name.
        if line_no < 2:
            errors.append(f"{location}：文本行前方不存在 @name。")
            continue
        name_match = NAME_PATTERN.match(content_without_line_ending(lines[line_no - 2]))
        if not name_match or name_match.group(1) != speaker:
            errors.append(f"{location}：前一行 @name 的角色與 speaker 不符。")
            continue

        translated = row.get("translated_text") or ""
        if not translated.strip():
            skipped += 1
            continue
        if "\r" in translated or "\n" in translated:
            errors.append(f"{location}：translated_text 不可包含換行。")
            continue
        if "\t" in translated:
            errors.append(f"{location}：translated_text 不可包含 Tab。")
            continue

        source_tags = Counter(INLINE_TAG_PATTERN.findall(source))
        translated_tags = Counter(INLINE_TAG_PATTERN.findall(translated))
        if source_tags != translated_tags:
            errors.append(f"{location}：翻譯沒有完整保留原文的方括號標記。")
            continue

        leading = LEADING_SPACE_PATTERN.match(source).group(0)
        translated_body = LEADING_SPACE_PATTERN.sub("", translated, count=1)
        replacement = leading + translated_body
        replacements[line_no] = replacement

    return replacements, skipped, errors


def next_backup_path(scenario: Path) -> Path:
    first = scenario.with_name(scenario.name + ".bak")
    if not first.exists():
        return first
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = scenario.with_name(f"{scenario.name}.{stamp}.bak")
    number = 1
    while candidate.exists():
        candidate = scenario.with_name(f"{scenario.name}.{stamp}-{number}.bak")
        number += 1
    return candidate


def write_utf16le_atomic(scenario: Path, text: str) -> None:
    payload = codecs.BOM_UTF16_LE + text.encode("utf-16-le")
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=scenario.name + ".",
            suffix=".tmp",
            dir=scenario.parent,
            delete=False,
        ) as stream:
            temporary_name = stream.name
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, scenario)
        temporary_name = None
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def replace_mode(scenario: Path) -> None:
    text, encoding = detect_and_decode(scenario)
    lines = text.splitlines(keepends=True)
    rows, files = load_translation_rows(scenario.parent)
    replacements, skipped, errors = prepare_replacements(rows, lines)

    print(f"讀取 TSV：{len(files)} 個，共 {len(rows)} 筆")
    print(f"可替換：{len(replacements)} 筆；未翻譯而跳過：{skipped} 筆")
    if errors:
        print(f"\n驗證失敗，共 {len(errors)} 個問題：")
        for message in errors[:20]:
            print(f"- {message}")
        if len(errors) > 20:
            print(f"- ……另外還有 {len(errors) - 20} 個問題")
        raise TranslationError("已取消替換，scenario.ks 沒有被修改。")
    if not replacements:
        raise TranslationError("沒有任何可替換的翻譯，scenario.ks 沒有被修改。")

    print(f"來源編碼：{encoding}")
    already_backed_up = ask_yes_no("你是否已經備份 scenario.ks？ (選否的話會自動備份 scenario.ks)")
    backup: Path | None = None
    if not already_backed_up:
        backup = next_backup_path(scenario)
        shutil.copy2(scenario, backup)
        print(f"已建立備份：{backup.name}")

    for line_no, replacement in replacements.items():
        original_line = lines[line_no - 1]
        lines[line_no - 1] = replacement + line_ending_of(original_line)

    write_utf16le_atomic(scenario, "".join(lines))
    print("\n替換完成")
    print(f"已替換：{len(replacements)} 筆")
    print(f"跳過未翻譯：{skipped} 筆")
    print("輸出編碼：UTF-16 LE BOM")
    if backup:
        print(f"備份：{backup}")


def main() -> int:
    print("NornMiel 遊戲文本提取／替換工具")
    print(f"目前資料夾：{Path.cwd()}")
    print("1. 提取 scenario.ks 到 Translation-xxx.tsv")
    print("2. 將 TSV 翻譯替換回 scenario.ks")
    print("0. 結束")
    choice = input("請選擇操作：").strip()

    if choice == "0":
        print("已結束。")
        return 0
    if choice not in {"1", "2"}:
        raise TranslationError("無效的選項，請輸入 1、2 或 0。")

    scenario = resolve_scenario(Path.cwd())
    if choice == "1":
        extract_mode(scenario)
    else:
        replace_mode(scenario)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (TranslationError, OSError, csv.Error) as exc:
        print(f"\n錯誤：{exc}", file=sys.stderr)
        raise SystemExit(1)
