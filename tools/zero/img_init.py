"""Sparse-to-raw image converter backed by bundled simg2img.exe.

Provides an in-place conversion: the original sparse file is replaced by
its raw equivalent.  Non-sparse files are reported and skipped without
raising, so the caller (imgextractor) can continue gracefully.
"""
import os
import subprocess
import time

_G = "\033[92m"   # green
_R = "\033[91m"   # red
_N = "\033[0m"    # reset

_SPARSE_MAGIC = b'\x3a\xff\x26\xed'  # 0xED26FF3A little-endian


def _info(msg):
    print(f"  {_G}[INFO]{_N}  {msg}")


def _error(msg):
    print(f"  {_R}[ERROR]{_N} {msg}")


def _exe():
    """Return path to simg2img.exe, or None if not found."""
    p = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'simg2img.exe')
    return p if os.path.isfile(p) else None


def simg2img(path: str):
    """Convert a sparse image to raw in-place.

    Non-sparse files: print [ERROR] and return (no exception).
    Conversion failure: print [ERROR], clean up temp file, return.
    Success: original file is replaced by the raw version.
    """
    try:
        with open(path, 'rb') as f:
            if f.read(4) != _SPARSE_MAGIC:
                _error(f"{os.path.basename(path)}: not a sparse image, skipping")
                return
    except OSError as e:
        _error(f"{os.path.basename(path)}: cannot read ({e})")
        return

    exe = _exe()
    if not exe:
        _error("simg2img.exe not found")
        return

    tmp = path + '.unsparse'
    size_mb = os.path.getsize(path) / 1048576
    name = os.path.basename(path)
    _info(f"Converting {name} ({size_mb:.1f}MB) sparse->raw...")

    start = time.time()
    result = subprocess.run([exe, path, tmp],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    elapsed = time.time() - start

    if result.returncode != 0:
        _error(f"simg2img.exe failed (exit code {result.returncode})")
        try:
            os.remove(tmp)
        except OSError:
            pass
        return

    os.remove(path)
    os.rename(tmp, path)
    _info(f"{name} converted ({elapsed:.1f}s)")
