"""Pure-Python ext4 image extractor.

Extracts an ext4 image into a directory tree while generating the metadata
files expected by the repack pipeline:

  work/config/{name}_fs_config
  work/config/{name}_file_contexts
  work/config/{name}_size.txt
  work/config/{name}_space.txt

Sparse images are first converted in-place by img_init.simg2img.
MOTOROLA-style wrapped images are detected and fixed before extraction.
"""
import os
import re
import struct
from timeit import default_timer as dti

from . import ext4
from .img_init import simg2img
from .posix import symlink

_EXT4_SUPER_MAGIC = b'\x53\xef'
_MOTO_PROBE_SIZE = 500_000
_MOTO_READ_SIZE = 15360


def _mode_to_octal(mode_str: str) -> str:
    """Convert ls -l style permission string to an octal mode string."""
    if len(mode_str) >= 10 and mode_str[0] in '-dlcbps':
        mode_str = mode_str[1:]
    if len(mode_str) != 9:
        return '000'

    def _triplet(r, w, x):
        v = 0
        if r == 'r':
            v += 4
        if w == 'w':
            v += 2
        if x in 'xXsStT':
            v += 1
        return v

    owner = _triplet(mode_str[0], mode_str[1], mode_str[2])
    group = _triplet(mode_str[3], mode_str[4], mode_str[5])
    other = _triplet(mode_str[6], mode_str[7], mode_str[8])

    special = 0
    if mode_str[2] in 'sS':
        special += 4
    if mode_str[5] in 'sS':
        special += 2
    if mode_str[8] in 'tT':
        special += 1

    if special:
        return f'{special}{owner}{group}{other}'
    return f'{owner}{group}{other}'


def _write_text(text: str, path: str) -> None:
    """Write text to file, creating parent directories if needed."""
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w', newline='\n', encoding='utf-8') as f:
        f.write(str(text).strip() + '\n')


def _read_symlink_target(inode):
    """Read the target of an ext4 symlink inode."""
    try:
        raw = inode.open_read().read()
        if raw:
            return raw.decode('utf-8')
    except (OSError, UnicodeDecodeError):
        pass
    return ''


class Extractor:
    def __init__(self):
        self.CONFIG_DIR = None
        self.FileName = ''
        self.OUTPUT_IMAGE_FILE = ''
        self.EXTRACT_DIR = ''
        self.context = []
        self.fs_config = []
        self.space = []
        self.error_times = 0

    @staticmethod
    def _out_name(file_path: str, out: int = 1) -> str:
        """Derive a clean partition/file name from a path.

        Splits on '-', ' ', '+', '{', '(' and returns the first part,
        matching the historical naming convention.
        """
        name = file_path if out == 1 else os.path.basename(file_path).rsplit('.', 1)[0]
        for sep in ('-', ' ', '+', '{', '('):
            name = name.split(sep)[0]
        return name

    @staticmethod
    def _parse_capabilities(value: bytes) -> str:
        """Parse a Linux security.capability xattr to a fs_config fragment."""
        if len(value) != 20:
            return ''
        try:
            r = struct.unpack('<5I', value)
        except struct.error:
            return ''
        # Preserve the legacy combined-capability encoding for compatibility
        # with existing Android build tooling.
        if r[1] > 65535:
            cap = hex((r[3] << 16) | r[1])
        else:
            cap = hex((r[3] << 32) | (r[2] << 16) | r[1])
        return f' capabilities={cap}'

    def _scan_dir(self, root_inode, root_path: str = '') -> None:
        """Recursively extract an ext4 directory inode."""
        for entry_name, entry_inode_idx, entry_type in root_inode.open_dir():
            if entry_name in ('.', '..') or entry_name.endswith(' (2)'):
                continue
            if self.error_times >= 200:
                print('  [W] Too many errors, stopping extraction.')
                break

            entry_inode = root_inode.volume.get_inode(entry_inode_idx, entry_type)
            entry_path = root_path + '/' + entry_name

            # Windows forbids ':' in filenames.
            if os.name == 'nt' and ':' in entry_path:
                print("  [W] ':' not allowed in Windows paths, replacing with '_'")
                entry_path = entry_path.replace(':', '_')

            # Inconsistent directory entry sanity check.
            if entry_path.endswith('/') and not entry_inode.is_dir:
                self.error_times += 1
                continue

            mode = _mode_to_octal(entry_inode.mode_str)
            uid = entry_inode.inode.i_uid
            gid = entry_inode.inode.i_gid
            cap = ''
            link_target = ''

            for attr_name, attr_value in entry_inode.xattrs():
                if attr_name == 'security.selinux':
                    label = attr_value.decode('utf-8').rstrip('\x00')
                    escaped_path = re.escape(entry_path)
                    self.context.append(f'/{self.FileName}{escaped_path} {label}')
                elif attr_name == 'security.capability':
                    cap = self._parse_capabilities(attr_value)

            if entry_inode.is_symlink:
                link_target = _read_symlink_target(entry_inode)

            fs_path = self.FileName + entry_path
            if ' ' in fs_path[1:]:
                self.space.append(fs_path)
                fs_path = fs_path.replace(' ', '_')

            self.fs_config.append(
                f'{fs_path} {uid} {gid} {mode}{cap} {link_target}'.rstrip())

            if entry_inode.is_dir:
                dir_target = self.EXTRACT_DIR + entry_path.replace(' ', '_').replace('"', '')
                if dir_target.endswith('.') and os.name == 'nt':
                    dir_target = dir_target[:-1]
                os.makedirs(dir_target, exist_ok=True)
                if os.name == 'posix' and os.geteuid() == 0:
                    os.chmod(dir_target, int(mode, 8))
                    os.chown(dir_target, uid, gid)
                self._scan_dir(entry_inode, entry_path)
            elif entry_inode.is_file:
                file_target = self.EXTRACT_DIR + entry_path.replace(' ', '_').replace('"', '')
                file_target_dir = os.path.dirname(file_target)
                if file_target_dir and not os.path.isdir(file_target_dir):
                    os.makedirs(file_target_dir, exist_ok=True)
                with open(file_target, 'wb') as out:
                    out.write(entry_inode.open_read().read())
                if os.name == 'posix' and os.geteuid() == 0:
                    os.chmod(file_target, int(mode, 8))
                    os.chown(file_target, uid, gid)
            elif entry_inode.is_symlink:
                target = self.EXTRACT_DIR + entry_path.replace(' ', '_')
                if os.path.exists(target) or os.path.islink(target):
                    try:
                        os.remove(target)
                    except OSError:
                        pass
                symlink(link_target, target)

    def _extract(self) -> None:
        """Extract the image and write fs_config / file_contexts metadata."""
        os.makedirs(self.CONFIG_DIR, exist_ok=True)
        _write_text(
            os.path.getsize(self.OUTPUT_IMAGE_FILE),
            os.path.join(self.CONFIG_DIR, f'{self.FileName}_size.txt'))

        with open(self.OUTPUT_IMAGE_FILE, 'rb') as f:
            self._scan_dir(ext4.Volume(f).root)

        self._insert_root_entries()
        self._write_configs()

    def _insert_root_entries(self) -> None:
        """Add mandatory root / lost+found / partition-root fs_config lines."""
        name = self.FileName
        # /
        self.fs_config.insert(
            0, '/ 0 2000 0755' if name == 'vendor' else '/ 0 0 0755')

        # lost+found or vendor special entry
        if name == 'vendor':
            self.fs_config.insert(1, f'{name} 0 2000 0755')
        else:
            self.fs_config.insert(1, '/lost+found 0 0 0700')

        # partition root
        insert_at = 2 if name == 'system' else 1
        self.fs_config.insert(insert_at, f'{name} 0 0 0755')

    def _write_configs(self) -> None:
        """Persist generated config files."""
        _write_text(
            '\n'.join(self.fs_config),
            os.path.join(self.CONFIG_DIR, f'{self.FileName}_fs_config'))
        if self.space:
            _write_text(
                '\n'.join(self.space),
                os.path.join(self.CONFIG_DIR, f'{self.FileName}_space.txt'))
        if self.context:
            self._insert_context_roots()
            self.context.sort()
            _write_text(
                '\n'.join(self.context),
                os.path.join(self.CONFIG_DIR, f'{self.FileName}_file_contexts'))

    def _insert_context_roots(self) -> None:
        """Add root-level file_contexts rules from a representative label."""
        label = None
        for line in self.context:
            if 'build.prop' in line or '/lost+found' in line:
                label = line.split(maxsplit=1)[1]
                break
        if not label:
            return
        name = self.FileName
        self.context.insert(0, f'/ {label}')
        self.context.insert(1, f'/{name}(/.*)? {label}')
        self.context.insert(2, f'/{name} {label}')
        self.context.insert(3, f'/{name}/lost+\\found {label}')

    @staticmethod
    def fix_moto(input_file: str) -> None:
        """Strip a Motorola wrapper header to expose the embedded ext4 image."""
        if not os.path.isfile(input_file):
            return
        output_file = input_file + '_'
        if os.path.exists(output_file):
            try:
                os.remove(output_file)
            except OSError:
                pass

        with open(input_file, 'rb') as f:
            data = f.read(_MOTO_PROBE_SIZE)
        if b'MOTO' not in data:
            return

        offsets = []
        for m in re.finditer(_EXT4_SUPER_MAGIC, data):
            pos = m.start() - 1080
            if 0 <= pos < len(data) and data[pos] == 0:
                offsets.append(pos)
        if not offsets:
            return

        with open(input_file, 'rb') as f, open(output_file, 'wb') as o:
            f.seek(offsets[0])
            chunk = f.read(_MOTO_READ_SIZE)
            if chunk:
                o.write(chunk)

        if os.path.exists(output_file):
            try:
                os.remove(input_file)
                os.rename(output_file, input_file)
            except OSError:
                pass

    def fix_size(self) -> None:
        """Expand a truncated image to the size declared by its ext4 superblock."""
        orig_size = os.path.getsize(self.OUTPUT_IMAGE_FILE)
        with open(self.OUTPUT_IMAGE_FILE, 'rb+') as f:
            volume = ext4.Volume(f)
            real_size = volume.get_block_count * volume.block_size
            if orig_size < real_size:
                print(
                    f'  [W] Image smaller than expected, '
                    f'expanding {orig_size} -> {real_size}')
                f.truncate(real_size)

    def main(self, target: str, output_dir: str, work: str, target_type: str = 'img') -> None:
        """Extract an ext4/sparse image to output_dir with config in work/config."""
        self.EXTRACT_DIR = (
            os.path.realpath(os.path.dirname(output_dir))
            + os.sep + self._out_name(os.path.basename(output_dir)))
        self.OUTPUT_IMAGE_FILE = (
            os.path.realpath(os.path.dirname(target))
            + os.sep + os.path.basename(target))
        self.FileName = self._out_name(os.path.basename(target), out=0)
        self.CONFIG_DIR = os.path.join(work, 'config')

        if target_type == 's_img':
            simg2img(target)
            target_type = 'img'

        # Inspect mount point; adjust output directory if the image name looks wrong.
        with open(self.OUTPUT_IMAGE_FILE, 'rb+') as f:
            volume = ext4.Volume(f)
            mount = volume.get_mount_point
            if mount.startswith('/'):
                mount = mount[1:]
            if '/' in mount:
                mount = mount.split('/')[-1]
            if any(c in mount for c in '.@#'):
                mount = ''
            out_base = self._out_name(os.path.basename(output_dir))
            if mount and out_base != mount and self.FileName != 'mi_ext':
                print(f'  [N] Filename appears to be wrong, extracting to {mount}')
                self.EXTRACT_DIR = (
                    os.path.realpath(os.path.dirname(output_dir))
                    + os.sep + mount)
                self.FileName = mount

        if target_type == 'img':
            with open(self.OUTPUT_IMAGE_FILE, 'rb') as f:
                data = f.read(_MOTO_PROBE_SIZE)
            if b'MOTO' in data:
                print('  [N] MOTO structure detected, fixing...')
                self.fix_moto(os.path.abspath(self.OUTPUT_IMAGE_FILE))
            self.fix_size()
            print(
                f'  [..] Extracting {os.path.basename(target)} '
                f'--> {os.path.basename(self.EXTRACT_DIR)}',
                end='', flush=True)
            start = dti()
            self._extract()
            print(f'\r  [OK] Extracted {os.path.basename(target)} '
                  f'({dti() - start:.2f}s)')
