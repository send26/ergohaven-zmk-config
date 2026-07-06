#!/usr/bin/env python3
"""Interactive test for ZMK sym layer Unicode output on macOS.

Usage:
  python3 scripts/test_sym_unicode.py              # quick smoke test (5 keys)
  python3 scripts/test_sym_unicode.py --full       # all sym keys
  python3 scripts/test_sym_unicode.py --analyze  # summarize last log

While the script waits for input:
  1. Focus this terminal window
  2. Be on ru or en layer — does not matter
  3. Hold sym-layer key (same as Backspace hold)
  4. Tap the prompted key once
  5. Release sym, type/paste the result here, press Enter
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_LOG = Path.home() / ".cache" / "zmk_layer" / "sym_unicode_test.jsonl"
MACIME = Path("/usr/local/bin/macime")
UNICODE_HEX = "com.apple.keylayout.UnicodeHexInput"
RUSSIAN = "com.apple.keylayout.Russian"
ABC = "com.apple.keylayout.ABC"


def current_macos_layout() -> str | None:
    if not MACIME.exists():
        return None
    try:
        import subprocess

        result = subprocess.run(
            [str(MACIME), "get"],
            check=False,
            capture_output=True,
            text=True,
        )
        layout = result.stdout.strip()
        return layout or None
    except OSError:
        return None


def preflight() -> None:
    layout = current_macos_layout()
    print("Preflight")
    print("---------")
    if layout:
        print(f"macime current layout: {layout}")
    else:
        print("macime not available — enter layout name manually")
    print()
    print("Unicode sym layer on macOS needs ONE of:")
    print("  • Input source 'Unicode Hex Input' added in System Settings")
    print("  • or working Option+hex entry for UC_MODE_MACOS")
    print()
    print("Recommended test order:")
    print("  1) macOS layout = Russian  → quick test")
    print("  2) macOS layout = ABC      → quick test again")
    print("  3) share log for analysis")
    print()

# Velvet v3 UI: 6 клавиш на ряд на каждой половине, счёт клавиш слева→направо на левой
# и от центра→наружу на правой. Ряд 1 — верхний пальцевый, ряд 4 — пальцы/большие.
# base_ref — где эта клавиша на слое en (ориентир).
SYM_KEYS: list[dict] = [
    # --- ряд 1 ---
    {
        "id": "hash",
        "expect": "#",
        "cp": 0x23,
        "position": "Левая половина, ряд 1, клавиша 2",
        "base_ref": "там же, где Q на слое en",
    },
    {
        "id": "lt",
        "expect": "<",
        "cp": 0x3C,
        "position": "Левая половина, ряд 1, клавиша 3",
        "base_ref": "там же, где W на слое en",
    },
    {
        "id": "equal",
        "expect": "=",
        "cp": 0x3D,
        "position": "Левая половина, ряд 1, клавиша 4",
        "base_ref": "там же, где E на слое en",
    },
    {
        "id": "gt",
        "expect": ">",
        "cp": 0x3E,
        "position": "Левая половина, ряд 1, клавиша 5",
        "base_ref": "там же, где R на слое en",
    },
    {
        "id": "asterisk",
        "expect": "*",
        "cp": 0x2A,
        "position": "Левая половина, ряд 1, клавиша 6 (у центра)",
        "base_ref": "там же, где T на слое en",
    },
    {
        "id": "caret",
        "expect": "^",
        "cp": 0x5E,
        "position": "Правая половина, ряд 1, клавиша 1 (у центра)",
        "base_ref": "там же, где Y на слое en",
    },
    {
        "id": "dquote",
        "expect": '"',
        "cp": 0x22,
        "position": "Правая половина, ряд 1, клавиша 2",
        "base_ref": "там же, где U на слое en",
    },
    {
        "id": "grave",
        "expect": "`",
        "cp": 0x60,
        "position": "Правая половина, ряд 1, клавиша 3",
        "base_ref": "там же, где I на слое en",
    },
    {
        "id": "squote",
        "expect": "'",
        "cp": 0x27,
        "position": "Правая половина, ряд 1, клавиша 4",
        "base_ref": "там же, где O на слое en",
    },
    {
        "id": "lbracket",
        "expect": "[",
        "cp": 0x5B,
        "position": "Правая половина, ряд 1, клавиша 5",
        "base_ref": "там же, где P на слое en",
    },
    {
        "id": "rbracket",
        "expect": "]",
        "cp": 0x5D,
        "position": "Правая половина, ряд 1, клавиша 6 (крайняя справа)",
        "base_ref": "там же, где Backspace на слое en",
    },
    # --- ряд 2 ---
    {
        "id": "star2",
        "expect": "*",
        "cp": 0x2A,
        "position": "Левая половина, ряд 2, клавиша 2",
        "base_ref": "там же, где S на слое en",
    },
    {
        "id": "lpar",
        "expect": "(",
        "cp": 0x28,
        "position": "Левая половина, ряд 2, клавиша 3",
        "base_ref": "там же, где D на слое en",
    },
    {
        "id": "minus",
        "expect": "-",
        "cp": 0x2D,
        "position": "Левая половина, ряд 2, клавиша 4",
        "base_ref": "там же, где F на слое en",
    },
    {
        "id": "rpar",
        "expect": ")",
        "cp": 0x29,
        "position": "Левая половина, ряд 2, клавиша 5",
        "base_ref": "там же, где G на слое en",
    },
    {
        "id": "plus",
        "expect": "+",
        "cp": 0x2B,
        "position": "Левая половина, ряд 2, клавиша 6 (у центра)",
        "base_ref": "там же, где H на слое en (левая рука)",
    },
    {
        "id": "percent",
        "expect": "%",
        "cp": 0x25,
        "position": "Правая половина, ряд 2, клавиша 1 (у центра)",
        "base_ref": "там же, где J на слое en",
    },
    {
        "id": "lbrace",
        "expect": "{",
        "cp": 0x7B,
        "position": "Правая половина, ряд 2, клавиша 2",
        "base_ref": "там же, где K на слое en",
    },
    {
        "id": "under",
        "expect": "_",
        "cp": 0x5F,
        "position": "Правая половина, ряд 2, клавиша 3",
        "base_ref": "там же, где L на слое en",
    },
    {
        "id": "rbrace",
        "expect": "}",
        "cp": 0x7D,
        "position": "Правая половина, ряд 2, клавиша 4",
        "base_ref": "там же, где ; на слое en",
    },
    {
        "id": "semi",
        "expect": ";",
        "cp": 0x3B,
        "position": "Правая половина, ряд 2, клавиша 5",
        "base_ref": "там же, где ' на слое en (правая домашняя)",
    },
    {
        "id": "backslash",
        "expect": "\\",
        "cp": 0x5C,
        "position": "Правая половина, ряд 2, клавиша 6 (крайняя справа)",
        "base_ref": "там же, где \\ на слое en",
    },
    # --- ряд 3 ---
    {
        "id": "comma",
        "expect": ",",
        "cp": 0x2C,
        "position": "Левая половина, ряд 3, клавиша 2",
        "base_ref": "там же, где X на слое en",
    },
    {
        "id": "backslash2",
        "expect": "\\",
        "cp": 0x5C,
        "position": "Левая половина, ряд 3, клавиша 3",
        "base_ref": "там же, где C на слое en",
    },
    {
        "id": "colon",
        "expect": ":",
        "cp": 0x3A,
        "position": "Левая половина, ряд 3, клавиша 4",
        "base_ref": "там же, где V на слое en",
    },
    {
        "id": "slash",
        "expect": "/",
        "cp": 0x2F,
        "position": "Левая половина, ряд 3, клавиша 5",
        "base_ref": "там же, где B на слое en",
    },
    {
        "id": "pipe",
        "expect": "|",
        "cp": 0x7C,
        "position": "Левая половина, ряд 3, клавиша 6 (у центра)",
        "base_ref": "там же, где B на слое en",
    },
    {
        "id": "at",
        "expect": "@",
        "cp": 0x40,
        "position": "Правая половина, ряд 3, клавиша 1 (у центра)",
        "base_ref": "там же, где N на слое en",
    },
    {
        "id": "dollar",
        "expect": "$",
        "cp": 0x24,
        "position": "Правая половина, ряд 3, клавиша 2",
        "base_ref": "там же, где M на слое en",
    },
    {
        "id": "comma2",
        "expect": ",",
        "cp": 0x2C,
        "position": "Правая половина, ряд 3, клавиша 3",
        "base_ref": "там же, где , (запятая) на слое en",
    },
    {
        "id": "dot",
        "expect": ".",
        "cp": 0x2E,
        "position": "Правая половина, ряд 3, клавиша 4",
        "base_ref": "там же, где . (точка) на слое en",
    },
    {
        "id": "qmark",
        "expect": "?",
        "cp": 0x3F,
        "position": "Правая половина, ряд 3, клавиша 5",
        "base_ref": "там же, где ? на слое en",
    },
    {
        "id": "excl",
        "expect": "!",
        "cp": 0x21,
        "position": "Правая половина, ряд 3, клавиша 6 (крайняя справа)",
        "base_ref": "крайняя нижняя справа (на en пусто/none)",
    },
    # --- ряд 4 (большие) ---
    {
        "id": "amps",
        "expect": "&",
        "cp": 0x26,
        "position": "Правая половина, ряд 4 (большие), клавиша 9",
        "base_ref": "правый большой палец, вторая клавиша справа от пробела",
    },
    {
        "id": "tilde",
        "expect": "~",
        "cp": 0x7E,
        "position": "Правая половина, ряд 4 (большие), клавиша 10",
        "base_ref": "правый большой палец, крайняя правая в нижнем ряду",
    },
]

QUICK_IDS = ("dollar", "at", "hash", "percent", "pipe")


def format_key_hint(key: dict) -> str:
    lines = [
        key.get("position", ""),
        f"Ориентир: {key.get('base_ref', '')}",
    ]
    return "\n  ".join(line for line in lines if line)


def print_layout_legend() -> None:
    print("Схема нумерации Velvet v3 UI:")
    print("  • Ряды 1–3 — пальцевые (сверху вниз)")
    print("  • Ряд 4 — большие пальцы")
    print("  • Левая половина: клавиши 1→6 слева направо")
    print("  • Правая половина: клавиши 1→6 от центра к правому краю")
    print("  • Sym включается удержанием Backspace (правая половина, ряд 4)")
    print()


def codepoints(text: str) -> list[int]:
    return [ord(ch) for ch in text]


def analyze_sym_ru_flapping(log_text: str, window_sec: float = 2.0) -> list[dict]:
    """Find sym↔ru rapid macime flips in daemon log (root cause of bad unicode)."""
    import re
    from datetime import datetime

    events: list[tuple[datetime, str, int]] = []
    layer_re = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ INFO Layer update.*: (?:sym|ru|base) \(index (\d+)\)"
    )
    macime_re = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ INFO macime → (com\.apple\.keylayout\.\S+)"
    )

    for line in log_text.splitlines():
        layer_match = layer_re.match(line)
        if layer_match:
            ts = datetime.fromisoformat(layer_match.group(1))
            events.append((ts, "layer", int(layer_match.group(2))))
            continue
        macime_match = macime_re.match(line)
        if macime_match:
            ts = datetime.fromisoformat(macime_match.group(1))
            events.append((ts, "macime", macime_match.group(1)))

    flips: list[dict] = []
    for index in range(1, len(events)):
        prev_ts, prev_kind, prev_val = events[index - 1]
        ts, kind, val = events[index]
        delta = (ts - prev_ts).total_seconds()
        if delta > window_sec:
            continue
        if prev_kind == "macime" and kind == "macime" and prev_val != val:
            if {prev_val, val} >= {UNICODE_HEX, RUSSIAN} or {prev_val, val} >= {
                UNICODE_HEX,
                "com.apple.keylayout.ABC",
            }:
                flips.append(
                    {
                        "at": ts.isoformat(sep=" "),
                        "delta_ms": int(delta * 1000),
                        "from": prev_val,
                        "to": val,
                    }
                )
    return flips


def analyze_daemon_log(path: Path) -> int:
    if not path.exists():
        print(f"Log not found: {path}")
        return 1
    flips = analyze_sym_ru_flapping(path.read_text(encoding="utf-8", errors="replace"))
    print(f"Daemon log: {path}")
    print(f"Sym layout flips within 2s: {len(flips)}")
    for flip in flips[-10:]:
        print(
            f"  {flip['at']} +{flip['delta_ms']}ms: "
            f"{flip['from']} → {flip['to']}"
        )
    return 0 if len(flips) == 0 else 1


    return [ord(ch) for ch in text]


def describe_chars(text: str) -> str:
    if not text:
        return "(empty)"
    parts = []
    for ch in text:
        parts.append(f"{ch!r} U+{ord(ch):04X}")
    return " ".join(parts)


def append_log(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def analyze_log(path: Path) -> int:
    records = load_log(path)
    if not records:
        print(f"No log entries in {path}")
        return 1

    print(f"Log: {path} ({len(records)} entries)\n")
    passed = failed = skipped = 0
    for record in records:
        status = record.get("status", "?")
        if status == "pass":
            passed += 1
        elif status == "skip":
            skipped += 1
        else:
            failed += 1
        print(
            f"[{status:4}] {record.get('id')}: "
            f"expected {record.get('expect')!r} "
            f"got {describe_chars(record.get('got', ''))}"
        )
        if record.get("position"):
            print(f"       pos: {record['position']}")
        if record.get("note"):
            print(f"       note: {record['note']}")

    print(f"\nSummary: {passed} pass, {failed} fail, {skipped} skip")
    return 0 if failed == 0 else 1


def prompt_layout() -> str:
    print("Current macOS input source (type name, e.g. Russian / ABC / Unicode Hex Input):")
    return input("> ").strip()


def run_tests(keys: list[dict], log_path: Path, session_note: str = "") -> int:
    print("=" * 60)
    print("ZMK sym Unicode test")
    print("=" * 60)
    print()
    preflight()
    print_layout_legend()
    print("Before each key:")
    print("  • focus THIS terminal")
    print("  • hold sym-layer (Backspace hold on ru/en)")
    print("  • tap the prompted key once")
    print("  • release sym")
    print("  • paste/type result below, Enter")
    print("  • empty line + Enter = skip")
    print("  • q + Enter = quit")
    print()
    layout = prompt_layout()
    print()
    input("Press Enter when ready to start...")
    print()

    session_id = datetime.now().isoformat(timespec="seconds")
    failures = 0

    for index, key in enumerate(keys, start=1):
        print("-" * 60)
        print(f"Test {index}/{len(keys)}: {key['id']}")
        print(f"Expected: {key['expect']!r}  (U+{key['cp']:04X})")
        print(f"Куда нажать:\n  {format_key_hint(key)}")
        got = input("Result> ")

        if got.strip().lower() == "q":
            print("Stopped.")
            break
        if got == "":
            record = {
                "session": session_id,
                "layout": layout,
                "id": key["id"],
                "expect": key["expect"],
                "expect_cp": key["cp"],
                "position": key.get("position", ""),
                "base_ref": key.get("base_ref", ""),
                "got": "",
                "got_cps": [],
                "status": "skip",
                "note": session_note,
            }
            append_log(log_path, record)
            print("skipped")
            continue

        got_cps = codepoints(got)
        ok = len(got) == 1 and got_cps[0] == key["cp"]
        status = "pass" if ok else "fail"
        if not ok:
            failures += 1

        record = {
            "session": session_id,
            "layout": layout,
            "id": key["id"],
            "expect": key["expect"],
            "expect_cp": key["cp"],
            "position": key.get("position", ""),
            "base_ref": key.get("base_ref", ""),
            "got": got,
            "got_cps": got_cps,
            "status": status,
            "note": session_note,
        }
        append_log(log_path, record)

        if ok:
            print(f"OK: {describe_chars(got)}")
        else:
            print(f"FAIL: got {describe_chars(got)}")

    print()
    print(f"Log written to: {log_path}")
    return 0 if failures == 0 else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="Test all sym keys")
    parser.add_argument("--analyze", action="store_true", help="Analyze interactive test log")
    parser.add_argument(
        "--analyze-daemon-log",
        nargs="?",
        const=Path.home() / "Library/Logs/zmk-layer-daemon.log",
        type=Path,
        help="Analyze zmk-layer-daemon.log for sym↔ru macime flapping",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=DEFAULT_LOG,
        help=f"Log file (default: {DEFAULT_LOG})",
    )
    parser.add_argument(
        "--note",
        default="",
        help="Optional note stored with each log row (firmware version, etc.)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.analyze_daemon_log is not None:
        return analyze_daemon_log(args.analyze_daemon_log)
    if args.analyze:
        return analyze_log(args.log)

    if args.full:
        keys = SYM_KEYS
    else:
        keys = [key for key in SYM_KEYS if key["id"] in QUICK_IDS]

    return run_tests(keys, args.log, session_note=args.note)


if __name__ == "__main__":
    sys.exit(main())
