#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import argparse
import hashlib
from urllib.parse import urlsplit
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path



R = "\x1b[91m"
G = "\x1b[92m"
Y = "\x1b[93m"
B = "\x1b[94m"
M = "\x1b[95m"
C = "\x1b[96m"
W = "\x1b[97m"
D = "\x1b[90m"
N = "\x1b[0m"
BD = "\x1b[1m"

# ---------------- 控制常量 ----------------
DEBUG_MODE = "1"
TOOL_TIMEOUT = 10 * 60

# auto 模式标志（--auto CLI），控制是否静默外部工具实时进度输出
AUTO_MODE = False


# ---------------- 控制台准备 ----------------
def init_console(auto=False):
    global AUTO_MODE
    AUTO_MODE = auto
    # 启用 ANSI 虚拟终端
    os.system("")
    # 设置控制台窗口标题（auto 模式下跳过）
    if not auto:
        os.system("title XMAPort 260824.Beta")
    # 防止非 UTF-8 终端下中文输出崩溃
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    # 子进程脚本同样用 UTF-8 输出，避免 CI cp1252 下中文崩溃
    os.environ["PYTHONIOENCODING"] = "utf-8"


# ---------------- 路径（脚本所在目录为根） ----------------
ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "tools"
WORKSPACE = ROOT / "workspace"


PY = sys.executable
if not PY:
    PY = "python"

ARIA2 = TOOLS / "aria2c.exe"
SZ = TOOLS / "7z.exe"
PDUMP = TOOLS / "payload-dumper-go.exe"
S2I = TOOLS / "simg2img.exe"
I2S = TOOLS / "img2simg.exe"
LPU = TOOLS / "lpunpack.exe"
LPM = TOOLS / "lpmake.exe"
LPD = TOOLS / "lpdumps.exe"
HLP = TOOLS / "img_helper.py"

CONFIG = ROOT / "config.ini"
SRC_DL = WORKSPACE / "download_source"
TGT_DL = WORKSPACE / "download_target"
SRC_ROM = WORKSPACE / "source_rom"
TGT_ROM = WORKSPACE / "target_rom"
SRC_UNPACK = WORKSPACE / "source_payload"
TGT_UNPACK = WORKSPACE / "target_payload"
OUT_DIR = WORKSPACE / "output"
SRC_FS = WORKSPACE / "source_filesystem"
TGT_FS = WORKSPACE / "target_filesystem"
PACK_OUT = WORKSPACE / "packed"

ALL_DIRS = [
    WORKSPACE, SRC_DL, TGT_DL, SRC_ROM, TGT_ROM, SRC_UNPACK,
    TGT_UNPACK, OUT_DIR, SRC_FS, TGT_FS, PACK_OUT,
]

UNPACK_PARTS = ["system", "system_ext", "product", "odm", "mi_ext", "vendor"]
PACK_SOURCE_PARTS = ["system", "system_ext", "product"]
ALL_OUTPUT_PARTS = ["system", "system_ext", "product", "odm", "mi_ext", "vendor", "vendor_dlkm"]

# ---------------- 日志文件（日期-小时.log） ----------------
_now = datetime.now()
LOG_FILE = WORKSPACE / "{}-{}.log".format(_now.strftime("%Y-%m-%d"), _now.hour)


def log_write(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("[{}] {}\n".format(datetime.now().strftime("%H:%M:%S"), msg))
    except Exception:
        pass


# ---------------- 输出辅助（INFO 仅在 DEBUG_MODE=1 时显示） ----------------
def info(msg):
    if DEBUG_MODE == "1":
        print("  {}[INFO]{}   {}".format(G, N, msg), flush=True)


def err(msg):
    print("  {}[ERROR]{} {}".format(R, N, msg), flush=True)


def prompt(text):
    # EOF 时优雅退出而非抛出 Traceback
    sys.stdout.write(text)
    sys.stdout.flush()
    try:
        return input()
    except EOFError:
        print()
        sys.exit(0)


def pause():
    # 等待任意键（非交互环境自动跳过）
    if sys.stdin and sys.stdin.isatty():
        sys.stdout.write("Please press any key to continue . . . ")
        sys.stdout.flush()
        try:
            import msvcrt
            msvcrt.getch()
            print(flush=True)
        except Exception:
            input()
    else:
        # 非交互环境自动跳过
        pass


def pause_seconds(seconds):
    time.sleep(seconds)


DEVICE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def is_safe_device_name(name):
    return bool(DEVICE_NAME_RE.fullmatch(name.strip()))


def run_tool(cmd, **kwargs):
    # 外部工具超过 10 分钟仍未退出时终止，避免流程永久挂起。
    label = Path(cmd[0]).name if cmd else "external tool"
    try:
        return subprocess.run(cmd, timeout=TOOL_TIMEOUT, **kwargs)
    except FileNotFoundError:
        err("{} not found (tool missing or blocked by antivirus)".format(label))
        log_write("ERROR: tool not found: {}".format(cmd[0]))
        return subprocess.CompletedProcess(cmd, 127, stdout="", stderr="")
    except subprocess.TimeoutExpired:
        err("{} timed out after {} minutes".format(label, TOOL_TIMEOUT // 60))
        log_write("ERROR: {} timed out after {} seconds".format(label, TOOL_TIMEOUT))
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")


# ---------------- 全局状态 ----------------
TARGET_DEVICE = ""
SRC_URL = ""
TGT_URL = ""
# 下载设置默认值
THREADS = 16
MAX_CONN = 16
TIMEOUT = 300
RETRY = 5
RETRY_WAIT = 3

# ---------------- CLI 覆盖参数（由 argparse 写入） ----------------
CLI_SOURCE_URL = ""
CLI_TARGET_URL = ""
CLI_DEVICE = ""


# ---------------- [A] 工具状态检查 ----------------
def check_tool(name, src):
    p = TOOLS / name
    try:
        ok = p.exists() and p.stat().st_size > 0
    except Exception:
        ok = False
    tag = "{}[OK]{}".format(G, N) if ok else "{}[N/A]{}".format(R, N)
    print("  {}{}  {}  {}{}{}".format(W, name, tag, D, src, N))


def tool_status(pause_after=True):
    os.system("cls" if os.name == "nt" else "clear")
    print()
    print("  {}+----------------------------------------------------------+{}".format(C, N))
    print("  {}|  Tools Checking, please wait for 5 seconds                |{}".format(C, N))
    print("  {}+----------------------------------------------------------+{}".format(C, N))
    print()
    print("  {}{:<20} {}".format(W, "Tool", "Source" + N))
    print("  " + D + "----------------------------------------------------------" + N)
    check_tool("aria2c.exe", "github.com/aria2/aria2")
    check_tool("7z.exe", "www.7-zip.org")
    check_tool("payload-dumper-go.exe", "github.com/ssut/payload-dumper-go")
    check_tool("simg2img.exe", "AOSP system/core/libsparse")
    check_tool("img2simg.exe", "AOSP system/core/libsparse")
    check_tool("lpunpack.exe", "AOSP extras/partition_tools")
    check_tool("lpmake.exe", "AOSP extras/partition_tools")
    check_tool("lpdumps.exe", "AOSP extras/partition_tools")
    check_tool("img_helper.py", "XMAPort bundled script")
    check_tool("pack_partitions.py", "XMAPort bundled script")
    print("  " + D + "----------------------------------------------------------" + N)
    if pause_after:
        pause()


# ---------------- [C] 开源致谢 ----------------
def show_credits_entry(no, name, desc, url, lic):
    print("  {}  {}. {}{}".format(G, no, name, N))
    print("  {}     {}{}".format(W, desc, N))
    print("  {}     {}{}".format(C, url, N))
    print("  {}     credit: {}{}".format(D, lic, N))
    print()


def show_credits():
    os.system("cls" if os.name == "nt" else "clear")
    print()
    print("  {}{}============================================================{}".format(C, BD, N))
    print("  {}{}  Open-source credits{}".format(C, BD, N))
    print("  {}{}============================================================{}".format(C, BD, N))
    print()
    show_credits_entry(1, "aria2c", "Multi-threaded downloader", "https://github.com/aria2/aria2", "GPL v2")
    show_credits_entry(2, "7-Zip (7z.exe)", "Archive extractor", "https://www.7-zip.org/", "GNU LGPL")
    show_credits_entry(3, "payload-dumper-go", "Android OTA payload.bin extractor",
                       "https://github.com/ssut/payload-dumper-go", "MIT")
    show_credits_entry(4, "AOSP partition tools", "lpunpack, lpmake, lpdumps",
                       "https://github.com/nicktal01/aosp15_partition_tools", "Apache 2.0")
    show_credits_entry(5, "erofs-utils", "EROFS image creation and extraction", "https://github.com/erofs/erofs-utils", "GPL v2")
    show_credits_entry(6, "e2fsprogs", "ext4 tools: mke2fs, e2fsdroid", "https://github.com/tytso/e2fsprogs", "GPL v2 / LGPL v2")
    show_credits_entry(7, "Google Brotli", "Block OTA Brotli decompression", "https://github.com/google/brotli", "MIT")
    show_credits_entry(8, "Magisk", "Verified AVB verification-disable pattern", "https://github.com/topjohnwu/Magisk", "GPL v3")
    print("  " + D + "----------------------------------------------------------" + N)
    pause()


# ---------------- [D] 清理 workspace ----------------
def clean_workspace():
    global TARGET_DEVICE
    os.system("cls" if os.name == "nt" else "clear")
    print()
    print("  {}  This will delete all extracted .img and payload.bin files.{}".format(Y, N))
    print("  {}  Including:{}".format(Y, N))
    for path in [
        str(SRC_UNPACK / "*.img"), str(TGT_UNPACK / "*.img"),
        str(SRC_ROM / "payload.bin"), str(TGT_ROM / "payload.bin"),
        str(WORKSPACE / "config.txt"),
    ]:
        print("  {}    - {}{}".format(D, path, N))
    print()
    answer = prompt("  {}Are you sure? (Y/N): {}".format(R, N))
    if answer.strip().lower() != "y":
        return
    info("Cleaning workspace...")
    for pattern in [SRC_UNPACK / "*.img", TGT_UNPACK / "*.img"]:
        for f in pattern.parent.glob(pattern.name):
            try:
                f.unlink()
            except Exception:
                pass
    for f in [SRC_ROM / "payload.bin", TGT_ROM / "payload.bin", WORKSPACE / "config.txt"]:
        try:
            if f.exists():
                f.unlink()
        except Exception:
            pass
    info("Workspace cleaned.")
    pause_seconds(2)


# ---------------- 配置读取 ----------------
def read_config():
    global SRC_URL, TGT_URL, THREADS, MAX_CONN, TIMEOUT, RETRY
    if not CONFIG.exists():
        info("config.ini not found, will create template")
        create_config()
        print("  {}  [!] Edit config.ini first{}".format(Y, N))
        pause()
        raise ReturnToMenu()

    info("Reading config.ini...")
    in_source = False
    in_target = False
    for raw in CONFIG.read_text(encoding="gbk", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(";"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
        else:
            key, val = line, ""
        if line == "[source]":
            in_source, in_target = True, False
        elif line == "[target]":
            in_target, in_source = True, False
        elif line == "[settings]":
            in_source, in_target = False, False
        elif line == "[packing]":
            in_source, in_target = False, False
        elif key == "url":
            if in_source:
                SRC_URL = val.strip()
            elif in_target:
                TGT_URL = val.strip()
        elif key == "threads":
            THREADS = int(val.strip())
        elif key == "max-connection":
            MAX_CONN = int(val.strip())
        elif key == "timeout":
            TIMEOUT = int(val.strip())
        elif key == "retry":
            RETRY = int(val.strip())
    info("Config loaded. SRC_URL=[{}]".format(SRC_URL))
    info("Config loaded. TGT_URL=[{}]".format(TGT_URL))
    # CLI 覆盖（--source / --target 优先于 config.ini）
    if CLI_SOURCE_URL:
        SRC_URL = CLI_SOURCE_URL
        info("SRC_URL overridden by --source")
        log_write("SRC_URL overridden by --source CLI arg")
    if CLI_TARGET_URL:
        TGT_URL = CLI_TARGET_URL
        info("TGT_URL overridden by --target")
        log_write("TGT_URL overridden by --target CLI arg")


def detect_legacy_erofs_marker():
    # 检测源 ROM 是否为 V13 DEV 版本，若是则全局启用老版 erofs 工具
    bp = SRC_FS / "product" / "etc" / "build.prop"
    if not bp.exists():
        return "false"
    try:
        text = bp.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff")
        for line in text.splitlines():
            if line.startswith("ro.product.build.version.incremental="):
                val = line.split("=", 1)[1].strip()
                if "V13" in val and "DEV" in val:
                    info("Legacy erofs marker detected: {}".format(line))
                    return "true"
    except Exception:
        pass
    return "false"


class ReturnToMenu(Exception):
    # 请求返回主菜单
    pass


# ---------------- 打包配置读取 ----------------
def read_packing_config():
    cfg = {
        "format": "erofs",
        "compression": "lz4hc",
        "compression_level": "9",
        "device_size": "6979321856",
        "metadata_size": "65536",
        "sparse": "true",
        "pack_super": "false",
        "super_name": "super",
        "super_group": "main",
        "metadata_slots": "3",
        "virtual_ab": "true",
        "is_skip_apex": "false",
        "enable_adb_debug": "false",
        "patch_vbmeta": "true",
        "utc_stamp": "",
        "erofs_old_kernel": "false",
        "device_platform": "qualcomm",
    }
    if CONFIG.exists():
        for raw in CONFIG.read_text(encoding="gbk", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith(";") or line.startswith("["):
                continue
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip().lower()
            if key in cfg:
                cfg[key] = val.strip()
    return cfg


# ---------------- 配置模板生成 ----------------
def create_config():
    content = """; ============================================
; XMAPort config file
; ============================================

; Device platform: Qualcomm/MTK, must be filled in correctly
device_platform=Qualcomm

[source]
; Source ROM download URL (direct URL, must not start with ultimateota)
; Used to extract system / system_ext / product / mi_ext partitions
; Empty URL: use local archives in workspace/download_source, otherwise reuse workspace
url=https://bkt-sgp-miui-ota-update-alisgp.oss-ap-southeast-1.aliyuncs.com/OS4.0.0.15.XPACNXM/nezha-ota_full-OS4.0.0.15.XPACNXM-user-17.0-87b65524dc.zip

[target]
; Base ROM download URL (direct URL, must not start with ultimateota)
; Used to extract odm / vendor target partitions
; Empty URL: use local archives in workspace/download_target, otherwise reuse workspace
url=https://bkt-sgp-miui-ota-update-alisgp.oss-ap-southeast-1.aliyuncs.com/OS2.0.204.0.VMWCNXM/sky-ota_full-OS2.0.204.0.VMWCNXM-user-15.0-5b8f723fe7.zip

[settings]
; aria2c download settings
; Download threads
threads=16

; Max connections
max-connection=16

; Timeout (seconds)
timeout=300

; Retry count
retry=5


[packing]
; ============================================
; Image format parameters
; ============================================
format=erofs

; Whether to pack super.img
pack_super=false

; Whether to generate sparse format image
sparse=true

; Leave empty to auto use UTC timestamp, auto decide if needed
utc_stamp=

; ============================================
; Super partition settings, fill in per device
; ============================================
; Total size allocated for device super partition, default 6.5GB
device_size=6979321856

; Keep the rest as default
; metadata partition size (bytes)
metadata_size=65536

; metadata slots
metadata_slots=3

; Whether to enable Virtual A/B
virtual_ab=true

; Super partition name
super_name=super

; Super group name
super_group=qti_dynamic_partitions

; ============================================
; erofs compression options
; ============================================
; erofs compression algorithm
compression=lz4hc

; erofs compression level
compression_level=8

; Compatibility with old kernels (-E legacy-compress)
erofs_old_kernel=false

; ============================================
; Keep this part as default
; ============================================
; When false, system_ext will be packed with legacy mkfs.erofs in tools/erofs-utils-cygwin
; When ro.product.build.version.incremental in source_filesystem/product/etc/build.prop contains both V13 and DEV, erofs packing auto uses legacy tool
is_skip_apex=false

; Whether to inject adb debug
enable_adb_debug=true

; Whether to disable vbmeta verification
patch_vbmeta=true

; ============================================
;  Build Prop Patch List, you can add props yourself, boot not guaranteed if modified
; ============================================
; patch build prop list
####################################
# from device/xiaomi/mivendor/common_rw.prop
####################################
# For common rw override property
#support night charge property
persist.vendor.night.charge=true
####################################
# from device/xiaomi/zero/odm/special_rw.prop
####################################
#support accelerate charge property
persist.vendor.accelerate.charge=true
#support battery health
persist.vendor.battery.health=true
#enable extreme battery
persist.vendor.extreme.mode=true
#support high temp dialog
persist.vendor.hightemp.notice=true
#support smart charge engine
persist.vendor.smartchg=854
#camera wechat beauty
persist.vendor.vcb.ability=true
persist.vendor.vcb.enable=false
ro.vendor.cabc.enable=fasle
ro.vendor.bcbc.enable=true
ro.vendor.dfps.enable=false
ro.vendor.fps.switch.default=true
ro.vendor.gcp.enable=1
ro.vendor.display.default_fps=90
ro.vendor.sre.enable=true
ro.vendor.localhbm.enable=true
ro.vendor.video_box.version=2
"""
    CONFIG.write_text(content, encoding="gbk")
    info("Created config template: {}".format(CONFIG))


# ---------------- Step 1 下载（两包并行 + 每包一行实时进度） ----------------
# aria2 自带的 --max-tries 只重试瞬时网络错误（超时/断连），
# HTTP 状态错误（403/404/5xx 等）会直接退出，因此必须在 Python 层整体重试。
# 每次重试借助 --continue=true 从断点续传，不会从头下载。
DL_SUMMARY_RE = re.compile(
    r"\[#\w+ (\S+)/(\S+)\((\d+|--)%\)[^\]]*?DL:(\S+)")


def download_archive_path(url, out_dir):
    # Explicit output prevents old archives or Content-Disposition from selecting the input.
    suffix = Path(urlsplit(url).path).suffix.lower()
    if suffix not in (".zip", ".tar", ".gz", ".tgz", ".7z", ".rar"):
        suffix = ".zip"
    name = "download-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16] + suffix
    return Path(out_dir) / name


def _aria2_cmd(url, out_dir):
    return [
        str(ARIA2), url,
        "--out=" + download_archive_path(url, out_dir).name,
        "-d", str(out_dir),
        "-x", str(MAX_CONN),
        "-s", str(THREADS),
        "-j", "1",
        "--min-split-size=1M",
        "--console-log-level=notice",
        "--summary-interval=1",
        "--file-allocation=falloc",
        "--timeout={}".format(TIMEOUT),
        "--max-tries={}".format(max(RETRY, 1)),
        "--retry-wait={}".format(RETRY_WAIT),
        "--lowest-speed-limit=10K",
        "--continue=true",
        "--auto-file-renaming=false",
        "--allow-overwrite=true",
        "--log-level=notice",
    ]


def _download_worker(url, out_dir, name, state):
    # 单包下载线程：整体重试，进度实时写入 state，不直接打印（避免打乱进度条）。
    # retry=0 视为只下载一次（不重试），保证至少尝试 1 次。
    total = max(RETRY, 1)
    state["attempts"] = total
    try:
        os.makedirs(out_dir, exist_ok=True)
        cmd = _aria2_cmd(url, out_dir)
        for attempt in range(1, total + 1):
            state["attempt"] = attempt
            state["status"] = "connecting"
            log_write("Download attempt {}/{} start: {}".format(attempt, total, name))
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True,
                                        errors="replace")
            except Exception:
                state["status"] = "failed"
                state["rc"] = 1
                state["error"] = "aria2c not runnable"
                log_write("ERROR: aria2c not runnable for {}".format(name))
                return
            for line in proc.stdout:
                m = DL_SUMMARY_RE.search(line)
                if m:
                    state["status"] = "downloading"
                    (state["done"], state["total"],
                     state["pct"], state["speed"]) = m.groups()
            rc = proc.wait()
            if rc == 0:
                state["status"] = "done"
                state["rc"] = 0
                log_write("Download done: {}".format(name))
                return
            log_write("Download attempt {}/{} failed for {}: exit {}".format(
                attempt, total, name, rc))
            if attempt < total:
                state["status"] = "retry_wait"
                for left in range(RETRY_WAIT, 0, -1):
                    state["retry_left"] = left
                    time.sleep(1)
        state["status"] = "failed"
        state["rc"] = 1
        state["error"] = "failed after {} attempts".format(total)
        log_write("ERROR: download failed after {} attempts: {}".format(total, name))
    except Exception as e:
        # 线程内任何意外异常都落到 failed 帧，避免进度条定格假进度、rc 悬空
        state["status"] = "failed"
        state["rc"] = 1
        state["error"] = "worker error: {}".format(e)
        log_write("ERROR: download worker crashed for {}: {}".format(name, e))


def _render_dl_line(name, st, bar_width=30):
    s = st["status"]
    if s == "done":
        total = st.get("total", "")
        return "  {:<10} [{}] 100%  {}  done".format(name, "#" * bar_width, total)
    if s == "failed":
        return "  {:<10} [FAILED] {}".format(name, st.get("error", ""))
    if s == "retry_wait":
        return "  {:<10} attempt {}/{} failed, retrying in {}s ...".format(
            name, st.get("attempt", 1), st.get("attempts", RETRY),
            st.get("retry_left", RETRY_WAIT))
    if s in ("starting", "connecting"):
        return "  {:<10} connecting ...".format(name)
    done = st.get("done", "?")
    total = st.get("total", "?")
    speed = st.get("speed", "?")
    try:
        p = int(st.get("pct", "0"))
    except ValueError:
        p = 0
    filled = int(bar_width * p / 100)
    bar = "#" * filled + "-" * (bar_width - filled)
    return "  {:<10} [{}] {:>3}%  {} / {}  DL:{}".format(
        name, bar, p, done, total, speed)


def download_roms(jobs):
    # 并行下载多个 ROM。jobs: [(url, out_dir, name), ...]；返回 {name: rc}。
    # 交互终端下每秒重绘进度（每包一行）；非 TTY（CI 日志）静默等待。
    states = {name: {"status": "starting", "rc": None} for _, _, name in jobs}
    threads = []
    for url, out_dir, name in jobs:
        t = threading.Thread(target=_download_worker,
                             args=(url, out_dir, name, states[name]), daemon=True)
        t.start()
        threads.append(t)

    if sys.stdout.isatty():
        printed = False
        while True:
            if printed:
                sys.stdout.write("\x1b[{}A".format(len(jobs)))
            for _, _, name in jobs:
                sys.stdout.write("\x1b[2K" + _render_dl_line(name, states[name]) + "\n")
            sys.stdout.flush()
            printed = True
            if all(not t.is_alive() for t in threads):
                break
            time.sleep(1)
    else:
        for t in threads:
            t.join()

    return {name: states[name]["rc"] for _, _, name in jobs}


# ---------------- Step 2 解包 ----------------
ARCHIVE_PATTERNS = ("*.zip", "*.tar", "*.gz", "*.tgz", "*.7z", "*.rar")


def local_archives(src_dir):
    return sorted({f for pattern in ARCHIVE_PATTERNS
                   for f in Path(src_dir).glob(pattern) if f.is_file()})


def select_archive(url, src_dir):
    if url:
        archive = download_archive_path(url, src_dir)
        if not archive.is_file() or archive.stat().st_size == 0:
            raise ValueError("Downloaded archive missing or empty: {}".format(archive))
    else:
        archives = local_archives(src_dir)
        if len(archives) > 1:
            raise ValueError("Multiple local archives in {}: {}. Keep only the intended package.".format(
                src_dir, ", ".join(f.name for f in archives)))
        if not archives:
            return None
        archive = archives[0]
    if archive.stat().st_size == 0 or archive.with_name(archive.name + ".aria2").exists():
        raise ValueError("Archive empty or download incomplete: {}".format(archive))
    return archive


def checked_workspace_path(path):
    path = Path(path)
    allowed = (SRC_ROM, TGT_ROM, SRC_UNPACK, TGT_UNPACK, SRC_FS, TGT_FS)
    root = WORKSPACE.resolve()
    if root != WORKSPACE.absolute():
        raise ValueError("Linked workspace blocks cleanup: {}".format(WORKSPACE))
    if path not in allowed or path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        raise ValueError("Refusing cleanup of unexpected path: {}".format(path))
    resolved = path.resolve()
    if root not in resolved.parents:
        raise ValueError("Cleanup path escapes workspace: {}".format(path))
    # Refuse linked descendants so recursive cleanup cannot affect another tree.
    if path.exists():
        for parent, dirs, files in os.walk(path, followlinks=False):
            for name in dirs + files:
                child = Path(parent) / name
                if child.is_symlink() or getattr(child, "is_junction", lambda: False)() or child.resolve() != child.absolute():
                    raise ValueError("Linked entry blocks workspace cleanup: {}".format(child))
    return path


def rebuild_directory(path):
    path = checked_workspace_path(path)
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def rebuild_filesystem(path):
    # Preserve user rules; all partition trees and generated metadata are rebuilt.
    path = checked_workspace_path(path)
    path.mkdir(parents=True, exist_ok=True)
    config = path / "config"
    if config.exists() and not config.is_dir():
        raise ValueError("Filesystem config path is not a directory: {}".format(config))
    for child in path.iterdir():
        if child == config:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    config.mkdir(exist_ok=True)
    for child in config.iterdir():
        if child.name in ("fs_special.conf", "fc_special.conf"):
            if not child.is_file():
                raise ValueError("Custom rule is not a file: {}".format(child))
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def incomplete_marker(path):
    return Path(path).with_name(Path(path).name + ".incomplete")


def payload_is_usable(path):
    path = Path(path)
    required = ("system", "system_ext", "product", "mi_ext") if path == SRC_UNPACK else ("odm", "vendor")
    return all((path / (part + ".img")).is_file()
               and (path / (part + ".img")).stat().st_size > 0 for part in required)


def extract_archive(archive, out_dir, label):
    info("Processing {} archive: {}".format(label, archive.name))
    rc = run_tool([str(SZ), "x", str(archive), "-o" + str(out_dir), "-y"],
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    if rc != 0:
        err("Extract failed: {}".format(archive.name))
        log_write("ERROR: extract failed: {} (rc={})".format(archive.name, rc))
        return 1
    return 0


# ---------------- Step 3 payload 解包 ----------------
REQUIRED_PAYLOAD_IMAGES = {
    "system.img",
    "system_ext.img",
    "product.img",
    "vendor.img",
    "odm.img",
}


def check_payload_extracted(target_dir):
    target_dir = Path(target_dir)
    if not target_dir.exists():
        return False
    found = {p.name.lower() for p in target_dir.rglob("*.img") if p.is_file()}
    if len(found) >= 6 and REQUIRED_PAYLOAD_IMAGES.issubset(found):
        info("Already extracted ({} partition images, required partitions present), skipping.".format(
            len(found)))
        return True
    return False


def detect_rom_format(rom_dir):
    """识别解压后 ROM 的格式，返回 (format, payload_path)"""
    # 1. A/B OTA
    for f in rom_dir.rglob("payload.bin"):
        return "payload", f
    # 2. block OTA（.dat / .dat.br / .dat.xz / 分卷）
    block_patterns = ["*.transfer.list", "*.new.dat", "*.new.dat.br",
                      "*.new.dat.xz", "*.new.dat.1"]
    if any(True for p in block_patterns for _ in rom_dir.rglob(p)):
        return "block_dat", None
    # 3. 已经存在 .img
    return "img", None


def extract_payload_bin(rom_dir, out_dir):
    rom_dir = Path(rom_dir)
    out_dir = Path(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    fmt, payload_file = detect_rom_format(rom_dir)

    if fmt == "payload":
        info("Found payload.bin (A/B OTA), extracting...")
        cmd = [str(PDUMP), "-o", str(out_dir), str(payload_file)]
        if AUTO_MODE:
            proc = run_tool(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            errors="replace")
            rc = proc.returncode
        else:
            rc = run_tool(cmd).returncode
        if rc != 0:
            err("payload-dumper-go failed")
            if AUTO_MODE and proc.stdout:
                tail = "\n".join(proc.stdout.strip().splitlines()[-30:])
                print(tail, flush=True)
                log_write(tail)
            return 1
        info("Payload extracted to: {}".format(out_dir))
        for f in sorted(out_dir.glob("*.img")):
            mb = round(f.stat().st_size / 1024 / 1024, 1)
            info("  {}.img  {} MB".format(f.stem, mb))
        return 0

    if fmt == "block_dat":
        # block OTA（.dat / .dat.br / .dat.xz / 分卷）→ 转换为 .img
        info("Found block OTA (.dat/.dat.br), converting to .img...")
        rc = run_tool([PY, str(TOOLS / "extract_dat.py"),
                       str(rom_dir), str(out_dir)]).returncode
        if rc != 0:
            err("block OTA .dat conversion failed")
            log_write("ERROR: extract_dat.py failed")
            return 1
        info("block OTA .dat partition(s) converted to .img")
        return 0

    # fmt == "img"：没有 payload.bin 和 .dat，直接复制已有的 .img
    info("No payload.bin / .dat found, copying existing .img files...")
    count = 0
    fail = 0
    for f in rom_dir.rglob("*.img"):
        count += 1
        try:
            shutil.copy2(f, out_dir / f.name)
        except Exception as e:
            err("Failed to copy {}: {}".format(f.name, e))
            log_write("ERROR: copy {} failed: {}".format(f.name, e))
            fail += 1
    info("Copied {} img file(s)".format(count))
    if count == 0:
        err("No .img files found in {}".format(rom_dir))
        log_write("ERROR: no .img files found in {}".format(rom_dir))
        return 1
    return 1 if fail else 0


# ---------------- Step 4 镜像解包 ----------------
def unpack_all_img(img_dir, out_dir, label):
    img_dir = Path(img_dir)
    out_dir = Path(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    fail = 0
    for part in UNPACK_PARTS:
        img = img_dir / (part + ".img")
        if img.exists():
            info("Processing {}.img ...".format(part))
            os.makedirs(out_dir / part, exist_ok=True)
            rc = run_tool([PY, str(TOOLS / "extract_img.py"), str(img), str(out_dir / part)]).returncode
            if rc != 0:
                err("Failed to extract {}.img".format(part))
                log_write("ERROR: extract {}.img failed (rc={})".format(part, rc))
                fail += 1
            else:
                info("{}.img extracted".format(part))
    if fail:
        err("{}/{} image(s) failed to unpack".format(fail, len(UNPACK_PARTS)))
        return 1
    return 0


# ---------------- Step 5 注入 adb debug ----------------
def inject_adb_debug(pack_cfg):
    if pack_cfg.get("enable_adb_debug", "false").lower() != "true":
        return
    target_prop = TGT_FS / "odm" / "etc" / "build.prop"
    if not target_prop.exists():
        err("enable_adb_debug=true but odm build.prop not found")
        log_write("WARNING: adb debug inject skipped, build.prop not found")
        return
    try:
        content = target_prop.read_text(encoding="utf-8", errors="replace")
    except Exception:
        content = ""
    if "# XMAport adb debug" in content:
        info("adb debug props already injected, skipping")
        log_write("adb debug props already present, skip")
        return
    lines = [
        "# XMAport adb debug",
        "ro.debuggable=1",
        "ro.secure=0",
        "ro.adb.secure=0",
        "persist.sys.usb.config=adb",
        "persist.adb.notify=0",
        "service.adb.root=1",
        "persist.sys.root_access=3",
    ]
    with open(target_prop, "a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
    info("adb debug props injected into odm build.prop")
    log_write("adb debug props injected: {}".format(target_prop))


# ---------------- vbmeta 禁验 ----------------
def patch_vbmeta(pack_cfg):
    if pack_cfg.get("patch_vbmeta", "true").lower() != "true":
        return
    log_write("Patching vbmeta (disable AVB verification)")
    info("Patching vbmeta images (disable AVB verification)...")
    count = 0
    for f in sorted(TGT_UNPACK.glob("vbmeta*.img")):
        if f.exists():
            try:
                shutil.copy2(f, PACK_OUT / f.name)
            except Exception:
                err("failed to copy: {}".format(f.name))
                log_write("ERROR: copy failed: {}".format(f.name))
                continue
            if (PACK_OUT / f.name).exists():
                info("vbmeta copied: {}".format(f.name))
                log_write("vbmeta copied: {}".format(f.name))
                count += 1
    if count == 0:
        err("No vbmeta*.img found in target payload")
        log_write("WARNING: no vbmeta*.img in target_payload, skip patching")
        return
    rc = subprocess.run([PY, str(TOOLS / "vbmeta_patch.py"), str(PACK_OUT)]).returncode
    if rc != 0:
        err("vbmeta patch reported errors")
        log_write("WARNING: vbmeta_patch.py reported errors")
    else:
        info("vbmeta patch done")
        log_write("vbmeta patched successfully")


def _append_lpc_entry(lpc_args, part, img_path, size, pack_cfg):
    # 与 R3 版(20260811)完全一致：readonly 写死
    lpc_args.append("--partition={}:readonly:{}:{}".format(
        part, size, pack_cfg.get("super_group", "main")))
    lpc_args.append("--image={}={}".format(part, img_path))


# ---------------- Step 6 分区打包辅助 ----------------
def pack_one_partition(part, fs_dir, pack_cfg, lpc_args, counters):
    src = fs_dir / part
    if not src.exists():
        return
    info("Packing partition: {}".format(part))
    log_write("Packing {}...".format(part))
    cmd = [
        PY, str(TOOLS / "pack_partitions.py"),
        pack_cfg["format"],
        "{},{}".format(pack_cfg["compression"], pack_cfg["compression_level"]),
        str(src),
        str(PACK_OUT),
    ]
    rc = run_tool(cmd).returncode
    out_img = PACK_OUT / (part + ".img")
    if rc != 0:
        err("{}: pack_partitions.py failed".format(part))
        log_write("ERROR: {} packing failed".format(part))
        counters["pack_fail"] += 1
        return
    if not out_img.exists():
        err("{}: output image not found".format(part))
        log_write("ERROR: {}.img not generated".format(part))
        counters["pack_fail"] += 1
        return
    size = out_img.stat().st_size
    info("{}.img packed, {} bytes".format(part, size))
    log_write("{}.img packed: {} bytes".format(part, size))
    _append_lpc_entry(lpc_args, part, out_img, size, pack_cfg)
    counters["pack_ok"] += 1


def copy_partition_image(part, src_file, pack_cfg, lpc_args, counters):
    # 从 payload 镜像直接复制到 packed（mi_ext / vendor / vendor_dlkm）
    if not src_file.exists():
        err("{}.img not found in payload".format(part))
        log_write("ERROR: {}.img not found in payload".format(part))
        counters["pack_fail"] += 1
        pause()
        return
    try:
        shutil.copy2(src_file, PACK_OUT / src_file.name)
    except Exception as e:
        err("{}.img copy failed: {}".format(part, e))
        log_write("ERROR: {}.img copy failed: {}".format(part, e))
        counters["pack_fail"] += 1
        pause()
        return
    if not (PACK_OUT / src_file.name).exists():
        err("{}.img copy failed".format(part))
        log_write("ERROR: {}.img copy failed (output missing)".format(part))
        counters["pack_fail"] += 1
        pause()
        return
    size = (PACK_OUT / src_file.name).stat().st_size
    info("{}.img ready, {} bytes".format(part, size))
    log_write("{}.img ready: {} bytes".format(part, size))
    _append_lpc_entry(lpc_args, part, PACK_OUT / src_file.name, size, pack_cfg)
    counters["pack_ok"] += 1


def create_super_img(pack_cfg, lpc_args, pack_ok):
    # lpmake 生成 super.img，返回 0=成功/跳过, 1=空间不足, 2=其他错误
    if pack_cfg.get("pack_super", "false").lower() != "true":
        return 0
    if pack_ok == 0:
        err("No partitions packed, skipping super.img.")
        log_write("WARNING: No partitions packed, super.img skipped")
        return 0
    info("Creating super.img...")
    cmd = [
        str(LPM),
        "--metadata-size", pack_cfg["metadata_size"],
        "--super-name", pack_cfg["super_name"],
        "--metadata-slots", pack_cfg["metadata_slots"],
        "--device", "{}:{}".format(pack_cfg["super_name"], pack_cfg["device_size"]),
        "--group", "{}:{}".format(pack_cfg["super_group"], pack_cfg["device_size"]),
    ]
    cmd += lpc_args
    if pack_cfg.get("virtual_ab", "true").lower() == "true":
        cmd.append("--virtual-ab")
    if pack_cfg.get("sparse", "true").lower() == "true":
        cmd.append("--sparse")
    cmd += ["--output=" + str(PACK_OUT / "super.img")]
    info("lpmake command: " + subprocess.list2cmdline(cmd))
    # lpmake 日志实时滚屏（不吞日志），同时逐行留档用于失败分类；
    # 10 分钟看门狗防止 lpmake 卡死。
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            errors="replace")
    timed_out = False

    def _kill_lpmake():
        nonlocal timed_out
        timed_out = True
        try:
            proc.kill()
        except Exception:
            pass

    watchdog = threading.Timer(TOOL_TIMEOUT, _kill_lpmake)
    watchdog.start()
    output_lines = []
    try:
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            output_lines.append(line)
        proc.wait()
    finally:
        watchdog.cancel()
    rc = proc.returncode
    output = "".join(output_lines)
    if timed_out:
        err("lpmake timed out after {} minutes".format(TOOL_TIMEOUT // 60))
        log_write("ERROR: lpmake timed out after {} seconds".format(TOOL_TIMEOUT))
        return 2
    if rc != 0:
        lower = output.lower()
        if any(kw in lower for kw in ["exceeds", "not enough", "no space", "too large", "overflow", "size limit"]):
            m = re.search(r"partition\s+(\S+)\s+with\s+size\s+(\d+)", lower)
            if m:
                err("lpmake failed: super space insufficient (partition={}, size={})".format(
                    m.group(1), m.group(2)))
                log_write("ERROR: lpmake failed - super space insufficient (partition={}, size={})".format(
                    m.group(1), m.group(2)))
            else:
                err("lpmake failed: super space insufficient")
                log_write("ERROR: lpmake failed - super space insufficient")
            return 1
        err("lpmake failed (full log above)")
        log_write("ERROR: lpmake failed to create super.img (rc={})".format(rc))
        pause()
        return 2
    log_write("super.img created successfully")
    if pack_cfg.get("sparse", "true").lower() == "true":
        info("sparse super.img created directly by lpmake")
    sup = PACK_OUT / "super.img"
    if sup.exists():
        info("super.img created, {} bytes".format(sup.stat().st_size))
    return 0


def _abort_port(auto, msg):
    # 流水线中途失败的统一出口：auto 直接返回失败码；交互提示后回菜单
    err(msg)
    log_write("ERROR: {}".format(msg))
    if auto:
        return 1
    pause()
    raise ReturnToMenu()


# ---------------- 一键移植流水线 ----------------
def one_click_port(auto=False):
    global TARGET_DEVICE

    tool_status(pause_after=False)
    if not auto:
        pause_seconds(3)

    os.system("cls" if os.name == "nt" else "clear")
    log_write("========== XMAport Session Start ==========")
    log_write("Target Device: {}".format(TARGET_DEVICE))
    print()
    print("  {}{}============================================================{}".format(C, BD, N))
    print("  {}{}  One-Click HyperOS Porting{}".format(C, BD, N))
    print("  {}{}============================================================{}".format(C, BD, N))
    print()
    print("  {}  Workflow:{}".format(W, N))
    print("  {}    Step 1{}  Download ROM packages".format(G, N))
    print("  {}    Step 2{}  Extract archives".format(G, N))
    print("  {}    Step 3{}  Extract payload (payload.bin/.dat)".format(G, N))
    print("  {}    Step 4{}  Unpack partition images".format(G, N))
    print("  {}    Step 5{}  Migrate & patch".format(G, N))
    print("  {}    Step 6{}  Pack partitions + super.img".format(G, N))
    print("  {}    Step 7{}  Summary & output".format(G, N))
    print()
    print("  " + D + "----------------------------------------------------------" + N)
    print()

    # 读取配置
    try:
        read_config()
    except ReturnToMenu:
        if auto:
            err("config.ini not found, cannot continue in auto mode")
            log_write("ERROR: config.ini missing, auto mode aborted")
            return 1
        raise
    pack_cfg = read_packing_config()

    # 输入/读取目标设备代号
    cfg_txt = WORKSPACE / "config.txt"
    if CLI_DEVICE:
        TARGET_DEVICE = CLI_DEVICE.strip()
        info("Device codename from --device: {}".format(TARGET_DEVICE))
    elif cfg_txt.exists():
        for line in cfg_txt.read_text(encoding="gbk", errors="ignore").splitlines():
            if line.startswith("TARGET_DEVICE="):
                TARGET_DEVICE = line.split("=", 1)[1].strip()
                break
    elif auto:
        err("Target device codename not provided (--device) and config.txt missing")
        log_write("ERROR: no device codename in auto mode")
        return 1
    else:
        print("  {}  Enter target device codename:{}".format(W, N))
        print("  {}  (e.g. sheng, fuxi, cupid, mondrian){}".format(D, N))
        TARGET_DEVICE = prompt("  > ").strip()

    if not is_safe_device_name(TARGET_DEVICE):
        err("Invalid device codename: only A-Z, a-z, 0-9, underscore and hyphen are allowed")
        log_write("ERROR: unsafe device codename rejected: {}".format(TARGET_DEVICE))
        if auto:
            return 1
        pause()
        raise ReturnToMenu()
    cfg_txt.write_text("TARGET_DEVICE={}\n".format(TARGET_DEVICE), encoding="gbk")

    print("  {}  Source URL:   {}{}{}".format(W, C, SRC_URL[:50], N))
    print("  {}  Target URL:   {}{}{}".format(W, C, TGT_URL[:50], N))
    print("  {}  Device:   {}{}{}".format(W, G, TARGET_DEVICE, N))
    print("  {}  Format:    {}{}{}  Compression: {}{} level {}{}  Pack super: {}{}{}".format(
        W, G, pack_cfg["format"], N, G, pack_cfg["compression"], pack_cfg["compression_level"], N,
        G, pack_cfg["pack_super"], N))
    print()
    if not auto:
        confirm = prompt("  {}Are These Right? (Y/N): {}".format(Y, N))
        if confirm.strip().lower() != "y":
            raise ReturnToMenu()
    else:
        info("Auto mode: skipping confirmation, proceeding...")

    # ---------------- Step 1: 下载（两包并行） ----------------
    info("=== Step 1/7: Download ROM ===")
    log_write("Step 1: Download ROM start")
    log_write("Source URL: {}".format(SRC_URL))
    log_write("Target URL: {}".format(TGT_URL))
    jobs = []
    if SRC_URL:
        jobs.append((SRC_URL, SRC_DL, "SourceROM"))
    if TGT_URL:
        jobs.append((TGT_URL, TGT_DL, "TargetROM"))
    if jobs:
        results = download_roms(jobs)
        failed = [name for name, rc in results.items() if rc != 0]
        if failed:
            err("Step 1 failed: {} download".format(" / ".join(failed)))
            log_write("ERROR: Step 1 download failed: {}".format(", ".join(failed)))
            if auto:
                return 1
            pause()
            raise ReturnToMenu()
        for d in [SRC_DL, TGT_DL]:
            try:
                for f in sorted(d.iterdir()):
                    if f.is_file():
                        info("  {}  {} bytes".format(f.name, f.stat().st_size))
            except Exception:
                pass
    info("Step 1 done")
    log_write("Step 1: Download ROM done")

    # Resolve both inputs before touching extracted data.
    try:
        source_archive = select_archive(SRC_URL, SRC_DL)
        target_archive = select_archive(TGT_URL, TGT_DL)
    except (OSError, ValueError) as exc:
        return _abort_port(auto, "Input selection failed: {}".format(exc))
    sides = [("Source", source_archive, SRC_ROM, SRC_UNPACK, SRC_FS),
             ("Target", target_archive, TGT_ROM, TGT_UNPACK, TGT_FS)]
    # A failed extraction is never silently reused. Recover using an archive.
    for label, archive, rom, payload, filesystem in sides:
        if archive is None and incomplete_marker(payload).exists():
            return _abort_port(auto, "{} extraction incomplete; provide a ROM package to rebuild.".format(label))

    info("=== Step 2/7: Extract archives ===")
    log_write("Step 2: Extract archives start")
    for label, archive, rom, payload, filesystem in sides:
        if archive is None:
            info("{}: no URL/local archive, reusing existing payload or ROM.".format(label))
            continue
        try:
            incomplete_marker(payload).write_text("archive extraction started\n", encoding="ascii")
            rebuild_directory(rom)
            if extract_archive(archive, rom, label) != 0:
                return _abort_port(auto, "Step 2 failed: {} archive extraction".format(label))
        except (OSError, ValueError) as exc:
            return _abort_port(auto, "Step 2 failed: {}: {}".format(label, exc))
    log_write("Step 2: Extract archives done")

    info("=== Step 3/7: Extract payload ===")
    log_write("Step 3: Extract payload start")
    for label, archive, rom, payload, filesystem in sides:
        if archive is None and payload_is_usable(payload):
            info("{}: reusing partition images.".format(label))
            continue
        try:
            incomplete_marker(payload).write_text("payload extraction started\n", encoding="ascii")
            rebuild_directory(payload)
            if extract_payload_bin(rom, payload) != 0 or not payload_is_usable(payload):
                return _abort_port(auto, "Step 3 failed: {} payload extraction or required images missing/empty".format(label))
            incomplete_marker(payload).unlink()
        except (OSError, ValueError) as exc:
            return _abort_port(auto, "Step 3 failed: {}: {}".format(label, exc))
    log_write("Step 3: Extract payload done")

    info("=== Step 4/7: Unpack IMG ===")
    log_write("Step 4: Unpack IMG start")
    for label, archive, rom, payload, filesystem in sides:
        try:
            rebuild_filesystem(filesystem)
            if unpack_all_img(payload, filesystem, label) != 0:
                return _abort_port(auto, "Step 4 failed: {} image unpack".format(label))
        except (OSError, ValueError) as exc:
            return _abort_port(auto, "Step 4 failed: {}: {}".format(label, exc))
    log_write("Step 4: Unpack IMG done")

    # ---------------- Step 5: 迁移 ----------------
    info("=== Step 5/7: Migrate ===")
    log_write("Step 5: Migrate start")
    migrate_ok = 0
    migrate_fail = 0
    mh = TOOLS / "make_hyper.py"
    rc = run_tool([PY, str(mh), "speed"]).returncode if mh.exists() else 1
    if rc == 0:
        migrate_ok += 1
        log_write("make_hyper.py speed: SUCCESS")
    else:
        migrate_fail += 1
        return _abort_port(auto, "Step 5 failed: make_hyper.py speed returned an error (rc={})".format(rc))
    info("Step 5 done. Success: {} , Fail: {}".format(migrate_ok, migrate_fail))
    log_write("Step 5: Migrate done (OK={}, Fail={})".format(migrate_ok, migrate_fail))

    # 注入 adb debug 属性
    inject_adb_debug(pack_cfg)

    # ---------------- Step 6: 打包分区 + super ----------------
    info("=== Step 6/7: Pack partitions ===")
    info("Format: {} , Compression: {} level {}".format(
        pack_cfg["format"], pack_cfg["compression"], pack_cfg["compression_level"]))
    info("Cleaning packed directory...")
    try:
        for old in PACK_OUT.glob("*.img"):
            old.unlink()
    except OSError as exc:
        return _abort_port(auto, "Step 6 failed: cannot remove old packed image: {}".format(exc))

    # 传递打包环境变量给 pack_partitions.py
    os.environ["XMAPORT_UTC_STAMP"] = str(pack_cfg.get("utc_stamp", ""))
    os.environ["XMAPORT_EROFS_LEGACY"] = str(pack_cfg.get("erofs_old_kernel", "false"))
    os.environ["XMAPORT_IS_SKIP_APEX"] = str(pack_cfg.get("is_skip_apex", "false"))
    sync_status = WORKSPACE / "sync_apex_changed.txt"
    sync_apex_changed = "false"
    try:
        sync_apex_changed = sync_status.read_text(encoding="ascii").strip().lower()
    except Exception:
        pass
    os.environ["XMAPORT_SYNC_APEX_CHANGED"] = "true" if sync_apex_changed == "true" else "false"
    os.environ["XMAPORT_USE_LEGACY_EROFS"] = detect_legacy_erofs_marker()

    # 打包前校验分区镜像格式（只警告不阻断）
    info("Checking original partition image formats...")
    try:
        subprocess.run([
            PY, str(TOOLS / "check_img_format.py"), pack_cfg["format"],
            str(SRC_UNPACK / "system.img"), str(SRC_UNPACK / "system_ext.img"),
            str(SRC_UNPACK / "product.img"), str(TGT_UNPACK / "odm.img"),
        ])
    except Exception:
        pass
    log_write("Partition image format check done (expected: {})".format(pack_cfg["format"]))

    counters = {"pack_ok": 0, "pack_fail": 0}
    port_failed = False
    lpc_args = []

    # 打包源分区 system / system_ext / product
    log_write("Packing source partitions: system, system_ext, product")
    is_skip_apex = pack_cfg.get("is_skip_apex", "false").lower() == "true"
    for part in PACK_SOURCE_PARTS:
        if part == "system_ext" and is_skip_apex:
            info("is_skip_apex=true: system_ext 跳过重新打包，将直接复制源 payload")
            continue
        pack_one_partition(part, SRC_FS, pack_cfg, lpc_args, counters)

    # is_skip_apex=true 时直接复制源 system_ext.img
    if is_skip_apex:
        log_write("Copying source system_ext.img (is_skip_apex=true)")
        copy_partition_image("system_ext", SRC_UNPACK / "system_ext.img", pack_cfg, lpc_args, counters)

    # 打包目标 odm（始终运行）
    log_write("Packing odm from target filesystem")
    info("Packing partition: odm")
    if (TGT_FS / "odm").exists():
        pack_one_partition("odm", TGT_FS, pack_cfg, lpc_args, counters)
    else:
        err("odm not found in target filesystem")
        log_write("ERROR: odm not found in target filesystem")
        counters["pack_fail"] += 1
        port_failed = True
        pause()

    # 复制 mi_ext（源 payload）
    log_write("Copying mi_ext from source payload")
    info("Adding mi_ext from source payload...")
    copy_partition_image("mi_ext", SRC_UNPACK / "mi_ext.img", pack_cfg, lpc_args, counters)

    # 处理 vendor：MTK 从 target filesystem 重新打包；高通直接复制目标 payload
    device_platform = pack_cfg.get("device_platform", "qualcomm").lower()
    if device_platform == "mtk":
        # unpack_all_img 不包含 vendor，需补充解包到 target_filesystem
        if not (TGT_FS / "vendor").exists():
            log_write("MTK: extracting vendor.img to target filesystem")
            info("Extracting vendor.img for MTK vendor repack...")
            img = TGT_UNPACK / "vendor.img"
            if img.exists():
                os.makedirs(TGT_FS / "vendor", exist_ok=True)
                run_tool([PY, str(TOOLS / "extract_img.py"), str(img), str(TGT_FS / "vendor")])
        log_write("Packing vendor from target filesystem (MTK)")
        info("Packing partition: vendor (MTK)")
        if (TGT_FS / "vendor").exists():
            pack_one_partition("vendor", TGT_FS, pack_cfg, lpc_args, counters)
        else:
            err("vendor not found in target filesystem")
            log_write("ERROR: vendor not found in target filesystem")
            counters["pack_fail"] += 1
            port_failed = True
            pause()
    else:
        log_write("Copying vendor from target payload")
        info("Adding vendor from target payload...")
        copy_partition_image("vendor", TGT_UNPACK / "vendor.img", pack_cfg, lpc_args, counters)

    # 复制 vendor_dlkm（目标 payload）
    if (TGT_UNPACK / "vendor_dlkm.img").exists():
        copy_partition_image("vendor_dlkm", TGT_UNPACK / "vendor_dlkm.img", pack_cfg, lpc_args, counters)

    # 生成 super.img；空间不足(rc=1)时自动极限精简 → 重打包 product → 重试一次
    log_write("Creating super.img (pack_super={})".format(pack_cfg.get("pack_super", "false")))
    super_rc = create_super_img(pack_cfg, lpc_args, counters["pack_ok"])
    if super_rc == 1:
        info("Triggering extreme slimming mode (make_hyper.py extreme)...")
        log_write("Super space insufficient, running extreme slimming")
        if run_tool([PY, str(TOOLS / "make_hyper.py"), "extreme"]).returncode != 0:
            port_failed = True
            err("make_hyper.py extreme failed, super.img not retried")
            log_write("ERROR: make_hyper.py extreme failed")
        else:
            info("Re-packing product partition after extreme slimming...")
            lpc_args[:] = [a for a in lpc_args
                           if not a.startswith("--partition=product:")
                           and not a.startswith("--image=product=")]
            try:
                (PACK_OUT / "product.img").unlink()
            except Exception:
                pass
            pack_one_partition("product", SRC_FS, pack_cfg, lpc_args, counters)
            info("Retrying super.img creation...")
            log_write("Retrying super.img after extreme slimming")
            super_rc = create_super_img(pack_cfg, lpc_args, counters["pack_ok"])
            if super_rc != 0:
                port_failed = True
                err("super.img retry failed (rc={})".format(super_rc))
                log_write("ERROR: super.img retry failed (rc={})".format(super_rc))
    elif super_rc != 0:
        port_failed = True
        err("super.img creation failed (rc={})".format(super_rc))
        log_write("ERROR: super.img creation failed (rc={})".format(super_rc))

    # vbmeta 禁验（在 super 打包之后、汇总之前，不受 pack_super 限制）
    patch_vbmeta(pack_cfg)

    # ---------------- Step 7: 汇总 ----------------
    port_ok = (not port_failed) and counters["pack_fail"] == 0
    log_write("========== Porting {} ==========".format(
        "Complete" if port_ok else "Finished With Errors"))
    log_write("Total packed: {} partitions, {} failed".format(counters["pack_ok"], counters["pack_fail"]))
    log_write("Step 6: Pack partitions done")
    log_write("Pack OK={}, Fail={}".format(counters["pack_ok"], counters["pack_fail"]))
    print()
    print("  {}{}============================================================{}".format(C, BD, N))
    if port_ok:
        print("  {}{}Porting Complete!{}".format(G, BD, N))
    else:
        print("  {}{}Porting Finished With Errors!{}".format(R, BD, N))
    print("  {}{}============================================================{}".format(C, BD, N))
    print()
    if not port_ok:
        print("  {}  Pack OK={}, Fail={} -- check workspace log for details{}".format(
            Y, counters["pack_ok"], counters["pack_fail"], N))
        print()
    print("  {}  Source FS:    {}{}{}".format(W, C, SRC_FS, N))
    print("  {}  Target FS:    {}{}{}".format(W, C, TGT_FS, N))
    print("  {}  Output:       {}{}{}".format(W, C, str(PACK_OUT / "super.img"), N))
    print()
    for part in ALL_OUTPUT_PARTS:
        img = PACK_OUT / (part + ".img")
        if img.exists():
            print("  {}    {}.img  {} bytes{}".format(G, part, img.stat().st_size, N))

    # ROM Info（从源分区 build.prop 读取）
    rom_info_lines = []
    print()
    rom_info_lines.append("---------- ROM Info ----------")
    print("  {}  ---------- ROM Info ----------{}".format(C, N))
    bp_candidates = [
        SRC_FS / "odm" / "etc" / "build.prop",
        SRC_FS / "product" / "etc" / "build.prop",
        SRC_FS / "system" / "system" / "build.prop",
    ]
    bp_path = None
    for cand in bp_candidates:
        if cand.exists():
            bp_path = cand
            break
    if bp_path is None:
        print("  {}  [ERR] build.prop not found{}".format(R, N))
        rom_info_lines.append("[ERR] build.prop not found")
    else:
        try:
            props_text = bp_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            props_text = ""
        for key in [
            "ro.product.odm.device", "ro.product.odm.model",
            "ro.product.odm.marketname", "ro.product.odm.brand",
            "ro.product.odm.name", "ro.product.odm.manufacturer",
        ]:
            label = key.split(".")[-1]
            if label == "manufacturer":
                label = "vendor"
            for line in props_text.splitlines():
                if "=" in line and line.split("=", 1)[0].strip() == key:
                    val = line.split("=", 1)[1].strip()
                    print("  {}  {}: {}{}{}".format(W, label.ljust(10), C, val, N))
                    rom_info_lines.append("{}: {}".format(label, val))
                    break
    print("  {}  ------------------------------{}".format(C, N))
    rom_info_lines.append("-------------------------------")
    if AUTO_MODE:
        try:
            (WORKSPACE / "rom_info.txt").write_text(
                "\n".join(rom_info_lines), encoding="utf-8")
        except Exception:
            pass
    print()
    print("  {}{}============================================================{}".format(C, BD, N))
    print()
    if not auto:
        pause()
    return 0 if port_ok else 1


# ---------------- 全局崩溃报告 ----------------
def crash_report(exc_type, exc, tb):
    # KeyboardInterrupt 不算崩溃
    if exc_type is KeyboardInterrupt:
        print()
        sys.exit(0)
    lineno = "?"
    module = "?"
    if tb is not None:
        while tb.tb_next is not None:
            tb = tb.tb_next
        lineno = tb.tb_lineno
        module = tb.tb_frame.f_globals.get("__name__", "?")
    details = [
        "",
        "  {}============================================================{}".format(R, N),
        "  {}  XMAPORT CRASHED{}".format(R, N),
        "  {}============================================================{}".format(R, N),
        "  {}  Error type:{} {}".format(W, Y, exc_type.__name__ + N),
        "  {}  Message:   {}{}".format(W, C, str(exc) + N),
        "  {}  Location:  {}{}:{}".format(W, D, module, str(lineno) + N),
        "  {}  Platform:  {}{}".format(W, D, platform.platform() + N),
        "  {}  Python:    {}{}".format(W, D, sys.version.split()[0] + N),
        "  {}  Details have been written to the log file{}".format(Y, N),
        "  {}============================================================{}".format(R, N),
        "",
    ]
    for line in details:
        try:
            print(line, flush=True)
        except Exception:
            pass
    log_write("CRASH: {}: {} ({}:{})".format(exc_type.__name__, exc, module, lineno))


sys.excepthook = crash_report


# ---------------- [A] 命令执行器 ----------------
def compose_super():
    # 用 workspace/packed 现有分区镜像合成 super.img：
    # 检测 packed 分区 → 从 config.ini 读取 super 参数 → lpmake 合成。
    os.system("cls" if os.name == "nt" else "clear")
    print()
    print("  {}{}============================================================{}".format(C, BD, N))
    print("  {}{}  Compose super.img{}".format(C, BD, N))
    print("  {}{}============================================================{}".format(C, BD, N))
    print()
    pack_cfg = read_packing_config()
    lpc_args = []
    counters = {"pack_ok": 0, "pack_fail": 0}
    found = []
    for part in ALL_OUTPUT_PARTS:
        img = PACK_OUT / (part + ".img")
        if img.exists():
            _append_lpc_entry(lpc_args, part, img, img.stat().st_size, pack_cfg)
            counters["pack_ok"] += 1
            found.append("{}  {} bytes".format(part + ".img", img.stat().st_size))
    if not found:
        err("No packed partition images found in workspace\\packed")
        err("Run a port first (menu [1]), then compose super.img here")
        log_write("compose_super aborted: no partition images in packed")
        pause()
        return
    print("  {}  Partitions found in packed:{}{}".format(W, G, N))
    for line in found:
        print("  {}    - {}{}".format(W, line, N))
    print("  {}  super: device_size={}  metadata={}/{} slots  group={}  virtual_ab={}  sparse={}".format(
        W, pack_cfg.get("device_size", "?"), pack_cfg.get("metadata_size", "?"),
        pack_cfg.get("metadata_slots", "?"), pack_cfg.get("super_group", "?"),
        pack_cfg.get("virtual_ab", "?"), pack_cfg.get("sparse", "?"), N))
    print()
    try:
        (PACK_OUT / "super.img").unlink()
    except Exception:
        pass
    # create_super_img 内部按 pack_super 配置决定是否跳过，此处强制执行合成
    pack_cfg["pack_super"] = "true"
    rc = create_super_img(pack_cfg, lpc_args, counters["pack_ok"])
    sup = PACK_OUT / "super.img"
    if rc == 0 and sup.exists():
        print()
        print("  {}  super.img ready: {} bytes{}".format(G, sup.stat().st_size, N))
        log_write("compose_super OK: {} bytes".format(sup.stat().st_size))
    elif rc == 1:
        # 单独合成时不自动触发极限精简重试，只提醒用户
        print()
        err("super space insufficient, compose aborted")
        print("  {}  Tip: run extreme slimming (python tools/make_hyper.py extreme),{}"
              .format(Y, N))
        print("  {}  then re-pack and re-run this compose, or enlarge device_size in config.ini{}".format(Y, N))
        log_write("compose_super: super space insufficient (rc=1), no auto retry")
    elif rc != 0:
        log_write("compose_super failed: rc={}".format(rc))
    pause()


def show_executor():
    os.system("cls" if os.name == "nt" else "clear")
    print()
    print("  {}{}============================================================{}".format(C, BD, N))
    print("  {}{}  Command Executor{}".format(C, BD, N))
    print("  {}{}============================================================{}".format(C, BD, N))
    print()
    print("  {}  [1] Compose super.img{}".format(W, N))
    print("  {}      Pack existing partitions in workspace\\packed into super.img{}".format(D, N))
    print("  {}  [0] Back{}".format(W, N))
    print()
    ch = prompt("  {}Select [0-1]: {}".format(Y, N)).strip()
    if ch == "1":
        compose_super()


# ---------------- 主菜单 ----------------
def print_banner():
    print()
    print("  {}{}============================================================{}".format(C, BD, N))
    print("  {}{}    __   __ __  __     _     ____    ___   ____   _____ {}".format(C, BD, N))
    print("  {}{}    \\ \\ / /|  \\/  |   / \\   |  _ \\  / _ \\ |  _ \\ |_   _|{}".format(C, BD, N))
    print("  {}{}     \\ V / | |\\/| |  / _ \\  | |_) || | | || |_) |  | |  {}".format(C, BD, N))
    print("  {}{}     /   \\ | |  | | / ___ \\ |  __/ | |_| ||  _ <   | |  {}".format(C, BD, N))
    print("  {}{}    /_/ \\_\\|_|  |_|/_/   \\_\\|_|     \\___/ |_| \\_\\  |_|  {}".format(C, BD, N))
    print("  {}{}============================================================{}".format(C, BD, N))


def show_menu():
    os.system("cls" if os.name == "nt" else "clear")
    print_banner()
    print()
    print("  {}{}  [1] One-Click Port HyperOS{}     {}Full auto workflow{}".format(G, BD, N, D, N))
    print()
    print("  {}{}  -- Tools --{}".format(Y, BD, N))
    print("  {}  [A] Command Executor{}".format(W, N))
    print("  {}  [C] Open-Source Credits{}".format(W, N))
    print("  {}  [D] Clean workspace{}".format(W, N))
    print()
    print("  {}{}============================================================{}".format(C, BD, N))
    print()
    choice = prompt("  {}{}Select [1, A-D]: {}".format(Y, BD, N))
    return choice.strip().lower()


# ---------------- CLI 参数解析 ----------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="XMAPort - Android ROM porting tool",
    )
    parser.add_argument("--auto", action="store_true",
                        help="Non-interactive mode for CI/GitHub Actions")
    parser.add_argument("--device", default="",
                        help="Target device codename (overrides config.txt)")
    parser.add_argument("--source", default="",
                        help="Source ROM URL (overrides config.ini [source] url)")
    parser.add_argument("--target", default="",
                        help="Target ROM URL (overrides config.ini [target] url)")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Skip confirmation prompts")
    return parser.parse_args()


def main():
    global CLI_SOURCE_URL, CLI_TARGET_URL, CLI_DEVICE
    args = parse_args()

    # CLI 覆盖
    CLI_SOURCE_URL = args.source
    CLI_TARGET_URL = args.target
    CLI_DEVICE = args.device

    # 初始化控制台与目录
    init_console(auto=args.auto)
    try:
        os.chdir(ROOT)
    except Exception:
        pass
    for d in ALL_DIRS:
        d.mkdir(parents=True, exist_ok=True)

    if args.auto:
        log_write("========== XMAport Auto Mode Start ==========")
        try:
            result = one_click_port(auto=True)
        except ReturnToMenu:
            err("Workflow aborted (ReturnToMenu) in auto mode")
            log_write("ERROR: auto mode aborted via ReturnToMenu")
            result = 1
        sys.exit(result if result is not None else 0)

    while True:
        try:
            ch = show_menu()
        except KeyboardInterrupt:
            print()
            break

        if ch == "1":
            try:
                one_click_port()
            except ReturnToMenu:
                continue
            except KeyboardInterrupt:
                print()
                continue
        elif ch == "a":
            show_executor()
        elif ch == "c":
            show_credits()
        elif ch == "d":
            clean_workspace()
        else:
            print("  {}  Invalid input{}".format(R, N))
            pause_seconds(1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        sys.exit(0)
