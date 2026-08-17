#!/usr/bin/env python3
"""Block-based OTA (.dat / .dat.br / .dat.xz) 解包工具

将 Android block OTA 的 transfer list + new.dat 转换为 .img，供 extract_img.py 继续解包。

参考：MIO-KITCHEN source (src/core/utils.py) 的 Sdat2img / Unxz，
sdat2img 算法源自 xpirt/luxi78 (MIT)。

目录约定（XMAPort 流程）：
  transfer list / new.dat 位于 rom_dir 内（任意深度）。
  找到 "*.transfer.list" 后，在同目录下找同前缀的 new.dat（含 .br/.xz/.1/.2 分卷），
  输出 .img 写入 out_dir/<prefix>.img。

步骤：
  1. 解压：.new.dat.br (brotli) / .new.dat.xz (标准库 lzma)
  2. 拼接分卷：.new.dat.1 .new.dat.2 ... (按序号升序拼接，与 sdat2img 保持一致)
  3. Sdat2img: 解析 transfer list，按 4096 字节块拷贝到 .img
  4. 清理：删除中间 .new.dat / .transfer.list / .patch.dat（增量补丁不需要）

用法：
  python extract_dat.py <rom_dir> <out_dir>
"""
import os
import subprocess
import sys
from lzma import LZMADecompressor
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BROTLI = os.path.join(SCRIPT_DIR, "brotli.exe")
BLOCK_SIZE = 4096

VERSIONS = {
    1: "Lollipop 5.0",
    2: "Lollipop 5.1",
    3: "Marshmallow 6.0",
    4: "Nougat 7.x and later",
}


def rangeset(src):
    """解析 transfer list 中 "N,a,b,c,d" 格式的 range 字符串为 (begin,end) 列表。
    N 是后续数字个数，后接 N/2 对 (begin,end)。"""
    parts = [int(x) for x in src.split(",")]
    if parts[0] + 1 != len(parts):
        raise ValueError("invalid rangeset: " + src)
    return [(parts[i], parts[i + 1]) for i in range(1, len(parts), 2)]


def parse_transfer_list(path):
    """生成器：先 yield (version, new_blocks)，然后 yield (cmd, block_list)"""
    with open(path, "r", encoding="utf-8") as f:
        version = int(f.readline().strip())
        new_blocks = int(f.readline().strip())
        if version >= 2:
            f.readline()  # stash entries
            f.readline()  # max stashed blocks
        yield version, new_blocks
        for line in f:
            toks = line.split()
            if not toks:
                continue
            cmd = toks[0]
            if cmd == "new":
                yield cmd, rangeset(toks[1])
            elif cmd in ("erase", "zero"):
                yield cmd, rangeset(toks[1])
            else:
                # skip other commands (move/bsdiff/imgdiff etc, 仅全量 OTA 处理需要)
                continue


def sdat2img(transfer_list_file, new_data_file, output_image_file):
    """将 transfer list + new.dat 转换为 .img，返回 transfer list 版本"""
    gen = parse_transfer_list(transfer_list_file)
    version, new_blocks = next(gen)
    ver_desc = VERSIONS.get(version, "unknown")
    print("  [..] transfer list v{} ({}), {} new blocks".format(version, ver_desc, new_blocks), flush=True)

    max_size = 0
    copied = 0
    block = bytearray(BLOCK_SIZE)
    with open(new_data_file, "rb") as dat, open(output_image_file, "wb") as out:
        for cmd, bl in gen:
            for begin, end in bl:
                n = end - begin
                out.seek(begin * BLOCK_SIZE)
                if cmd == "new":
                    while n > 0:
                        chunk = dat.read(BLOCK_SIZE)
                        if len(chunk) < BLOCK_SIZE:
                            chunk += b"\x00" * (BLOCK_SIZE - len(chunk))
                        out.write(chunk)
                        n -= 1
                    copied += end - begin
                elif cmd == "zero":
                    while n > 0:
                        out.write(block)
                        n -= 1
                else:  # erase
                    pass
                if end * BLOCK_SIZE > max_size:
                    max_size = end * BLOCK_SIZE
    # 若输出末尾没写满，补齐到最大块位置
    with open(output_image_file, "r+b") as out:
        out.seek(0, os.SEEK_END)
        if out.tell() < max_size:
            out.truncate(max_size)
    return version


def unxz(src, dst, buff_size=1 << 20):
    """标准库 lzma 流式解压 .xz"""
    dec = LZMADecompressor()
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        while True:
            raw = fin.read(buff_size)
            if not raw:
                if not dec.eof:
                    while True:
                        data = dec.decompress(b"")
                        if data:
                            fout.write(data)
                        if dec.eof:
                            break
                break
            while True:
                data = dec.decompress(raw, max_length=buff_size)
                if data:
                    fout.write(data)
                if dec.eof or dec.needs_input:
                    break
                raw = b""


def unbr(src, dst):
    """用 tools/brotli.exe 解压 .br"""
    if not os.path.exists(BROTLI):
        raise FileNotFoundError("brotli.exe not found: " + BROTLI)
    subprocess.run([BROTLI, "-d", "-c", src], stdout=open(dst, "wb"), check=True)


def merge_split(d, prefix):
    """拼接 .new.dat.1, .2... 分卷为 .new.dat，返回拼接后的路径"""
    parts = sorted(
        d.glob(prefix + ".new.dat.*"),
        key=lambda p: int("".join(c for c in p.name.rsplit(".", 1)[-1] if c.isdigit()) or "0"),
    )
    if not parts:
        return None
    dst = d / (prefix + ".new.dat")
    with open(dst, "wb") as fout:
        for p in parts:
            with open(p, "rb") as fin:
                while True:
                    chunk = fin.read(1 << 20)
                    if not chunk:
                        break
                    fout.write(chunk)
    return dst


def convert_one(transfer_list, out_dir):
    """处理单个 transfer list，产出 .img"""
    transfer_list = Path(transfer_list)
    d = transfer_list.parent
    prefix = transfer_list.name[: -len(".transfer.list")]
    out_img = Path(out_dir) / (prefix + ".img")

    dat = None
    # 1. .br → brotli
    br = d / (prefix + ".new.dat.br")
    if br.exists():
        print("  [..] brotli: {}".format(br.name), flush=True)
        unbr(str(br), str(d / (prefix + ".new.dat")))
        dat = d / (prefix + ".new.dat")
    # 2. .xz → lzma
    xz = d / (prefix + ".new.dat.xz")
    if dat is None and xz.exists():
        print("  [..] xz: {}".format(xz.name), flush=True)
        unxz(str(xz), str(d / (prefix + ".new.dat")))
        dat = d / (prefix + ".new.dat")
    # 3. 分卷 .new.dat.1,.2
    if dat is None:
        dat = merge_split(d, prefix)
        if dat:
            print("  [..] merged {} split parts".format(
                len(list(d.glob(prefix + ".new.dat.*")))), flush=True)
    # 4. 直接 .new.dat
    if dat is None:
        nd = d / (prefix + ".new.dat")
        if nd.exists():
            dat = nd

    if dat is None:
        print("  [X] {} : no .new.dat (br/xz/split/plain) found".format(prefix))
        return False

    ver = sdat2img(str(transfer_list), str(dat), str(out_img))
    print("  [OK] {} -> {} (transfer list v{})".format(prefix, out_img.name, ver))

    # 清理中间文件（增量 .patch.dat 不需要）
    for tmp in [transfer_list, dat, d / (prefix + ".patch.dat")]:
        try:
            tmp.unlink()
        except Exception:
            pass
    for p in list(d.glob(prefix + ".new.dat.*")):
        try:
            p.unlink()
        except Exception:
            pass
    return True


def main():
    if len(sys.argv) != 3:
        print("用法: python extract_dat.py <rom_dir> <out_dir>")
        sys.exit(1)
    rom_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    transfer_files = sorted(rom_dir.rglob("*.transfer.list"))
    if not transfer_files:
        print("  [X] no .transfer.list found in {}".format(rom_dir))
        sys.exit(1)

    info_list = []
    ok = True
    for tf in transfer_files:
        print("  [*] block OTA partition: {}".format(tf.name))
        try:
            if convert_one(tf, out_dir):
                info_list.append(tf.name.replace(".transfer.list", ""))
            else:
                ok = False
        except Exception as e:
            print("  [X] {}: {}".format(tf.name, e))
            ok = False

    if info_list:
        print("  [OK] converted {} partition(s): {}".format(
            len(info_list), ", ".join(info_list)))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
