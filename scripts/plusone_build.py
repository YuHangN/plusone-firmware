#!/usr/bin/env python3
"""Build the Plusone firmware for M5Stack AtomS3R + Atomic Echo Base.

The default OTA URL (our server address) is private and must never be
committed. This script reads it at build time, in this order:

  1. --ota-url https://example.com/plusone/ota/
  2. environment variable PLUSONE_OTA_URL
  3. plusone.local.env in the repo root (git-ignored):
         PLUSONE_OTA_URL=https://example.com/plusone/ota/
     or  PLUSONE_HOST=example.com
  4. the Plusone deploy config (default ../Plusone/private/deploy.env,
     override with --deploy-env or PLUSONE_DEPLOY_ENV):
         PLUSONE_OTA_URL=...   or   PLUSONE_HOST=example.com
     PLUSONE_HOST becomes https://<host>/plusone/ota/

Everything else (wake word, hotspot name, partition table) lives in
main/boards/atoms3r-echo-base/config.json.

The URL only ends up in sdkconfig and build/, which are both git-ignored.

Usage (inside an ESP-IDF shell, i.e. after `. $IDF_PATH/export.sh`):
    python scripts/plusone_build.py
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
BOARD = "atoms3r-echo-base"
BOARD_CONFIG = "CONFIG_BOARD_TYPE_M5STACK_ATOM_S3R_ECHO_BASE"
OTA_PATH = "/plusone/ota/"


def read_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def url_from_values(values: Dict[str, str]) -> Optional[str]:
    if values.get("PLUSONE_OTA_URL"):
        return values["PLUSONE_OTA_URL"]
    if values.get("PLUSONE_HOST"):
        return f"https://{values['PLUSONE_HOST']}{OTA_PATH}"
    return None


def resolve_ota_url(args: argparse.Namespace) -> Tuple[str, str]:
    if args.ota_url:
        return args.ota_url, "--ota-url"
    if os.environ.get("PLUSONE_OTA_URL"):
        return os.environ["PLUSONE_OTA_URL"], "env PLUSONE_OTA_URL"
    local = ROOT / "plusone.local.env"
    url = url_from_values(read_env_file(local))
    if url:
        return url, str(local)
    deploy = Path(args.deploy_env or os.environ.get("PLUSONE_DEPLOY_ENV")
                  or ROOT.parent / "Plusone" / "private" / "deploy.env")
    url = url_from_values(read_env_file(deploy))
    if url:
        return url, str(deploy)
    sys.exit(
        "没有找到 OTA 地址。任选一种：\n"
        "  python scripts/plusone_build.py --ota-url https://你的域名/plusone/ota/\n"
        "  export PLUSONE_OTA_URL=https://你的域名/plusone/ota/\n"
        "  在仓库根目录建 plusone.local.env，写 PLUSONE_HOST=你的域名\n"
        f"  （或者在 {deploy} 里写 PLUSONE_HOST=你的域名）"
    )


def masked(url: str) -> str:
    """Show the shape of the URL without the host, so logs stay shareable."""
    u = urlparse(url)
    return f"{u.scheme}://***{u.path}"


def run(cmd: list) -> None:
    print("+", " ".join(cmd), flush=True)
    if subprocess.call(cmd, cwd=ROOT) != 0:
        sys.exit(f"失败：{' '.join(cmd)}")


def partition_size(csv_path: Path, name: str) -> Optional[int]:
    for line in csv_path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#"):
            continue
        cols = [c.strip() for c in line.split(",")]
        if len(cols) >= 5 and cols[0] == name:
            size = cols[4]
            if size.upper().endswith("M"):
                return int(size[:-1]) * 1024 * 1024
            if size.upper().endswith("K"):
                return int(size[:-1]) * 1024
            return int(size, 0)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ota-url", help="default OTA URL baked into the firmware")
    parser.add_argument("--deploy-env", help="path to the Plusone deploy.env")
    args = parser.parse_args()

    if not os.environ.get("IDF_PATH"):
        sys.exit("先进入 ESP-IDF 环境：. ~/esp/esp-idf-v5.5.2/export.sh")

    ota_url, source = resolve_ota_url(args)
    if not ota_url.startswith(("http://", "https://")):
        sys.exit(f"OTA 地址要以 http:// 或 https:// 开头（来自 {source}）")
    if not ota_url.endswith("/"):
        ota_url += "/"
    print(f"OTA URL: {masked(ota_url)}  (from {source})")

    cfg = json.loads((ROOT / "main" / "boards" / BOARD / "config.json").read_text(encoding="utf-8"))
    build = cfg["builds"][0]
    append = [f"{BOARD_CONFIG}=y", *build.get("sdkconfig_append", []),
              f'CONFIG_OTA_URL="{ota_url}"']

    os.environ.pop("IDF_TARGET", None)
    run(["idf.py", "set-target", cfg["target"]])
    with (ROOT / "sdkconfig").open("a", encoding="utf-8") as f:
        f.write("\n# Append by plusone_build.py\n")
        for item in append:
            f.write(item + "\n")
    run(["idf.py", f"-DBOARD_NAME={build['name']}", f"-DBOARD_TYPE={BOARD}", "build"])
    run(["idf.py", "merge-bin"])

    # Sanity checks: the settings really landed, and everything fits.
    sdkconfig = (ROOT / "sdkconfig").read_text(encoding="utf-8")
    for item in append:
        key, _, value = item.partition("=")
        if f"{key}={value}" not in sdkconfig:
            print(f"[WARN] sdkconfig 里没有生效：{key}", file=sys.stderr)

    part_csv = None
    for item in append:
        if item.startswith("CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="):
            part_csv = ROOT / item.split("=", 1)[1].strip('"')
    if part_csv is None:
        sys.exit("config.json 里没有 CONFIG_PARTITION_TABLE_CUSTOM_FILENAME")
    print(f"分区表：{part_csv.relative_to(ROOT)}")
    app_part = "factory" if partition_size(part_csv, "factory") else "ota_0"
    app_bin = ROOT / "build" / "xiaozhi.bin"
    assets_bin = ROOT / "build" / "generated_assets.bin"
    ok = True
    for label, path, part in (("app", app_bin, app_part), ("assets", assets_bin, "assets")):
        limit = partition_size(part_csv, part)
        size = path.stat().st_size if path.exists() else None
        if size is None or limit is None:
            print(f"[WARN] 找不到 {path.name} 或分区 {part}")
            ok = False
            continue
        pct = size * 100 / limit
        print(f"{label:6s} {size / 1024 / 1024:5.2f} MB / {limit / 1024 / 1024:.2f} MB ({pct:.0f}%)")
        if size > limit:
            print(f"[ERROR] {label} 超出分区大小", file=sys.stderr)
            ok = False
    if not ok:
        sys.exit(1)
    print("完成：build/merged-binary.bin（整片烧录用），或 idf.py -p <端口> flash")


if __name__ == "__main__":
    main()
