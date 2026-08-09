# zero package init: sparse->raw adapter backed by bundled simg2img.exe
import os
import subprocess
import time

_SPARSE_MAGIC = b'\x3a\xff\x26\xed'  # 0xED26FF3A little-endian


def _exe():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'simg2img.exe')


def simg2img(path: str):
    """
    Convert a sparse image to a raw image IN-PLACE (replaces the original file).
    Mirrors upstream utils.simg2img behavior: if the file is not sparse, do nothing.
    """
    try:
        with open(path, 'rb') as f:
            if f.read(4) != _SPARSE_MAGIC:
                return
    except OSError:
        return
    tmp = path + '.unsparse'
    size_mb = os.path.getsize(path) / 1048576
    desc = f"Converting {os.path.basename(path)} ({size_mb:.1f}MB) sparse->raw"
    print(f"  [..] {desc}...", end="", flush=True)
    start = time.time()
    subprocess.run([_exe(), path, tmp], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elapsed = time.time() - start
    print(f"\r  [OK] {desc} ({elapsed:.1f}s)")
    os.remove(path)
    os.rename(tmp, path)
