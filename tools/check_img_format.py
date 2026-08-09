#!/usr/bin/env python3
# 镜像格式校验工具（参照 TIK5 gettype 思路，仅做 erofs/ext4/sparse 识别）
#
# 用法: python check_img_format.py <期望格式> <img1> [img2 ...]
# 期望格式 = erofs | ext4
# 检测每个镜像的实际文件系统格式（按 superblock magic），与期望不一致时输出 [WARN]。
# 只警告不阻断，退出码恒为 0。

import os
import sys

# erofs superblock magic 0xE0F5E1E2 @ 偏移 1024（小端存储）
EROFS_MAGIC_OFFSET = 1024
EROFS_MAGIC = b"\xe2\xe1\xf5\xe0"

# ext4 superblock magic 0xEF53 @ 偏移 0x438（小端存储）
EXT4_MAGIC_OFFSET = 0x438
EXT4_MAGIC = b"\x53\xef"

# android sparse 镜像 magic 0xED26FF3A @ 偏移 0（小端存储）
SPARSE_MAGIC_OFFSET = 0
SPARSE_MAGIC = b"\x3a\xff\x26\xed"


def detect_format(path):
    # 返回 'erofs' | 'ext4' | 'sparse' | 'unknown'
    try:
        with open(path, "rb") as f:
            head = f.read(2048)
    except OSError:
        return "unknown"
    if len(head) >= EROFS_MAGIC_OFFSET + 4:
        if head[EROFS_MAGIC_OFFSET:EROFS_MAGIC_OFFSET + 4] == EROFS_MAGIC:
            return "erofs"
    if len(head) >= EXT4_MAGIC_OFFSET + 2:
        if head[EXT4_MAGIC_OFFSET:EXT4_MAGIC_OFFSET + 2] == EXT4_MAGIC:
            return "ext4"
    if len(head) >= SPARSE_MAGIC_OFFSET + 4:
        if head[SPARSE_MAGIC_OFFSET:SPARSE_MAGIC_OFFSET + 4] == SPARSE_MAGIC:
            return "sparse"
    return "unknown"


def main():
    if len(sys.argv) < 3:
        sys.exit("Usage: python check_img_format.py <erofs|ext4> <img1> [img2 ...]")

    expected = sys.argv[1].strip().lower()
    if expected not in ("erofs", "ext4"):
        sys.exit("Expected format must be 'erofs' or 'ext4'.")

    for arg in sys.argv[2:]:
        name = os.path.basename(arg)
        if not os.path.isfile(arg):
            print("  [skip] %s : image not found" % name)
            continue
        detected = detect_format(arg)
        if detected == expected:
            print("  [MATCH] %s : %s" % (name, detected))
        elif detected == "unknown":
            print("  [WARN] %s : format unknown, cannot verify" % name)
        else:
            print("  [WARN] %s : expected %s, detected %s "
                  "(packed with config format, may fail to mount!)"
                  % (name, expected, detected))
    # 只警告不阻断
    sys.exit(0)


if __name__ == "__main__":
    main()
