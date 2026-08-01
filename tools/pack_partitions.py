#!/usr/bin/env python3
# 分区打包器 + 权限自动补全 Powered by GLM-5.2, Only used for XMAPort.

# 目录约定（与 extract_img.py 一致）：Thanks to MIO-KITCHEN
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
# - 补全前后内容写入 work/config/{name}_fs_config.log

# 用法: python pack_partitions.py <format> <compression> <source_dir> <output_dir> [ext4_packer]
# format      = erofs | ext4
# compression = "alg,level"（如 lz4hc,9；erofs 用）
# source_dir  = work/{name}（分区目录，如 source_filesystem/system）
# output_dir  = 输出镜像目录（如 workspace/packed）
# ext4_packer = make_ext4fs（默认）| mke2fs
#
import os
import re
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


def find_tool(name):
    for cand in (name + '.exe', name):
        p = os.path.join(SCRIPT_DIR, cand)
        if os.path.isfile(p):
            return p
    return None


def detect_content_dir(work, name):
    # 内容目录 = work/{name}（解包输出根级）。

    # 注意：work/{name}/{name}/ 可能存在（Android 11+ system_root 等镜像内部结构），
    # 但那是镜像内部子目录，不是打包内容目录。fs_config 路径对应 work/{name} 根级。
    #
    return os.path.join(work, name)


def call(cmd):
    print(f"    $ {' '.join(cmd)}")
    try:
        return subprocess.run(cmd).returncode
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
    prefix = part_name + "/"
    if path.startswith(prefix):
        return path[len(prefix):]
    if path == part_name:
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


def is_dir_mode(mode_str):
    # 通过 mode 是否含执行位判断是否为目录条目
    if len(mode_str) == 4:
        return mode_str[3] in '1357'
    if len(mode_str) == 3:
        return mode_str[2] in '1357'
    return False


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


def build_peer_map(cfg):
    # 从已有 cfg 构建 parent -> { ext_or_'__dir__': (uid,gid,mode) } 多数决映射。
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

        if is_dir_mode(parts[2]):
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
#  核心：fs_config 自动补全 + 前后日志
# ============================================================
def prepare_fs_config(name, work, content_dir):
    #
    # 读取原始 fs_config，剔除不存在的条目，补全缺失的条目。
    # 写出 _fixed_{name}_fs_config，并输出 before/after 日志。
    # 返回 fixed_fs_config 路径；若原始 fs_config 不存在返回 None。
    #
    config_dir = os.path.join(work, 'config')
    orig_path = os.path.join(config_dir, f'{name}_fs_config')
    fixed_path = os.path.join(config_dir, f'_fixed_{name}_fs_config')
    log_path = os.path.join(config_dir, f'{name}_fs_config.log')

    if not os.path.isfile(orig_path):
        print(f"    [ERROR] fs_config 不存在: {orig_path}")
        print(f"    [ERROR] 不允许在无 fs_config 的情况下打包（全默认权限）")
        return None

    uid, gid, dir_mode, file_mode = DEFAULT_PERMS.get(name, FALLBACK_PERM)

    # --- 读取原始 fs_config 内容（用于 before 日志）---
    with open(orig_path, 'r', encoding='utf-8') as f:
        orig_lines = f.read().splitlines()

    # --- Step 1: 解析原始条目，剔除不存在的 ---
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
        check = os.path.join(content_dir, clean)
        if os.path.exists(check):
            cfg[clean] = " ".join(parts[1:])
        else:
            removed += 1
            removed_log.append(f"  {orig_path_entry}")

    if removed:
        print(f"    [*] 剔除 {removed} 条不存在的 fs_config 条目")

    # --- Step 2: 同目录同后缀多数决（仅 system_ext）---
    peer_map = None
    if name == "system_ext":
        peer_map = build_peer_map(cfg)

    # --- Step 3: 遍历文件系统目录，补全缺失条目 ---
    added = 0
    added_log = []
    for root, dirs, files in os.walk(content_dir):
        for fname in files:
            rel = os.path.relpath(os.path.join(root, fname), content_dir).replace('\\', '/')
            if rel not in cfg:
                assigned = False
                if peer_map:
                    _, ext = os.path.splitext(fname)
                    ext = ext.lower()
                    parent = os.path.dirname(rel)
                    if parent in peer_map and ext in peer_map[parent]:
                        p = peer_map[parent][ext]
                        cfg[rel] = f"{p[0]} {p[1]} {p[2]}"
                        assigned = True
                if not assigned:
                    fpath = os.path.join(content_dir, rel)
                    sym_target = read_symlink_target(fpath)
                    rel_parts = rel.split('/')
                    is_bin = 'bin' in rel_parts or 'xbin' in rel_parts
                    if sym_target:
                        fm = file_mode
                        fgid = gid
                        if is_bin:
                            fgid = '2000'
                            fm = '0755'
                        elif rel.endswith('.sh'):
                            fm = '0750'
                        cfg[rel] = f"{uid} {fgid} {fm} {sym_target}"
                    elif is_bin:
                        cfg[rel] = f"{uid} 2000 0755"
                    elif rel.endswith('.sh'):
                        cfg[rel] = f"{uid} {gid} 0750"
                    else:
                        cfg[rel] = f"{uid} {gid} {file_mode}"
                added_log.append(f"  {rel} -> {cfg[rel]}")
                added += 1
        for dname in dirs:
            rel = os.path.relpath(os.path.join(root, dname), content_dir).replace('\\', '/')
            if rel not in cfg:
                assigned = False
                if peer_map:
                    parent = os.path.dirname(rel)
                    if parent in peer_map and "__dir__" in peer_map[parent]:
                        p = peer_map[parent]["__dir__"]
                        cfg[rel] = f"{p[0]} {p[1]} {p[2]}"
                        assigned = True
                if not assigned:
                    cfg[rel] = f"{uid} {gid} {dir_mode}"
                added_log.append(f"  {rel} -> {cfg[rel]}")
                added += 1

    print(f"    [*] 补全 {added} 条缺失的 fs_config 条目 (uid={uid} gid={gid})")
    if peer_map:
        print(f"    [*] system_ext 同目录同后缀多数决权限继承已启用")

    # --- Step 4: 确保根目录 ---
    if "/" not in cfg:
        cfg["/"] = f"{uid} {gid} {dir_mode}"
        print(f"    [*] 补充根 \"/\" 条目")

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
#  file_contexts 自动补全（仅 product 分区启用）
#  - 只追加缺失的规则，不改动原始规则行
#  - 判定"缺失"：文件/目录没有任何正则规则或精确路径规则匹配
#    （纯前缀目录规则不视为该路径自身的规则）
#  - 新规则 label 继承最近父级前缀规则的 label，无则用 product 默认
# ============================================================
_FC_META_RE = re.compile(r'[.^$*+?{}()\\|\[\]]')


def _fc_has_regex(pattern):
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


def _fc_parent_label(rules, path):
    # 从无元字符前缀规则中找最近父级 label；无则返回 None。
    best = None
    for pattern, label in rules:
        if _fc_has_regex(pattern):
            continue
        base = pattern.rstrip('/')
        if base == '/' or base == '':
            continue
        if path.startswith(base + '/') or path == base:
            if best is None or len(base) > best[0]:
                best = (len(base), label)
    return best[1] if best else None


def prepare_file_contexts(name, work, content_dir):
    # 为新增文件自动补全 file_contexts 规则（仅 product）。

    # 读取原始 {name}_file_contexts，保留全部原始规则行，
    # 遍历文件系统，为没有精确规则匹配的文件/目录生成新规则
    # （路径转义 + 继承父级 label），追加写出 _fixed_{name}_file_contexts。
    # 返回 fixed 路径；原始文件不存在返回 None。
    #
    config_dir = os.path.join(work, 'config')
    orig_path = os.path.join(config_dir, f'{name}_file_contexts')
    fixed_path = os.path.join(config_dir, f'_fixed_{name}_file_contexts')

    if not os.path.isfile(orig_path):
        print(f"    [ERROR] file_contexts 不存在: {orig_path}")
        return None

    with open(orig_path, 'r', encoding='utf-8') as f:
        orig_lines = f.read().splitlines()

    rules = []  # (pattern, label)
    for line in orig_lines:
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        parts = s.split(None, 1)
        if len(parts) == 2:
            rules.append((parts[0], parts[1]))

    def has_exact_rule(path):
        for pattern, _ in rules:
            if _fc_has_regex(pattern):
                try:
                    if re.fullmatch(pattern, path):
                        return True
                except re.error:
                    continue
            elif path == pattern:
                return True
        return False

    fallback_label = 'u:object_r:system_file:s0'
    added = []
    for root, dirs, files in os.walk(content_dir):
        entries = [os.path.join(root, d) for d in dirs] + \
                  [os.path.join(root, f) for f in files]
        for ep in entries:
            rel = os.path.relpath(ep, content_dir).replace('\\', '/')
            if rel == '':
                continue
            path = '/' + name + '/' + rel
            if has_exact_rule(path):
                continue
            label = _fc_parent_label(rules, path)
            if label is None:
                label = fallback_label
            new_pattern = re.escape(path)
            rules.append((new_pattern, label))
            added.append(f"{new_pattern} {label}")

    if not added:
        print(f"    [*] file_contexts 无需补全（{name}）")
        return orig_path

    out_lines = orig_lines + [''] + added
    with open(fixed_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out_lines) + '\n')

    print(f"    [*] file_contexts 补全 {len(added)} 条缺失规则（仅 {name}）")
    for a in added:
        print(f"        + {a}")
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
    if utc is None:
        utc = int(time.time())
    mkfs = find_tool('mkfs.erofs')
    if not mkfs:
        print("    [X] mkfs.erofs 未找到")
        return 1

    content_dir = detect_content_dir(work, name)
    fc = check_configs(name, work)
    if fc is None:
        return 1
    fixed_fs = prepare_fs_config(name, work, content_dir)
    if fixed_fs is None:
        return 1
    if name == "product":
        fixed_fc = prepare_file_contexts(name, work, content_dir)
        if fixed_fc is None:
            return 1
        fc = fixed_fc

    extra = f'{fmt_alg},{level}' if fmt_alg != 'lz4' else fmt_alg
    src = content_dir + os.sep   # 带尾斜杠（约定）
    out_img = os.path.join(work_output, f'{name}.img')
    cmd = [mkfs, f'-z{extra}', '-T', f'{utc}',
           f'--mount-point=/{name}',
           f'--product-out={work}',
           f'--fs-config-file={fixed_fs}',
           f'--file-contexts={fc}',
           out_img, src]
    return call(cmd)


# ============================================================
#  ext4 打包：make_ext4fs
# ============================================================
def make_ext4fs(name, work, work_output, sparse=False, size=0, utc=None):
    if utc is None:
        utc = int(time.time())
    exe = find_tool('make_ext4fs')
    if not exe:
        print("    [X] make_ext4fs 未找到")
        return 1

    content_dir = detect_content_dir(work, name)
    fc = check_configs(name, work)
    if fc is None:
        return 1
    fixed_fs = prepare_fs_config(name, work, content_dir)
    if fixed_fs is None:
        return 1
    if name == "product":
        fixed_fc = prepare_file_contexts(name, work, content_dir)
        if fixed_fc is None:
            return 1
        fc = fixed_fc

    src = content_dir
    out_img = os.path.join(work_output, f'{name}.img')
    if not size:
        size = folder_size_bytes(src) + 524288   # +512KB 余量
    print(f"    {name}:[{size}]")
    cmd = [exe, '-J', '-T', f'{utc}', '-s' if sparse else '',
           '-S', fc, '-l', f'{size}',
           '-C', fixed_fs, '-L', name, '-a', f'/{name}',
           out_img, src]
    cmd = [c for c in cmd if c]
    return call(cmd)


# ============================================================
#  ext4 打包：mke2fs + e2fsdroid
# ============================================================
def mke2fs(name, work, work_output, sparse=False, size=0, utc=None):
    if utc is None:
        utc = int(time.time())
    mke2fs_exe = find_tool('mke2fs')
    e2fsdroid_exe = find_tool('e2fsdroid')
    if not mke2fs_exe or not e2fsdroid_exe:
        print("    [X] mke2fs 或 e2fsdroid 未找到")
        return 1

    content_dir = detect_content_dir(work, name)
    fc = check_configs(name, work)
    if fc is None:
        return 1
    fixed_fs = prepare_fs_config(name, work, content_dir)
    if fixed_fs is None:
        return 1
    if name == "product":
        fixed_fc = prepare_file_contexts(name, work, content_dir)
        if fixed_fc is None:
            return 1
        fc = fixed_fc

    src = content_dir
    new_img = os.path.join(work_output, f'{name}_new.img')
    if not size:
        size = folder_size_blocks(src)
    print(f"    {name}:[{size}]")
    r = call([mke2fs_exe, '-O',
              '^has_journal,^metadata_csum,extent,huge_file,^flex_bg,^64bit,uninit_bg,dir_nlink,extra_isize',
              '-L', name, '-I', '256', '-M', f'/{name}', '-m', '0', '-t', 'ext4', '-b', '4096',
              new_img, f'{int(size)}'])
    if r != 0:
        _rm(new_img)
        return r
    r = call([e2fsdroid_exe, '-e', '-T', f'{utc}', '-S', fc, '-C', fixed_fs,
              '-a', f'/{name}', '-f', src, new_img])
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
    ext4_packer = sys.argv[5] if len(sys.argv) > 5 else 'make_ext4fs'

    if not os.path.isdir(source_dir):
        print(f"  [!] 源目录不存在: {source_dir}")
        sys.exit(1)

    name = os.path.basename(source_dir)
    work = os.path.dirname(source_dir)
    os.makedirs(output_dir, exist_ok=True)

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
        if ext4_packer == 'mke2fs':
            ret = mke2fs(name, work, output_dir)
        else:
            ret = make_ext4fs(name, work, output_dir)
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
