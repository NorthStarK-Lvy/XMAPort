"""Cross-platform symlink bridge for ext4 image unpack/pack.

On POSIX systems, native os.symlink/os.readlink are used directly.

On Windows (NTFS without admin privileges), a placeholder-file scheme is
used: the symlink target is stored inside a regular file prefixed with a
magic header.  This keeps symlink metadata round-trippable across the
unpack -> repack pipeline without requiring elevated filesystem symlinks.

Placeholder format (identical to the existing contract):
    b'!<symlink>' + target_path(UTF-16-LE, no BOM) + b'\\x00\\x00'
"""
import os

if os.name == 'nt':
    from ctypes import windll
    from ctypes.wintypes import DWORD, LPCSTR
    from stat import FILE_ATTRIBUTE_SYSTEM

_MAGIC = b'!<symlink>'
_TRAILER = b'\x00\x00'


def symlink(link_target, target):
    """Create a symlink (POSIX) or a placeholder file (Windows)."""
    parent = os.path.dirname(target)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)

    if os.name == 'posix':
        os.symlink(link_target, target)
        return

    # Windows: write placeholder
    path = target.replace('/', os.sep)
    with open(path, 'wb') as f:
        f.write(_MAGIC + link_target.encode('utf-16-le') + _TRAILER)
    try:
        windll.kernel32.SetFileAttributesA(
            LPCSTR(path.encode()), DWORD(FILE_ATTRIBUTE_SYSTEM))
    except Exception:
        pass


def readlink(path):
    """Read a symlink target (POSIX) or a placeholder file (Windows)."""
    if os.name != 'nt':
        return os.readlink(path)

    if os.path.isdir(path):
        return ''
    try:
        with open(path, 'rb') as f:
            if f.read(len(_MAGIC)) != _MAGIC:
                return ''
            return f.read().decode('utf-16-le', errors='replace').rstrip('\x00')
    except OSError:
        return ''
