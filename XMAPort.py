#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path



R = "\x1b[91m"
G = "\x1b[92m"
Y = "\x1b[93m"
B = "\x1b[94m"      # 蓝色（保留，未在界面使用）
M = "\x1b[95m"      # 紫色（保留，未在界面使用）
C = "\x1b[96m"
W = "\x1b[97m"
D = "\x1b[90m"
N = "\x1b[0m"
BD = "\x1b[1m"

# ---------------- 控制常量 ----------------
# 调试模式：1 时打印 INFO 日志，0 时隐藏（原 bat 的 DEBUG_MODE）
DEBUG_MODE = "1"


# ---------------- 控制台准备 ----------------
def init_console():
    # Windows 上先置空 TITLE，再启用 ANSI 虚拟终端（模拟原 bat 的 reg add）
    os.system("")
    # 设置控制台窗口标题
    os.system("title XMAPort 260811.R3")
    # 防止非 UTF-8 终端下中文输出崩溃
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ---------------- 路径（脚本所在目录为根） ----------------
ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "tools"
WORKSPACE = ROOT / "workspace"

# Python 解释器：原 bat 写死 python，这里优先用当前解释器
PY = sys.executable
if not PY:
    PY = "python"

ARIA2 = TOOLS / "aria2c.exe"
SZ = TOOLS / "7z.exe"
PDUMP = TOOLS / "payload-dumper-go.exe"
S2I = TOOLS / "simg2img.exe"        # 保留（流水线未直接调用）
I2S = TOOLS / "img2simg.exe"        # 保留（流水线未直接调用）
LPU = TOOLS / "lpunpack.exe"        # 保留（流水线未直接调用）
LPM = TOOLS / "lpmake.exe"
LPD = TOOLS / "lpdumps.exe"
HLP = TOOLS / "img_helper.py"       # 保留（流水线未直接调用）

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

# ---------------- 日志文件（格式与原 bat 一致：日期-小时.log） ----------------
_now = datetime.now()
LOG_FILE = WORKSPACE / "{}-{}.log".format(_now.strftime("%Y-%m-%d"), _now.hour)


def log_write(msg):
    # 写入运行日志文件（原 :LogWrite）
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
    # 带刷新的输入提示，EOF 时优雅退出而不是抛出 Traceback
    sys.stdout.write(text)
    sys.stdout.flush()
    try:
        return input()
    except EOFError:
        print()
        sys.exit(0)


def pause():
    # 对应原 bat 的 pause：等待任意键
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
        # 非交互环境（管道/重定向）直接跳过等待
        pass


def pause_seconds(seconds):
    # 对应原 bat 的 timeout /t N
    time.sleep(seconds)


# ---------------- 全局状态（对应原 bat 的 set 变量） ----------------
TARGET_DEVICE = ""
SRC_URL = ""
TGT_URL = ""
# 下载设置默认值
THREADS = 16
MAX_CONN = 16
TIMEOUT = 300
RETRY = 5


# ---------------- [A] 工具状态检查 ----------------
def check_tool(name, src):
    # 单个工具检查（原 :CT）
    p = TOOLS / name
    try:
        ok = p.exists() and p.stat().st_size > 0
    except Exception:
        ok = False
    tag = "{}[OK]{}".format(G, N) if ok else "{}[N/A]{}".format(R, N)
    print("  {}{}  {}  {}{}{}".format(W, name, tag, D, src, N))


def tool_status():
    os.system("cls" if os.name == "nt" else "clear")
    print()
    print("  {}+----------------------------------------------------------+{}".format(C, N))
    print("  {}|  PortingDone                                               |{}".format(C, N))
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
    check_tool("img_helper.py", "SuccessSourcePythonSuccess")
    check_tool("pack_partitions.py", "SuccessSourcePythonDone")
    print("  " + D + "----------------------------------------------------------" + N)
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
    show_credits_entry(1, "aria2c", "SourcePorting", "https://github.com/aria2/aria2", "GPL v2")
    show_credits_entry(2, "7-Zip (7z.exe)", "DonePorting", "https://www.7-zip.org/", "GNU LGPL")
    show_credits_entry(3, "payload-dumper-go", "Android OTA payload.bin SuccessPorting",
                       "https://github.com/ssut/payload-dumper-go", "MIT")
    show_credits_entry(4, "AOSP partition tools", "lpunpack, lpmake, lpdumps",
                       "https://github.com/nicktal01/aosp15_partition_tools", "Apache 2.0")
    show_credits_entry(5, "MIO_KITCHEN SOURCE", "img2simg, ext4.py, imgextractor.py",
                       "https://github.com/ColdWindScholar/MIO-KITCHEN-SOURCE", "GPL")
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


# ---------------- 配置读取（对应原 :ReadConfig） ----------------
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
    # 内部异常：请求返回主菜单
    pass


# ---------------- 打包配置读取（对应原 :ReadPackingConfig） ----------------
def read_packing_config():
    cfg = {
        "format": "erofs",
        "compression": "lz4hc",
        "compression_level": "9",
        "readonly": "true",
        "device_size": "6979321856",
        "metadata_size": "65536",
        "sparse": "true",
        "pack_super": "false",
        "super_name": "super",
        "super_group": "main",
        "metadata_slots": "3",
        "virtual_ab": "true",
        "ext4_packer": "make_ext4fs",
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


# ---------------- 配置模板生成（对应原 :CreateConfig） ----------------
def create_config():
    content = (
        "[source]\n"
        "url=\n"
        "\n"
        "[target]\n"
        "url=\n"
        "\n"
        "[settings]\n"
        "threads=16\n"
        "max-connection=16\n"
        "timeout=300\n"
        "retry=5\n"
        "\n"
        "[packing]\n"
        "pack_super=false\n"
        "format=erofs\n"
        "readonly=true\n"
        "compression=lz4hc\n"
        "compression_level=9\n"
        "device_size=6979321856\n"
        "metadata_size=65536\n"
        "sparse=true\n"
        "super_name=super\n"
        "super_group=main\n"
        "metadata_slots=3\n"
        "virtual_ab=true\n"
        "ext4_packer=make_ext4fs\n"
        "is_skip_apex=false\n"
        "enable_adb_debug=false\n"
        "patch_vbmeta=true\n"
        "utc_stamp=\n"
        "erofs_old_kernel=false\n"
        "device_platform=Qualcomm\n"
    )
    CONFIG.write_text(content, encoding="gbk")
    info("Created config template: {}".format(CONFIG))


# ---------------- Step 1 下载（对应原 :DL_One） ----------------
def dl_one(url, out_dir, name):
    os.makedirs(out_dir, exist_ok=True)
    info("Downloading: {}".format(name))
    cmd = [
        str(ARIA2), url,
        "-d", str(out_dir),
        "-x", str(MAX_CONN),
        "-s", str(THREADS),
        "-j", "1",
        "--console-log-level=notice",
        "--summary-interval=1",
        "--file-allocation=falloc",
        "--timeout={}".format(TIMEOUT),
        "--max-tries={}".format(RETRY),
        "--retry-wait=3",
        "--continue=true",
        "--auto-file-renaming=false",
        "--allow-overwrite=true",
        "--log-level=notice",
    ]
    try:
        rc = subprocess.call(cmd)
    except Exception:
        err("Download failed (aria2c not runnable): {}".format(name))
        return 1
    if rc != 0:
        err("Download failed: {}".format(name))
        return 1
    info("{} download done".format(name))
    try:
        for f in sorted(out_dir.iterdir()):
            if f.is_file():
                info("  {}  {} bytes".format(f.name, f.stat().st_size))
    except Exception:
        pass
    return 0


# ---------------- Step 2 解包（对应原 :ExtractArchive） ----------------
def extract_archive(src_dir, out_dir, label):
    src_dir = Path(src_dir)
    os.makedirs(out_dir, exist_ok=True)
    count = 0
    # 与原 bat 相同的扩展名顺序
    for ext in ["*.zip", "*.tar", "*.gz", "*.tgz", "*.7z", "*.rar"]:
        for f in sorted(src_dir.glob(ext)):
            count += 1
            info("Processing: {}".format(f.name))
            rc = subprocess.call([str(SZ), "x", str(f), "-o" + str(out_dir), "-y"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if rc == 0:
                info("Extracted: {}".format(f.name))
            else:
                err("Extract failed: {}".format(f.name))
    if count == 0:
        err("No archives found in {}".format(src_dir))
        return 1
    return 0


# ---------------- Step 3 payload 解包（对应原 :ExtractPayloadBin / :CheckPayloadExtracted） ----------------
def check_payload_extracted(target_dir):
    target_dir = Path(target_dir)
    if not target_dir.exists():
        return False
    count = sum(1 for _ in target_dir.rglob("*") if _.is_file())
    if count > 6:
        info("Already extracted ({} files), skipping.".format(count))
        return True
    return False


def extract_payload_bin(rom_dir, out_dir):
    rom_dir = Path(rom_dir)
    out_dir = Path(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    # 递归查找 payload.bin
    payload_file = None
    for f in rom_dir.rglob("payload.bin"):
        payload_file = f
        break

    if payload_file is None:
        info("payload.bin not found, copying existing img files...")
        count = 0
        for f in rom_dir.rglob("*.img"):
            count += 1
            try:
                shutil.copy2(f, out_dir / f.name)
            except Exception:
                pass
        info("Copied {} img file(s)".format(count))
        return 0

    info("Found payload: {}".format(payload_file))
    info("Extracting payload.bin...")
    rc = subprocess.call([str(PDUMP), "-o", str(out_dir), str(payload_file)])
    if rc != 0:
        err("payload-dumper-go failed")
        return 1
    info("Payload extracted to: {}".format(out_dir))
    for f in sorted(out_dir.glob("*.img")):
        mb = round(f.stat().st_size / 1024 / 1024, 1)
        info("  {}.img  {} MB".format(f.stem, mb))
    return 0


# ---------------- Step 4 镜像解包（对应原 :UnpackAllIMG） ----------------
def unpack_all_img(img_dir, out_dir, label):
    img_dir = Path(img_dir)
    out_dir = Path(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    for part in ["system", "system_ext", "product", "odm"]:
        img = img_dir / (part + ".img")
        if img.exists():
            info("Processing {}.img ...".format(part))
            os.makedirs(out_dir / part, exist_ok=True)
            rc = subprocess.call([PY, str(TOOLS / "extract_img.py"), str(img), str(out_dir / part)])
            if rc != 0:
                err("Failed to extract {}.img".format(part))
            else:
                info("{}.img extracted".format(part))
    return 0


# ---------------- Step 5 注入 adb debug（对应原 :InjectAdbDebug） ----------------
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


# ---------------- vbmeta 禁验（对应原 :PatchVbmeta） ----------------
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
    rc = subprocess.call([PY, str(TOOLS / "vbmeta_patch.py"), str(PACK_OUT)])
    if rc != 0:
        err("vbmeta patch reported errors")
        log_write("WARNING: vbmeta_patch.py reported errors")
    else:
        info("vbmeta patch done")
        log_write("vbmeta patched successfully")


# ---------------- Step 6 分区打包辅助 ----------------
def pack_one_partition(part, fs_dir, pack_cfg, lpc_args, counters):
    # 单个分区打包并追加 lpc_args（原 bat 内联逻辑）
    src = fs_dir / part
    if not src.exists():
        # 原 bat：源目录不存在时静默跳过
        return
    info("Packing partition: {}".format(part))
    log_write("Packing {}...".format(part))
    cmd = [
        PY, str(TOOLS / "pack_partitions.py"),
        pack_cfg["format"],
        "{},{}".format(pack_cfg["compression"], pack_cfg["compression_level"]),
        str(src),
        str(PACK_OUT),
        pack_cfg["ext4_packer"],
    ]
    rc = subprocess.call(cmd)
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
    lpc_args.append("--partition={}:readonly:{}:{}".format(part, size, pack_cfg.get("super_group", "main")))
    lpc_args.append("--image={}={}".format(part, out_img))
    counters["pack_ok"] += 1


def copy_partition_image(part, src_file, pack_cfg, lpc_args, counters):
    # 从 payload 镜像直接复制到 packed（mi_ext / vendor / vendor_dlkm）
    # 原 bat 行为：失败时 pause 后继续（不返回菜单）
    if not src_file.exists():
        err("{}.img not found in payload".format(part))
        pause()
        return
    try:
        shutil.copy2(src_file, PACK_OUT / src_file.name)
    except Exception:
        err("{}.img copy failed".format(part))
        pause()
        return
    if not (PACK_OUT / src_file.name).exists():
        err("{}.img copy failed".format(part))
        pause()
        return
    size = (PACK_OUT / src_file.name).stat().st_size
    info("{}.img ready, {} bytes".format(part, size))
    log_write("{}.img ready: {} bytes".format(part, size))
    lpc_args.append("--partition={}:readonly:{}:{}".format(part, size, pack_cfg.get("super_group", "main")))
    lpc_args.append("--image={}={}".format(part, PACK_OUT / src_file.name))
    counters["pack_ok"] += 1


def create_super_img(pack_cfg, lpc_args, pack_ok):
    # lpmake 生成 super.img（对应原 bat Step 6 末尾）
    if pack_cfg.get("pack_super", "false").lower() != "true":
        return
    if pack_ok == 0:
        err("No partitions packed, skipping super.img.")
        log_write("WARNING: No partitions packed, super.img skipped")
        return
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
    rc = subprocess.call(cmd)
    if rc != 0:
        err("lpmake failed")
        log_write("ERROR: lpmake failed to create super.img")
        pause()
        return
    log_write("super.img created successfully")
    if pack_cfg.get("sparse", "true").lower() == "true":
        info("sparse super.img created directly by lpmake")
    sup = PACK_OUT / "super.img"
    if sup.exists():
        info("super.img created, {} bytes".format(sup.stat().st_size))


# ---------------- 一键移植流水线（对应原 :OneClickPort） ----------------
def one_click_port():
    global TARGET_DEVICE

    os.system("cls" if os.name == "nt" else "clear")
    log_write("========== XMAport Session Start ==========")
    log_write("Target Device: {}".format(TARGET_DEVICE))
    print()
    print("  {}{}============================================================{}".format(C, BD, N))
    print("  {}{}  Done HyperOS{}".format(C, BD, N))
    print("  {}{}============================================================{}".format(C, BD, N))
    print()
    print("  {}  Workflow:{}".format(W, N))
    print("  {}    Step 1{}  Download ROM packages".format(G, N))
    print("  {}    Step 2{}  Extract archives".format(G, N))
    print("  {}    Step 3{}  Extract payload.bin".format(G, N))
    print("  {}    Step 4{}  Extract archivesSource".format(G, N))
    print("  {}    Step 5{}  Extract archivesSource".format(G, N))
    print("  {}    Step 6{}  Extract archivesSource".format(G, N))
    print("  {}    Step 7{}  Success".format(G, N))
    print()
    print("  " + D + "----------------------------------------------------------" + N)
    print()

    # 读取配置
    read_config()
    pack_cfg = read_packing_config()

    # 输入/读取目标设备代号
    cfg_txt = WORKSPACE / "config.txt"
    if not cfg_txt.exists():
        print("  {}  Enter target device codename:{}".format(W, N))
        print("  {}  (e.g. sheng, fuxi, cupid, mondrian){}".format(D, N))
        TARGET_DEVICE = prompt("  > ")
        cfg_txt.write_text("TARGET_DEVICE={}\n".format(TARGET_DEVICE), encoding="gbk")
    if cfg_txt.exists():
        for line in cfg_txt.read_text(encoding="gbk", errors="ignore").splitlines():
            if line.startswith("TARGET_DEVICE="):
                TARGET_DEVICE = line.split("=", 1)[1].strip()
                break

    print("  {}  Source URL:   {}{}{}".format(W, C, SRC_URL[:50], N))
    print("  {}  Target URL:   {}{}{}".format(W, C, TGT_URL[:50], N))
    print("  {}  Device:   {}{}{}".format(W, G, TARGET_DEVICE, N))
    print("  {}  Format1:   {}{}{}  Compression: {}{} level {}{}  Pack super: {}{}{}".format(
        W, G, pack_cfg["format"], N, G, pack_cfg["compression"], pack_cfg["compression_level"], N,
        G, pack_cfg["pack_super"], N))
    print()
    confirm = prompt("  {}SuccessSource(Y/N): {}".format(Y, N))
    if confirm.strip().lower() != "y":
        raise ReturnToMenu()

    # ---------------- Step 1: 下载 ----------------
    info("=== Step 1/7: Download ROM ===")
    log_write("Step 1: Download ROM start")
    log_write("Source URL: {}".format(SRC_URL))
    log_write("Target URL: {}".format(TGT_URL))
    if SRC_URL:
        info("[1/2] Downloading source ROM...")
        if dl_one(SRC_URL, SRC_DL, "SourceROM") != 0:
            err("Step 1 failed: source ROM download")
            log_write("ERROR: Source ROM download failed")
            pause()
            raise ReturnToMenu()
    if TGT_URL:
        info("[2/2] Downloading target ROM...")
        if dl_one(TGT_URL, TGT_DL, "TargetROM") != 0:
            err("Step 1 failed: target ROM download")
            log_write("ERROR: Target ROM download failed")
            pause()
            raise ReturnToMenu()
    info("Step 1 done")
    log_write("Step 1: Download ROM done")

    # ---------------- Step 2: 解压 ----------------
    info("=== Step 2/7: Extract archives ===")
    log_write("Step 2: Extract archives start")
    info("[1/2] Extracting source archive...")
    extract_archive(SRC_DL, SRC_ROM, "Source")
    info("[2/2] Extracting target archive...")
    extract_archive(TGT_DL, TGT_ROM, "Target")
    info("Step 2 done")
    log_write("Step 2: Extract archives done")

    # ---------------- Step 3: 解包 payload ----------------
    info("=== Step 3/7: Extract payload ===")
    log_write("Step 3: Extract payload start")
    if not check_payload_extracted(SRC_UNPACK):
        info("[1/2] Extracting source payload...")
        extract_payload_bin(SRC_ROM, SRC_UNPACK)
        log_write("Source payload extracted to: {}".format(SRC_UNPACK))
    if not check_payload_extracted(TGT_UNPACK):
        info("[2/2] Extracting target payload...")
        extract_payload_bin(TGT_ROM, TGT_UNPACK)
        log_write("Target payload extracted to: {}".format(TGT_UNPACK))
    info("Step 3 done")
    log_write("Step 3: Extract payload done")

    # ---------------- Step 4: 解包镜像 ----------------
    info("=== Step 4/7: Unpack IMG ===")
    log_write("Step 4: Unpack IMG start")
    info("Unpacking source images...")
    unpack_all_img(SRC_UNPACK, SRC_FS, "Source")
    log_write("Source images unpacked to: {}".format(SRC_FS))
    info("Unpacking target images...")
    unpack_all_img(TGT_UNPACK, TGT_FS, "Target")
    log_write("Target images unpacked to: {}".format(TGT_FS))
    info("Step 4 done")
    log_write("Step 4: Unpack IMG done")

    # ---------------- Step 5: 迁移 ----------------
    info("=== Step 5/7: Migrate ===")
    log_write("Step 5: Migrate start")
    migrate_ok = 0
    migrate_fail = 0
    mh = TOOLS / "make_hyper.exe"
    rc = subprocess.call([str(mh), "speed"]) if mh.exists() else 1
    if rc == 0:
        migrate_ok += 1
        log_write("make_hyper.exe speed: SUCCESS")
    else:
        migrate_fail += 1
        err("Step 5 failed: make_hyper.exe speed returned an error")
        log_write("ERROR: make_hyper.exe speed failed")
        pause()
    info("Step 5 done. Success: {} , Fail: {}".format(migrate_ok, migrate_fail))
    log_write("Step 5: Migrate done (OK={}, Fail={})".format(migrate_ok, migrate_fail))

    # 注入 adb debug 属性
    inject_adb_debug(pack_cfg)

    # ---------------- Step 6: 打包分区 + super ----------------
    info("=== Step 6/7: Pack partitions ===")
    info("Format: {} , Compression: {} level {}".format(
        pack_cfg["format"], pack_cfg["compression"], pack_cfg["compression_level"]))
    info("Cleaning packed directory...")
    for old in PACK_OUT.glob("*.img"):
        try:
            old.unlink()
        except Exception:
            pass

    # 传递打包环境变量给 pack_partitions.py（UTC 时间戳 / erofs 旧内核兼容 / is_skip_apex / V13 DEV 标记）
    os.environ["XMAPORT_UTC_STAMP"] = str(pack_cfg.get("utc_stamp", ""))
    os.environ["XMAPORT_EROFS_LEGACY"] = str(pack_cfg.get("erofs_old_kernel", "false"))
    os.environ["XMAPORT_IS_SKIP_APEX"] = str(pack_cfg.get("is_skip_apex", "false"))
    os.environ["XMAPORT_USE_LEGACY_EROFS"] = detect_legacy_erofs_marker()

    # 打包前校验分区镜像的原始文件系统格式（只警告不阻断）
    info("Checking original partition image formats...")
    try:
        subprocess.call([
            PY, str(TOOLS / "check_img_format.py"), pack_cfg["format"],
            str(SRC_UNPACK / "system.img"), str(SRC_UNPACK / "system_ext.img"),
            str(SRC_UNPACK / "product.img"), str(TGT_UNPACK / "odm.img"),
        ])
    except Exception:
        pass
    log_write("Partition image format check done (expected: {})".format(pack_cfg["format"]))

    counters = {"pack_ok": 0, "pack_fail": 0}
    lpc_args = []

    # 打包源分区 system / system_ext / product
    log_write("Packing source partitions: system, system_ext, product")
    is_skip_apex = pack_cfg.get("is_skip_apex", "false").lower() == "true"
    for part in ["system", "system_ext", "product"]:
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
                subprocess.call([PY, str(TOOLS / "extract_img.py"), str(img), str(TGT_FS / "vendor")])
        log_write("Packing vendor from target filesystem (MTK)")
        info("Packing partition: vendor (MTK)")
        if (TGT_FS / "vendor").exists():
            pack_one_partition("vendor", TGT_FS, pack_cfg, lpc_args, counters)
        else:
            err("vendor not found in target filesystem")
            pause()
    else:
        log_write("Copying vendor from target payload")
        info("Adding vendor from target payload...")
        copy_partition_image("vendor", TGT_UNPACK / "vendor.img", pack_cfg, lpc_args, counters)

    # 复制 vendor_dlkm（目标 payload）
    if (TGT_UNPACK / "vendor_dlkm.img").exists():
        copy_partition_image("vendor_dlkm", TGT_UNPACK / "vendor_dlkm.img", pack_cfg, lpc_args, counters)

    # 生成 super.img（可选）
    log_write("Creating super.img (pack_super={})".format(pack_cfg.get("pack_super", "false")))
    create_super_img(pack_cfg, lpc_args, counters["pack_ok"])

    # vbmeta 禁验（在 super 打包之后、汇总之前，不受 pack_super 限制）
    patch_vbmeta(pack_cfg)

    # ---------------- Step 7: 汇总 ----------------
    log_write("========== Porting Complete ==========")
    log_write("Total packed: {} partitions, {} failed".format(counters["pack_ok"], counters["pack_fail"]))
    log_write("Step 6: Pack partitions done")
    log_write("Pack OK={}, Fail={}".format(counters["pack_ok"], counters["pack_fail"]))
    print()
    print("  {}{}============================================================{}".format(C, BD, N))
    print("  {}{}Porting Complete!{}".format(G, BD, N))
    print("  {}{}============================================================{}".format(C, BD, N))
    print()
    print("  {}  Source FS:    {}{}{}".format(W, C, SRC_FS, N))
    print("  {}  Target FS:    {}{}{}".format(W, C, TGT_FS, N))
    print("  {}  Output:       {}{}{}".format(W, C, str(PACK_OUT / "super.img"), N))
    print()
    for part in ["system", "system_ext", "product", "odm", "mi_ext", "vendor", "vendor_dlkm"]:
        img = PACK_OUT / (part + ".img")
        if img.exists():
            print("  {}    {}.img  {} bytes{}".format(G, part, img.stat().st_size, N))

    # ROM Info（从源分区 build.prop 读取）
    print()
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
                # 原 bat 中 manufacturer 显示为 vendor
                label = "vendor"
            for line in props_text.splitlines():
                if "=" in line and line.split("=", 1)[0].strip() == key:
                    print("  {}  {}: {}{}{}".format(W, label.ljust(10), C, line.split("=", 1)[1].strip(), N))
                    break
    print("  {}  ------------------------------{}".format(C, N))
    print()
    print("  {}{}============================================================{}".format(C, BD, N))
    print()
    pause()


# ---------------- 全局崩溃报告（参照 TIK5 的 error 面板思路，无 rich 依赖） ----------------
def crash_report(exc_type, exc, tb):
    # KeyboardInterrupt 视为正常退出，不算崩溃
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


# ---------------- 主菜单（对应原 :Menu + :Exit） ----------------
def print_banner():
    print()
    print("  {}{}============================================================{}".format(C, BD, N))
    print("  {}{}   _____              _   _   _                          {}".format(C, BD, N))
    print("  {}{}  |__  /___ _ __ ___ | | | | | |__  _   _ _ __   ___ _ __ {}".format(C, BD, N))
    print("  {}{}    / // _ \\ '__/ _ \\| |_| | | '_ \\| | | | '_ \\ / _ \\ '__|{}".format(C, BD, N))
    print("  {}{}   / /|  __/ |  | (_) |  _  | | | | |_| | |_) |  __/ |   {}".format(C, BD, N))
    print("  {}{}  /____\\___|_|  \\___/|_| |_| |_| |_|\\__, | .__/ \\___|_|   {}".format(C, BD, N))
    print("  {}{}                                  |___/|_|              {}".format(C, BD, N))
    print("  {}{}============================================================{}".format(C, BD, N))


def show_menu():
    os.system("cls" if os.name == "nt" else "clear")
    print_banner()
    print()
    print("  {}{}  [1] Done Port HyperOS{}        {}Full auto workflow{}".format(G, BD, N, D, N))
    print()
    print("  {}{}  -- Tools --{}".format(Y, BD, N))
    print("  {}  [A] Check Tools{}".format(W, N))
    print("  {}  [B] Open Workspace{}".format(W, N))
    print("  {}  [C] Open-Source Credits{}".format(W, N))
    print("  {}  [D] Clean workspace{}".format(W, N))
    print("  {}  [0] Exit{}".format(R, N))
    print()
    print("  {}{}============================================================{}".format(C, BD, N))
    print()
    choice = prompt("  {}{}Select [0-1, A-C]: {}".format(Y, BD, N))
    return choice.strip().lower()


def main():
    # 初始化控制台与目录；工作目录切换到脚本目录（与双击 bat 的行为一致）
    init_console()
    try:
        os.chdir(ROOT)
    except Exception:
        pass
    for d in ALL_DIRS:
        d.mkdir(parents=True, exist_ok=True)

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
            tool_status()
        elif ch == "b":
            os.system('explorer "{}"'.format(WORKSPACE))
        elif ch == "c":
            show_credits()
        elif ch == "d":
            clean_workspace()
        elif ch == "0":
            os.system("cls" if os.name == "nt" else "clear")
            print("  {}============================================================{}".format(C, N))
            print("  {}  Done Porting!{}".format(G, N))
            print("  {}============================================================{}".format(C, N))
            pause()
            return
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
