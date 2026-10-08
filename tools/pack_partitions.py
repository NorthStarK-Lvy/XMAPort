#!/usr/bin/env python3
# 分区打包器 + 权限自动补全 Powered by GLM-5.2, Only used for XMAPort.

# 目录约定
# work/                                  = 工作根（source_dir 的父目录）
# work/{name}/                           = 分区文件系统目录
# work/config/{name}_fs_config           = fs_config（解包时生成，必需）
# work/config/{name}_file_contexts       = file_contexts（解包时生成，必需）

# 打包方式：
# - erofs:  mkfs.erofs  --mount-point --product-out --fs-config-file --file-contexts
# - ext4 :  make_ext4fs（默认）或 mke2fs+e2fsdroid

# 权限自动补全：
# - fs_config / file_contexts 缺失 → 报错终止（不允许全默认权限）
# - 原始 fs_config 中不存在的条目会被剔除
# - 文件系统目录中缺少 fs_config 条目的文件/目录会被自动补全权限
# - 补全规则：DEFAULT_PERMS + 同目录同后缀多数决 + symlink/bin/.sh 特殊规则
# - 特殊可执行名单：config/fs_special.conf（bin/su 等强制 0 2000 0755）
# - file_contexts 自动补全：product + system_ext（缺规则即补，label 继承父级）
# - 特殊 label 名单：config/fc_special.conf（路径 → 指定 label，优先于继承）
# - 名单文件不存在时自动生成预填模板，可手动增删
# - 补全前后内容写入 work/config/{name}_fs_config.log

# 用法: python pack_partitions.py <format> <compression> <source_dir> <output_dir> [ext4_packer]
# format      = erofs | ext4
# compression = "alg,level"（如 lz4hc,9；erofs 用）
# source_dir  = work/{name}（分区目录，如 source_filesystem/system）
# output_dir  = 输出镜像目录（如 workspace/packed）
# ext4_packer = make_ext4fs（默认）| mke2fs
#
# 可选环境变量：
# XMAPORT_UTC_STAMP    = 固定 UTC 时间戳（整数）。留空/未设 → 使用当前时间
# XMAPORT_EROFS_LEGACY = true 时 erofs 打包附加 -E legacy-compress（兼容旧内核）
# XMAPORT_IS_SKIP_APEX = false 时，system_ext 分区使用 tools/erofs-utils-cygwin 老版 mkfs.erofs
# XMAPORT_USE_LEGACY_EROFS = true 时，所有 erofs 分区使用老版 mkfs.erofs（MIUI13自动检测）
#
import os
import re
import shutil
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ============================================================
#  分区默认权限 (uid, gid, dir_mode, file_mode)
# ============================================================
DEFAULT_PERMS = {
    "system":     (0, 0, "0755", "0644"),
    "vendor":     (0, 0, "0755", "0644"),
    "odm":        (0, 0, "0755", "0644"),
    "product":    (0, 0, "0755", "0644"),
    "system_ext": (0, 0, "0755", "0644"),
}
FALLBACK_PERM = (0, 0, "0755", "0644")


def _win_unc_path(p):
    # 加 \\?\ 前缀，绕过 Win32 对末尾带点路径的规范化，使重命名/删除能访问到
    p = os.path.abspath(p)
    if p.startswith("\\\\"):
        return p
    return "\\\\?\\" + p


def sanitize_trailing_dots(root):
    # Windows 会自动规范化末尾带点的路径，导致 os.path.exists 判断失败、fs_config 不一致。
    # 打包前把末尾带点的文件/目录重命名为不带点；重命名失败（如路径被占用）则删除。
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for fn in filenames:
            if fn.endswith("."):
                old = os.path.join(dirpath, fn)
                new = os.path.join(dirpath, fn.rstrip("."))
                try:
                    os.rename(_win_unc_path(old), _win_unc_path(new))
                except Exception as e1:
                    try:
                        os.remove(_win_unc_path(old))
                        print(f"    \033[93m[WARN]\033[0m 重命名失败，已删除文件 {old}: {e1}")
                    except Exception as e2:
                        print(f"    \033[93m[WARN]\033[0m 无法处理文件 {old}: {e1} / {e2}")
        for dn in dirnames:
            if dn.endswith("."):
                old = os.path.join(dirpath, dn)
                new = os.path.join(dirpath, dn.rstrip("."))
                try:
                    os.rename(_win_unc_path(old), _win_unc_path(new))
                except Exception as e1:
                    try:
                        shutil.rmtree(_win_unc_path(old))
                        print(f"    \033[93m[WARN]\033[0m 重命名失败，已删除目录 {old}: {e1}")
                    except Exception as e2:
                        print(f"    \033[93m[WARN]\033[0m 无法处理目录 {old}: {e1} / {e2}")


# ============================================================
#  
# ============================================================
class _Progress:
    """简单的进度汇报器（不引入第三方依赖）。"""
    __slots__ = ('name', 'tick', 'count', 'last')

    def __init__(self, name, tick=20000):
        self.name = name
        self.tick = tick
        self.count = 0
        self.last = 0

    def bump(self, n=1):
        self.count += n

    def done(self):
        pass


def scan_content_dir(content_dir, name, tick=20000):
    """一次性扫描分区内容目录，返回所有条目元数据。

    返回: list of (rel_path, abs_path, is_dir, is_symlink, symlink_target)
    用于 prepare_fs_config 和 prepare_file_contexts，避免多次 os.walk。
    """
    entries = []
    progress = _Progress(name, tick)
    for root, dirs, files in os.walk(content_dir):
        for dname in dirs:
            abs_path = os.path.join(root, dname)
            rel = os.path.relpath(abs_path, content_dir).replace('\\', '/')
            entries.append((rel, abs_path, True, False, ''))
            progress.bump()
        for fname in files:
            abs_path = os.path.join(root, fname)
            rel = os.path.relpath(abs_path, content_dir).replace('\\', '/')
            sym_target = read_symlink_target(abs_path)
            entries.append((rel, abs_path, False, True if sym_target else False, sym_target))
            progress.bump()
    progress.done()
    return entries


class _TrieNode:
    __slots__ = ('children', 'label')

    def __init__(self):
        self.children = {}
        self.label = None


class PathTrie:
    """轻量级前缀树，用于 file_contexts 最长前缀匹配（无第三方依赖）。"""

    def __init__(self):
        self.root = _TrieNode()

    def add(self, path, label):
        node = self.root
        for part in path.strip('/').split('/'):
            if part not in node.children:
                node.children[part] = _TrieNode()
            node = node.children[part]
        node.label = label

    def longest_prefix_label(self, path):
        """返回最长前缀匹配的标签，无匹配返回 None。"""
        node = self.root
        best_label = None
        for part in path.strip('/').split('/'):
            if part not in node.children:
                break
            node = node.children[part]
            if node.label is not None:
                best_label = node.label
        return best_label


def find_tool(name, legacy=False):
    # legacy=True 时优先使用 erofs-utils-cygwin 内的旧版工具
    if legacy:
        p = os.path.join(SCRIPT_DIR, 'erofs-utils-cygwin', name + '.exe')
        if os.path.isfile(p):
            return p
    for cand in (name + '.exe', name):
        p = os.path.join(SCRIPT_DIR, cand)
        if os.path.isfile(p):
            return p
    return None


def resolve_utc(utc):
    # 时间戳优先级：显式参数 > 环境变量 XMAPORT_UTC_STAMP > 当前时间
    if utc is not None:
        return int(utc)
    env_utc = os.environ.get("XMAPORT_UTC_STAMP", "").strip()
    if env_utc.isdigit():
        return int(env_utc)
    return int(time.time())


def detect_content_dir(work, name):
    # 内容目录 = work/{name}（解包输出根级）。

    # 注意：work/{name}/{name}/ 可能存在（Android 11+ system_root 等镜像内部结构），
    # 但那是镜像内部子目录，不是打包内容目录。fs_config 路径对应 work/{name} 根级。
    #
    return os.path.join(work, name)


def call(cmd):
    try:
        print("    $ " + subprocess.list2cmdline(cmd))
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors='replace')
        for line in proc.stdout:
            print(line, end='', flush=True)
        return proc.wait()
    except FileNotFoundError:
        print(f"    [X] 工具未找到: {cmd[0]}")
        return 1


# ============================================================
#  权限补全辅助函数
# ============================================================
def strip_prefix(path, part_name):
    # 去掉分区名前缀：system/app/x -> app/x，system -> /
    if not part_name:
        return path
    # 同时兼容前导 /system/ 与 system/
    for prefix in ("/" + part_name + "/", part_name + "/"):
        if path.startswith(prefix):
            return path[len(prefix):]
    for exact in ("/" + part_name, part_name):
        if path == exact:
            return "/"
    return path


def parse_line(line):
    # 解析 fs_config 一行：path uid gid mode [caps] [link_target]
    s = line.strip()
    if not s or s.startswith('#'):
        return None
    parts = s.split()
    if len(parts) < 4:
        return None
    return parts


def read_symlink_target(filepath):
    # 检查文件是否为 Windows reparse-point symlink，返回目标路径。
    if not os.path.isfile(filepath):
        return ''
    try:
        with open(filepath, 'rb') as f:
            if f.read(10) == b'!<symlink>':
                return f.read().decode('utf-16-le', errors='replace').rstrip('\0')
    except Exception:
        pass
    return ''


def build_peer_map(cfg, is_dir_map=None):
    # 从已有 cfg 构建 parent -> { ext_or_'__dir__': (uid,gid,mode) } 多数决映射。
    # is_dir_map: dict[rel_path] -> bool，用于准确判断条目是否为目录；
    # 为 None 时回退到"mode 字符串全为奇数位"的保守启发式。
    def _guess_dir(path, mode_str):
        if is_dir_map is not None:
            return is_dir_map.get(path, False)
        # 启发式：三位/四位 mode 全为奇数时大概率是目录
        m = mode_str.lstrip('0')
        return all(c in '1357' for c in m)

    counts = {}
    for path, perm_str in cfg.items():
        if path == "/":
            continue
        parts = perm_str.split()
        if len(parts) < 3:
            continue
        parent = os.path.dirname(path) or "/"
        parent = parent.replace('\\', '/')
        name = os.path.basename(path)
        key_entry = (parts[0], parts[1], parts[2])

        if _guess_dir(path, parts[2]):
            ext = "__dir__"
        else:
            _, ext = os.path.splitext(name)
            ext = ext.lower()

        counts.setdefault(parent, {}).setdefault(ext, {}).setdefault(key_entry, 0)
        counts[parent][ext][key_entry] += 1

    result = {}
    for parent, ext_dict in counts.items():
        result[parent] = {}
        for ext, counter in ext_dict.items():
            result[parent][ext] = max(counter, key=lambda k: counter[k])
    return result


# ============================================================
#  名单文件机制（fs_special.conf / fc_special.conf）
#  - 文件不存在时自动生成预填模板（含常见项 + 格式说明），方便手动修改
#  - 文件存在时以文件内容为准（可增删内置常见项）
# ============================================================

# fs_config 特殊可执行名单：路径包含以下片段即强制 0 2000 0755
_FS_SPECIAL_DEFAULT = [
    "bin/su",
    "xbin/su",
    "bin/rw-system.sh",
    "bin/getSPL",
    "bin/install-recovery",
    "bin/daemon",
    "ext/.su",
    "disable_selinux.sh",
]

# file_contexts 特殊 label 名单：路径命中（或其子路径）时优先使用该 label
_FC_SPECIAL_DEFAULT = [
    "/vendor/bin/hw/android.hardware.wifi@1.0                u:object_r:hal_wifi_default_exec:s0",
    "/vendor/bin/hw/android.hardware.wifi@1.0-service        u:object_r:hal_wifi_default_exec:s0",
    "/vendor/bin/hw/android.hardware.displayfeature@1.0-service   u:object_r:hal_displayfeature_default_exec:s0",
    "/system/bin/su                                          u:object_r:su_exec:s0",
    "/system/xbin/su                                         u:object_r:su_exec:s0",
]


def load_special_list(config_dir, filename, defaults, comment_lines=()):
    # 读取名单文件；不存在时生成预填模板。返回有效条目列表。
    path = os.path.join(config_dir, filename)
    if not os.path.isfile(path):
        lines = ['# ' + c for c in comment_lines]
        lines.append('')
        lines.extend(defaults)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
            print(f"    [*] 已生成名单文件: {path}")
        except OSError:
            pass
    entries = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith('#'):
                    continue
                entries.append(s)
    except OSError:
        return list(defaults)
    return entries


# ============================================================
#  核心：fs_config 自动补全 + 前后日志
# ============================================================
def prepare_fs_config(name, work, content_dir, entries=None):
    #
    # 读取原始 fs_config，剔除不存在的条目，补全缺失的条目。
    # 写出 _fixed_{name}_fs_config，并输出 before/after 日志。
    # 返回 fixed_fs_config 路径；若原始 fs_config 不存在返回 None。
    #
    # 参数:
    #   entries: 可选，scan_content_dir() 返回的列表，避免重复 walk。
    #
    config_dir = os.path.join(work, 'config')
    orig_path = os.path.join(config_dir, f'{name}_fs_config')
    fixed_path = os.path.join(config_dir, f'_fixed_{name}_fs_config')
    log_path = os.path.join(config_dir, f'{name}_fs_config.log')

    if not os.path.isfile(orig_path):
        print(f"    [ERROR] fs_config 不存在: {orig_path}")
        print(f"    [ERROR] 不允许在无 fs_config 的情况下打包（全默认权限）")
        return None

    special_exec = load_special_list(
        config_dir, 'fs_special.conf', _FS_SPECIAL_DEFAULT,
        comment_lines=(
            '特殊可执行名单：路径包含以下片段即强制 0 2000 0755',
            '每行一条，支持 # 注释；修改后重新打包即生效。',
            '常见项已预填，可按需增删：',
        ))

    uid, gid, dir_mode, file_mode = DEFAULT_PERMS.get(name, FALLBACK_PERM)

    # --- 读取原始 fs_config 内容（用于 before 日志）---
    with open(orig_path, 'r', encoding='utf-8') as f:
        orig_lines = f.read().splitlines()

    # --- 一次性扫描文件系统（如未提供）---
    if entries is None:
        entries = scan_content_dir(content_dir, name)
    existing = {rel for rel, *_ in entries}
    is_dir_map = {rel: is_dir for rel, _, is_dir, *_ in entries}

    # --- Step 1: 解析原始条目，剔除不存在的条目 ---
    cfg = {}          # clean_path -> "uid gid mode [caps] [link]"
    removed = 0
    removed_log = []
    for line in orig_lines:
        parts = parse_line(line)
        if parts is None:
            continue
        orig_path_entry = parts[0]
        clean = strip_prefix(orig_path_entry, name)
        if clean in ("", "/"):
            clean = "/"
        if clean == "/":
            cfg["/"] = " ".join(parts[1:])
            continue
        if clean == "lost+found" or clean.startswith("lost+found/"):
            cfg[clean] = " ".join(parts[1:])
            continue
        if clean in existing:
            cfg[clean] = " ".join(parts[1:])
        elif any(c in clean for c in "*?["):
            # 保留含 glob 通配符的条目（Windows 下字面含 * 的文件会被重命名，
            # 这些条目不应被简单剔除；打包工具按原始 fs_config 匹配）
            cfg[clean] = " ".join(parts[1:])
        else:
            removed += 1
            removed_log.append(f"  {orig_path_entry}")

    if removed:
        print(f"    [*] 剔除 {removed} 条不存在的 fs_config 条目")

    # --- Step 2: 同目录同后缀多数决（仅 system_ext）---
    peer_map = None
    if name == "system_ext":
        peer_map = build_peer_map(cfg, is_dir_map=is_dir_map)

    # --- Step 3: 遍历文件系统目录，补全缺失条目 ---
    added = 0
    added_log = []
    for rel, abs_path, is_dir, is_symlink, sym_target in entries:
        if rel in cfg:
            continue
        assigned = False
        # 顶层 bin/xbin 目录严格保持旧行为（0 2000 0755），不参与多数决继承
        skip_inherit = is_dir and rel in ("bin", "xbin")
        if peer_map and not skip_inherit:
            parent = os.path.dirname(rel) or "/"
            if is_dir:
                if parent in peer_map and "__dir__" in peer_map[parent]:
                    p = peer_map[parent]["__dir__"]
                    cfg[rel] = f"{p[0]} {p[1]} {p[2]}"
                    assigned = True
            else:
                _, ext = os.path.splitext(rel)
                ext = ext.lower()
                if parent in peer_map and ext in peer_map[parent]:
                    p = peer_map[parent][ext]
                    cfg[rel] = f"{p[0]} {p[1]} {p[2]}"
                    assigned = True
        if assigned:
            added_log.append(f"  {rel} -> {cfg[rel]}")
            added += 1
            continue
        rel_parts = rel.split('/')
        is_bin = 'bin' in rel_parts or 'xbin' in rel_parts
        is_special = any(s in rel for s in special_exec)
        if is_dir:
            dgid = '2000' if ('bin' in rel_parts or 'xbin' in rel_parts) else gid
            cfg[rel] = f"{uid} {dgid} {dir_mode}"
        else:
            if is_symlink or sym_target:
                fm = file_mode
                fgid = gid
                if is_bin or is_special:
                    fgid = '2000'
                    fm = '0755'
                elif rel.endswith('.sh'):
                    fm = '0750'
                cfg[rel] = f"{uid} {fgid} {fm} {sym_target}"
            elif is_special:
                cfg[rel] = f"{uid} 2000 0755"
            elif is_bin:
                cfg[rel] = f"{uid} 2000 0755"
            elif rel.endswith('.sh'):
                cfg[rel] = f"{uid} {gid} 0750"
            else:
                cfg[rel] = f"{uid} {gid} {file_mode}"
        added_log.append(f"  {rel} -> {cfg[rel]}")
        added += 1

    print(f"    [*] 补全 {added} 条缺失的 fs_config 条目 (uid={uid} gid={gid})")
    if peer_map:
        print(f"    [*] system_ext 同目录同后缀多数决权限继承已启用")

    # --- Step 4: 确保根目录与 lost+found ---
    if "/" not in cfg:
        cfg["/"] = f"{uid} {gid} {dir_mode}"
        print(f"    [*] 补充根 \"/\" 条目")
    if "lost+found" not in cfg:
        cfg["lost+found"] = "0 0 0755"
        print(f"    [*] 补充 lost+found 条目")

    # --- Step 5: 写出 fixed fs_config（带分区前缀）---
    prefix = name + "/"
    fixed_lines = []
    for path, perms in sorted(cfg.items()):
        if path == "/":
            fixed_lines.append(f"/ {perms}")
        else:
            fixed_lines.append(f"{prefix}{path} {perms}")
    with open(fixed_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(fixed_lines) + '\n')

    # --- Step 6: 写 before/after 日志 ---
    with open(log_path, 'w', encoding='utf-8') as lf:
        lf.write(f"[{name}] fs_config 补全日志\n")
        lf.write(f"原始条目数: {len([l for l in orig_lines if parse_line(l)])}\n")
        lf.write(f"剔除(不存在): {removed}\n")
        lf.write(f"补全(缺失): {added}\n")
        lf.write(f"最终条目数: {len(fixed_lines)}\n")
        lf.write(f"uid={uid} gid={gid} dir_mode={dir_mode} file_mode={file_mode}\n\n")

        lf.write("=" * 60 + "\n")
        lf.write("=== BEFORE (原始 fs_config) ===\n")
        lf.write("=" * 60 + "\n")
        lf.write('\n'.join(orig_lines) + '\n\n')

        if removed_log:
            lf.write("--- 剔除的条目 ---\n")
            lf.write('\n'.join(removed_log) + '\n\n')

        lf.write("=" * 60 + "\n")
        lf.write("=== AFTER (补全后 fs_config) ===\n")
        lf.write("=" * 60 + "\n")
        lf.write('\n'.join(fixed_lines) + '\n\n')

        if added_log:
            lf.write("--- 新增的条目 ---\n")
            lf.write('\n'.join(added_log) + '\n')

    print(f"    [*] fs_config 日志: {log_path}")
    print(f"    [*] 补全后 fs_config: {fixed_path}")
    return fixed_path


# ============================================================
#  file_contexts 自动补全（product / system_ext 启用）
#  - 只追加缺失的规则，不改动原始规则行
#  - 判定"缺失"：文件/目录没有任何正则规则或精确路径规则匹配
#    （纯前缀目录规则不视为该路径自身的规则）
#  - 新规则 label 优先级：特殊名单(fc_special.conf) > 父级前缀规则继承 > 分区默认
# ============================================================
_FC_META_RE = re.compile(r'[.^$*+?{}()\\|\[\]]')

# 启用 file_contexts 补全的分区
_FC_ALLOW_PARTS = ("product", "system_ext")

# 分区默认 label（特殊名单与父级继承均未命中时使用）
_FC_DEFAULT_LABEL = {
    "product":    "u:object_r:system_file:s0",
    "system_ext": "u:object_r:system_ext_file:s0",
}


def _fc_has_regex(pattern):
    # 检测 file_contexts 规则是否包含正则元字符
    return _FC_META_RE.search(pattern) is not None


def _fc_match(pattern, path):
    # 判定 file_contexts 规则是否匹配路径。
    # 含正则元字符 → 正则 fullmatch；否则按 libselinux 前缀语义匹配。
    #
    if _fc_has_regex(pattern):
        try:
            return re.fullmatch(pattern, path) is not None
        except re.error:
            return False
    base = pattern.rstrip('/')
    return path == base or path.startswith(base + '/')


def prepare_file_contexts(name, work, content_dir, entries=None):
    # 为新增文件自动补全 file_contexts 规则（product / system_ext 启用）。

    # 读取原始 {name}_file_contexts，保留全部原始规则行，
    # 遍历文件系统，为没有精确规则匹配的文件/目录生成新规则
    # （路径转义 + 继承父级 label），追加写出 _fixed_{name}_file_contexts。
    # 返回 fixed 路径；原始文件不存在返回 None。
    #
    # 参数:
    #   entries: 可选，scan_content_dir() 返回的列表，避免重复 walk。
    #
    config_dir = os.path.join(work, 'config')
    orig_path = os.path.join(config_dir, f'{name}_file_contexts')
    fixed_path = os.path.join(config_dir, f'_fixed_{name}_file_contexts')

    if not os.path.isfile(orig_path):
        print(f"    [ERROR] file_contexts 不存在: {orig_path}")
        return None

    special_labels = load_special_list(
        config_dir, 'fc_special.conf', _FC_SPECIAL_DEFAULT,
        comment_lines=(
            '特殊 label 名单：每行一条 "路径 label"，支持 # 注释。',
            '路径命中（或其子路径）时优先使用该 label；',
            '常见项已预填（su / wifi / displayfeature 等），可按需增删：',
        ))

    # 用 Trie 加速特殊 label 的最长前缀匹配
    special_trie = PathTrie()
    for s in special_labels:
        parts = s.split(None, 1)
        if len(parts) == 2:
            special_trie.add(parts[0].rstrip('/'), parts[1])

    with open(orig_path, 'r', encoding='utf-8') as f:
        orig_lines = f.read().splitlines()

    raw_rules = []  # (pattern, label)
    for line in orig_lines:
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        parts = s.split(None, 1)
        if len(parts) == 2:
            raw_rules.append((parts[0], parts[1]))

    # 按语义拆分规则，避免全量遍历导致 O(n²)（system_ext 文件量大时卡死）：
    # - exact_rules  : 无元字符 pattern + 新增条目，O(1) set 查找
    # - regex_rules  : 预编译正则规则，数量固定，不随新增条目增长
    # - prefix_trie  : 无元字符前缀规则用 Trie 做最长前缀匹配
    exact_rules = set()
    regex_rules = []
    prefix_trie = PathTrie()
    for pattern, label in raw_rules:
        if _fc_has_regex(pattern):
            try:
                regex_rules.append(re.compile(pattern))
            except re.error:
                pass
        else:
            exact_rules.add(pattern)
            base = pattern.rstrip('/')
            if base and base != '/':
                prefix_trie.add(base, label)

    def is_covered(path):
        # 路径是否已被规则覆盖（精确集合 O(1) + 数量固定的预编译正则）
        if path in exact_rules:
            return True
        for cre in regex_rules:
            if cre.fullmatch(path):
                return True
        return False

    def pick_label(path):
        # label 优先级：特殊名单 > 最长父级前缀继承 > 分区默认
        slabel = special_trie.longest_prefix_label(path)
        if slabel is not None:
            return slabel
        plabel = prefix_trie.longest_prefix_label(path)
        if plabel is not None:
            return plabel
        return _FC_DEFAULT_LABEL.get(name, 'u:object_r:system_file:s0')

    if entries is None:
        entries = scan_content_dir(content_dir, name)

    added = []
    progress = _Progress(name, tick=20000)
    for rel, abs_path, is_dir, is_symlink, sym_target in entries:
        if rel == '':
            continue
        path = '/' + name + '/' + rel
        progress.bump()
        if is_covered(path):
            continue
        label = pick_label(path)
        exact_rules.add(path)   # 去重，且供后续条目 O(1) 精确命中
        added.append(f"{re.escape(path)} {label}")
    progress.done()

    lf_path = '/' + name + '/lost+found'
    if not is_covered(lf_path):
        label = pick_label(lf_path)
        exact_rules.add(lf_path)
        added.append(f"{re.escape(lf_path)} {label}")

    if not added:
        print(f"    [*] file_contexts 无需补全（{name}）")
        return orig_path

    out_lines = orig_lines + [''] + added
    with open(fixed_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out_lines) + '\n')

    print(f"    [*] file_contexts 补全 {len(added)} 条缺失规则（{name}）")
    if len(added) <= 200:
        # 条目较少时逐条展示；海量补全时只打摘要（避免控制台刷屏拖慢）
        for a in added:
            print(f"        + {a}")
    else:
        print(f"        （条目过多，省略明细，详见补全后文件）")
    print(f"    [*] 补全后 file_contexts: {fixed_path}")
    return fixed_path


def check_configs(name, work):
    #
    # 检查 fs_config / file_contexts 是否存在。
    # 缺失任一 → 报错返回 None。
    #
    config_dir = os.path.join(work, 'config')
    fs_cfg = os.path.join(config_dir, f'{name}_fs_config')
    fc = os.path.join(config_dir, f'{name}_file_contexts')
    if not os.path.isfile(fs_cfg):
        print(f"    [ERROR] fs_config 不存在: {fs_cfg}")
        print(f"    [ERROR] 不允许在无 fs_config 的情况下打包（全默认权限）")
        return None
    if not os.path.isfile(fc):
        print(f"    [ERROR] file_contexts 不存在: {fc}")
        print(f"    [ERROR] 不允许在无 file_contexts 的情况下打包（缺 SELinux 标签）")
        return None
    return fc


# ============================================================
#  erofs 打包
# ============================================================
def mkerofs(name, work, work_output, fmt_alg, level, utc=None):
    utc = resolve_utc(utc)
    legacy_marker = os.environ.get("XMAPORT_USE_LEGACY_EROFS", "").strip().lower() == "true"
    sync_apex_changed = os.environ.get("XMAPORT_SYNC_APEX_CHANGED", "").strip().lower() == "true"
    use_legacy = legacy_marker or (name == "system_ext" and sync_apex_changed)
    mkfs = find_tool('mkfs.erofs', legacy=use_legacy)
    if not mkfs:
        print("    [X] mkfs.erofs 未找到")
        return 1
    if use_legacy:
        reason = "V13 DEV marker" if legacy_marker else "sync_apex changed"
        print(f"    [*] {reason}: {name} 使用旧版 mkfs.erofs (erofs-utils 1.4)")

    content_dir = detect_content_dir(work, name)
    # 检查 fs_config / file_contexts 是否存在
    fc = check_configs(name, work)
    if fc is None:
        return 1
    # 一次性扫描分区目录，fs_config 和 file_contexts 复用同一份结果
    entries = scan_content_dir(content_dir, name)
    # 补全 fs_config 缺失条目
    fixed_fs = prepare_fs_config(name, work, content_dir, entries)
    if fixed_fs is None:
        return 1
    # product / system_ext 额外补全 file_contexts
    if name in _FC_ALLOW_PARTS:
        fixed_fc = prepare_file_contexts(name, work, content_dir, entries)
        if fixed_fc is None:
            return 1
        fc = fixed_fc

    extra = f'{fmt_alg},{level}' if fmt_alg != 'lz4' else fmt_alg
    legacy = []
    if os.environ.get("XMAPORT_EROFS_LEGACY", "").strip().lower() == "true":
        legacy = ['-E', 'legacy-compress']
    src = content_dir + os.sep
    out_img = os.path.join(work_output, f'{name}.img')
    cmd = [mkfs, *legacy, f'-z{extra}', '-T', f'{utc}',
           f'--mount-point=/{name}',
           f'--product-out={work}',
           f'--fs-config-file={fixed_fs}',
           f'--file-contexts={fc}',
           out_img, src]
    return call(cmd)


# ============================================================
#  ext4 打包：mke2fs + e2fsdroid（AOSP 官方路线）
# ============================================================
def mke2fs(name, work, work_output, sparse=False, size=0, utc=None):
    utc = resolve_utc(utc)
    mke2fs_exe = find_tool('mke2fs')
    e2fsdroid_exe = find_tool('e2fsdroid')
    if not mke2fs_exe or not e2fsdroid_exe:
        print("    [X] mke2fs 或 e2fsdroid 未找到")
        return 1

    content_dir = detect_content_dir(work, name)
    fc = check_configs(name, work)
    if fc is None:
        return 1
    # 一次性扫描分区目录，fs_config 和 file_contexts 复用同一份结果
    entries = scan_content_dir(content_dir, name)
    fixed_fs = prepare_fs_config(name, work, content_dir, entries)
    if fixed_fs is None:
        return 1
    if name in _FC_ALLOW_PARTS:
        fixed_fc = prepare_file_contexts(name, work, content_dir, entries)
        if fixed_fc is None:
            return 1
        fc = fixed_fc

    src = content_dir
    new_img = os.path.join(work_output, f'{name}_new.img')
    if not size:
        size = folder_size_blocks(src)
    print(f"    {name}:[{size}]")
    # e2fsdroid 无法打开反斜杠路径，统一转为正斜杠绝对路径
    def _posix(p):
        return os.path.abspath(p).replace('\\', '/')
    r = call([mke2fs_exe, '-O',
              '^has_journal,^metadata_csum,extent,huge_file,^flex_bg,^64bit,uninit_bg,dir_nlink,extra_isize',
              '-L', name, '-I', '256', '-M', f'/{name}', '-m', '0', '-t', 'ext4', '-b', '4096',
              new_img, f'{int(size)}'])
    if r != 0:
        _rm(new_img)
        return r
    r = call([e2fsdroid_exe, '-e', '-T', f'{utc}', '-S', _posix(fc), '-C', _posix(fixed_fs),
              '-a', f'/{name}', '-f', _posix(src), _posix(new_img)])
    if r != 0:
        _rm(new_img)
        return r
    if sparse:
        i2s = find_tool('img2simg')
        final = os.path.join(work_output, f'{name}.img')
        r = call([i2s, new_img, final]) if i2s else 1
        _rm(new_img)
        return r
    final = os.path.join(work_output, f'{name}.img')
    _rm(final)
    os.rename(new_img, final)
    return 0


# ============================================================
#  辅助
# ============================================================
def folder_size_bytes(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def folder_size_blocks(path):
    total = 0
    for root, _, files in os.walk(path):
        total += os.path.getsize(root) if os.path.isdir(root) else 0
        for f in files:
            fp = os.path.join(root, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total // 4096 + 64


def _rm(p):
    if p and os.path.exists(p):
        try:
            os.remove(p)
        except OSError:
            pass


# ============================================================
#  主入口
# ============================================================
def main():
    if len(sys.argv) < 5:
        print("用法: python pack_partitions.py <format> <compression> <source_dir> <output_dir> [ext4_packer]")
        sys.exit(1)

    fmt = sys.argv[1]
    compression = sys.argv[2]
    source_dir = os.path.normpath(sys.argv[3])
    output_dir = sys.argv[4]
    ext4_packer = sys.argv[5] if len(sys.argv) > 5 else 'mke2fs'

    if not os.path.isdir(source_dir):
        print(f"  [!] 源目录不存在: {source_dir}")
        sys.exit(1)

    name = os.path.basename(source_dir)
    work = os.path.dirname(source_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Windows 下末尾带点路径会导致 fs_config 与实际文件系统不一致，打包前统一处理
    sanitize_trailing_dots(source_dir)

    print(f"\n  [{name}]")
    print(f"    work:       {work}")
    print(f"    source:     {source_dir}")
    print(f"    output_dir: {output_dir}")
    print(f"    format:     {fmt}  compression: {compression}")

    parts = compression.split(',', 1)
    alg = parts[0] if parts else 'lz4hc'
    level = parts[1] if len(parts) > 1 and parts[1] else '9'

    if fmt == 'erofs':
        ret = mkerofs(name, work, output_dir, alg, level)
    elif fmt == 'ext4':
        ret = mke2fs(name, work, output_dir)
    else:
        print(f"    [X] 不支持的格式: {fmt}")
        sys.exit(1)

    if ret != 0:
        print(f"    [X] {name} 打包失败")
        sys.exit(1)

    out_img = os.path.join(output_dir, f'{name}.img')
    if os.path.isfile(out_img):
        mb = os.path.getsize(out_img) / 1024 / 1024
        print(f"    [OK] {name}.img ({mb:.1f} MB)")
    else:
        print(f"    [X] {name}.img 未生成")
        sys.exit(1)


if __name__ == '__main__':
    main()
