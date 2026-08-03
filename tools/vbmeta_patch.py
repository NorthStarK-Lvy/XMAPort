#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vbmeta 禁验补丁工具
#
# 读取 vbmeta 镜像，校验 AVB0 magic 后将偏移 123 处的 flags 字节
# 设为 0x03（disable-verity | disable-verification），实现 AVB 校验禁用。
#
# 用法:
#     python vbmeta_patch.py <文件或目录> [<文件或目录> ...]
#
# 目录参数会自动扫描其中的 vbmeta*.img 文件（不区分大小写）。
# 非 vbmeta 文件会被警告并跳过，不影响其他文件处理。

import os
import sys

AVB_MAGIC = b"AVB0"
AVB_MAGIC_LEN = 4
FLAGS_OFFSET = 123
FLAGS_DISABLE = b"\x03"


def patch_one(path):
    # 对单个 vbmeta 文件打补丁。
    # 返回: (status, msg)  status: 'patched' | 'skipped' | 'invalid' | 'error'
    try:
        with open(path, "r+b") as f:
            magic = f.read(AVB_MAGIC_LEN)
            if magic != AVB_MAGIC:
                return ("invalid", "not a vbmeta image (magic mismatch)")
            f.seek(FLAGS_OFFSET)
            cur = f.read(1)
            if cur == FLAGS_DISABLE:
                return ("skipped", "flags already 0x03 (idempotent)")
            f.seek(FLAGS_OFFSET)
            f.write(FLAGS_DISABLE)
            f.flush()
            os.fsync(f.fileno())
            old = ord(cur) if cur else 0
            return ("patched", "flags 0x%02X -> 0x03" % old)
    except OSError as e:
        return ("error", str(e))


def collect_files(args):
    # 从参数列表收集待处理的 vbmeta 文件清单。
    files = []
    for arg in args:
        if os.path.isdir(arg):
            for name in sorted(os.listdir(arg)):
                low = name.lower()
                if low.startswith("vbmeta") and low.endswith(".img"):
                    files.append(os.path.join(arg, name))
        elif os.path.isfile(arg):
            files.append(arg)
        else:
            print("  [warn] not found: %s" % arg)
    return files


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python vbmeta_patch.py <file|dir> [<file|dir> ...]")

    files = collect_files(sys.argv[1:])
    if not files:
        sys.exit("No vbmeta*.img found to patch.")

    n_patch = n_skip = n_invalid = n_err = 0
    for path in files:
        status, msg = patch_one(path)
        name = os.path.basename(path)
        if status == "patched":
            n_patch += 1
            print("  [OK]   %s : patched (%s)" % (name, msg))
        elif status == "skipped":
            n_skip += 1
            print("  [SKIP] %s : %s" % (name, msg))
        elif status == "invalid":
            n_invalid += 1
            print("  [WARN] %s : %s (skipped)" % (name, msg))
        else:
            n_err += 1
            print("  [ERR]  %s : %s" % (name, msg))

    print("")
    print("Summary: %d patched, %d skipped, %d invalid, %d error"
          % (n_patch, n_skip, n_invalid, n_err))
    sys.exit(0 if (n_err == 0) else 1)


if __name__ == "__main__":
    main()
