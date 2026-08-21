#!/usr/bin/env python3
"""
libsurfaceflinger.so CONFIG_GROUP 通用补丁器
============================================
适用: 小米 HyperOS Android 16 (AIDL composer3) 系统 + Android 15 及更老 vendor (HIDL composer 2.x)
      的移植场景, SurfaceFlinger 启动即崩溃循环 "No matching frame rate modes"。

原理: 见同目录 README.md。不依赖硬编码偏移, 通过符号表定位
      HWComposer::getModesFromLegacyDisplayConfigs, 再做指令模式匹配,
      因此对不同的 libsurfaceflinger.so 构建版本有适应性。

用法:
    python3 patch_sf.py <libsurfaceflinger.so 路径> [--dry-run] [--no-backup]

退出码: 0=成功(或dry-run确认可打) 1=错误
"""
import struct, sys, shutil, hashlib, os

# ---------- ELF64 解析(仅标准库) ----------
def parse_sections(data):
    if data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        sys.exit("错误: 不是 ELF64 小端文件")
    e_shoff = struct.unpack_from("<Q", data, 0x28)[0]
    e_shentsize = struct.unpack_from("<H", data, 0x3A)[0]
    e_shnum = struct.unpack_from("<H", data, 0x3C)[0]
    e_shstrndx = struct.unpack_from("<H", data, 0x3E)[0]
    secs = []
    for i in range(e_shnum):
        o = e_shoff + i * e_shentsize
        vals = struct.unpack_from("<IIQQQQIIQQ", data, o)
        secs.append(dict(name_off=vals[0], type=vals[1], addr=vals[3],
                         offset=vals[4], size=vals[5], link=vals[6], entsize=vals[9]))
    shstr = secs[e_shstrndx]
    for s in secs:
        end = data.index(b"\x00", shstr["offset"] + s["name_off"])
        s["name"] = data[shstr["offset"] + s["name_off"]:end].decode()
    return secs

def find_symbol(secs, data, substr):
    """在 .dynsym 里找名字含 substr 且有地址的符号"""
    try:
        ds = next(s for s in secs if s["name"] == ".dynsym")
        st = next(s for s in secs if s["name"] == ".dynstr")
    except StopIteration:
        sys.exit("错误: 缺少符号表(被 strip 过头?)")
    for i in range(ds["size"] // ds["entsize"]):
        o = ds["offset"] + i * ds["entsize"]
        st_name, _info, _other, _shndx, st_value, st_size = struct.unpack_from("<IBBHQQ", data, o)
        end = data.index(b"\x00", st["offset"] + st_name)
        name = data[st["offset"] + st_name:end].decode(errors="ignore")
        if substr in name and st_value:
            return name, st_value, st_size
    return None, 0, 0

def va2off(secs, va):
    for s in secs:
        if s["addr"] and s["addr"] <= va < s["addr"] + s["size"] and s["type"] != 8:  # 非 NOBITS
            return s["offset"] + (va - s["addr"])
    return None

# ---------- 指令判定 ----------
def is_movz_w3_imm7(w):   return w == 0x528000E3          # movz w3, #7
def is_bl(w):             return (w & 0xFC000000) == 0x94000000   # bl imm26
def is_str_w0_sp(w):      # str w0, [sp, #imm]  (Rt=0, Rn=31)
    return (w & 0xFFC003E0) == 0xB90003E0 and (w & 0x1F) == 0
def is_str_wzr_patch(w):  # 已是 str wzr, [sp, #imm] (Rt=31)
    return (w & 0xFFC003E0) == 0xB90003E0 and (w & 0x1F) == 0x1F

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    path = args[0]
    dry = "--dry-run" in flags
    data = bytearray(open(path, "rb").read())
    print(f"目标: {path}  ({len(data)} 字节)")
    print(f"md5(补丁前): {hashlib.md5(data).hexdigest()}")

    secs = parse_sections(bytes(data))

    # ---- 定位函数 ----
    name, va, size = find_symbol(secs, data, "getModesFromLegacyDisplayConfigs")
    if not name:
        sys.exit("错误: 找不到 getModesFromLegacyDisplayConfigs 符号, 此库结构未知, 需人工分析")
    print(f"函数符号: {name}")
    print(f"  VA {va:#x}  size {size:#x}")
    off = va2off(secs, va)
    if off is None:
        sys.exit("错误: 函数地址无法映射到文件偏移")

    n_words = size // 4
    words = [struct.unpack_from("<I", data, off + i * 4)[0] for i in range(n_words)]

    # ---- 候选锚点: movz w3,#7 (待补丁) 或 movz w3,#6 (可能是已打补丁) ----
    anchors = [(i, w == 0x528000E3) for i, w in enumerate(words)
               if w in (0x528000E3, 0x528000C3)]

    idx_a, idx_b, already = [], None, False
    for i, is7 in anchors:
        # 锚点后 10 条内找第一个 bl (getAttribute 调用)
        for j in range(i + 1, min(i + 11, n_words)):
            if not is_bl(words[j]):
                continue
            # bl 后 10 条内找第一条 str w?, [sp, #imm]
            for k in range(j + 1, min(j + 11, n_words)):
                w = words[k]
                if is_str_w0_sp(w):
                    if is7:
                        idx_a, idx_b = [i], k   # 可打补丁的完整链
                    break
                if is_str_wzr_patch(w):
                    if not is7:                # #6 + str wzr = 我们打过的补丁
                        already = True
                    break
            break
        if idx_b is not None or already:
            break

    if already:
        print("结论: 该库已是补丁状态, 无操作。")
        return
    if idx_b is None:
        sys.exit("错误: 未找到 configGroup 存储指令(str w0,[sp,#imm]), 库结构变化, 需人工分析")
    a_desc = f"补丁A: VA {va + idx_a[0]*4:#x}  movz w3,#7 -> movz w3,#6   (应用)" if idx_a else "补丁A: 跳过(未找到 movz w3,#7, 不影响核心修复)"
    print(a_desc)
    print(f"补丁B: VA {va + idx_b*4:#x}  str w0,[sp,#imm] -> str wzr   (核心)")

    if dry:
        print("\n[dry-run] 未写入。确认以上定位正确后去掉 --dry-run 执行。")
        return

    if not "--no-backup" in flags:
        bak = path + ".bak"
        shutil.copy2(path, bak)
        print(f"已备份 -> {bak}")

    if idx_a:
        struct.pack_into("<I", data, off + idx_a[0] * 4, 0x528000C3)
    struct.pack_into("<I", data, off + idx_b * 4, (words[idx_b] & ~0x1F) | 0x1F)
    open(path, "wb").write(data)
    print(f"md5(补丁后): {hashlib.md5(data).hexdigest()}")
    print("完成。将该文件放回镜像树并重打包。")

if __name__ == "__main__":
    main()
