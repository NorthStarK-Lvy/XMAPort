#!/usr/bin/env python3
"""解包 Android 分区镜像（erofs / ext4 / sparse）

目录约定（扁平，不嵌套）：
  work/                            = 工作根（out_dir 的父目录）
  work/{name}/                     = 分区文件系统（提取结果，单层）
  work/config/{name}_fs_config     = fs_config
  work/config/{name}_file_contexts = file_contexts

- erofs: extract.erofs.exe -o work（自动建 {name}/ + config/，不嵌套）
- ext4:  纯 Python ext4 解析器（tools/zero/ext4.py），
         不再使用 7z。提取时同时生成 fs_config 与 file_contexts。
- sparse: simg2img.exe 就地转为 raw 后按上述处理。
"""
import os
import struct
import subprocess
import sys
import time

SPARSE_MAGIC = 0xED26FF3A
EROFS_MAGIC = 0xE0F5E1E2
EXT4_MAGIC = 0xEF53

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def detect(img):
    """检测镜像格式: SPARSE / EROFS / EXT4 / UNKNOWN"""
    try:
        with open(img, 'rb') as f:
            head = f.read(4)
            if len(head) >= 4 and struct.unpack('<I', head)[0] == SPARSE_MAGIC:
                return 'SPARSE'
            f.seek(0x400)
            m = f.read(4)
            if len(m) == 4 and struct.unpack('<I', m)[0] == EROFS_MAGIC:
                return 'EROFS'
            f.seek(0x438)
            m = f.read(2)
            if len(m) == 2 and struct.unpack('<H', m)[0] == EXT4_MAGIC:
                return 'EXT4'
    except OSError:
        pass
    return 'UNKNOWN'


def run(cmd, desc="Processing"):
    print(f"  [..] {desc}...", end="", flush=True)
    start = time.time()
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elapsed = time.time() - start
    print(f"\r  [OK] {desc} ({elapsed:.1f}s)")


def simg2img_inplace(path):
    exe = os.path.join(SCRIPT_DIR, 'simg2img.exe')
    tmp = path + '.unsparse'
    size_mb = os.path.getsize(path) / 1048576
    run([exe, path, tmp], f"Converting {os.path.basename(path)} ({size_mb:.1f}MB) sparse->raw")
    os.remove(path)
    os.rename(tmp, path)


def extract_erofs(img, work):
    exe = os.path.join(SCRIPT_DIR, 'extract.erofs.exe')
    size_mb = os.path.getsize(img) / 1048576
    run([exe, '-i', img, '-x', '-o', work], f"Extracting {os.path.basename(img)} ({size_mb:.1f}MB) erofs")


def extract_ext4(img, out, work):
    """用纯 Python ext4 解析器提取，并生成 fs_config / file_contexts。

    调用约定：main(target, output_dir, work, 'img')
      - output_dir: 提取目标（work/{name}）
      - work: 工作根，config 写到 work/config/
    """
    sys.path.insert(0, SCRIPT_DIR)
    from zero.imgextractor import Extractor
    e = Extractor()
    e.main(img, out, work, 'img')


def extract_img(img_path, out_dir):
    if not os.path.isfile(img_path):
        print(f"ERROR: 镜像不存在 {img_path}")
        return False

    fmt = detect(img_path)
    print(f"  [*] 检测格式: {fmt}")

    # work = out_dir 的父目录（config 写到 work/config/）
    work = os.path.dirname(os.path.normpath(out_dir))

    # sparse 先就地转 raw（保持原文件名，Extractor 据此命名 fs_config）
    if fmt == 'SPARSE':
        print("  [*] Sparse 镜像，就地转换为 raw...")
        try:
            simg2img_inplace(img_path)
        except subprocess.CalledProcessError:
            print("ERROR: sparse 转换失败")
            return False
        fmt = detect(img_path)
        print(f"  [*] 转 raw 后格式: {fmt}")

    try:
        if fmt == 'EROFS':
            print("  [*] 使用 extract.erofs.exe 解压...")
            extract_erofs(img_path, work)
        elif fmt == 'EXT4':
            print("  [*] 使用 ext4 解析器提取（纯 Python，不依赖 7z）...")
            extract_ext4(img_path, out_dir, work)
        else:
            print(f"ERROR: 不支持的镜像格式: {fmt}")
            return False
    except subprocess.CalledProcessError as e:
        print(f"ERROR: 解压失败: {e}")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

    count = sum(1 for _ in os.listdir(out_dir))
    print(f"  [OK] 解压成功，{count} 个文件/目录")
    return True


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("用法: python extract_img.py <镜像路径> <输出目录>")
        sys.exit(1)
    sys.exit(0 if extract_img(sys.argv[1], sys.argv[2]) else 1)
