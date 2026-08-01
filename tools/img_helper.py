#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IMG 解打包工具 - Python 辅助脚本
提供镜像格式检测、分区信息解析等辅助功能

二进制工具说明：
  simg2img.exe     - Android sparse image → raw image 转换
                    Sparse 是 Android 的压缩格式，刷机前需转为 Raw
  img2simg.exe     - raw image → sparse image 转换（压缩用）
  lpunpack.exe     - 解包 super.img（Android 动态分区容器）
                    super.img 内含 system/vendor/product 等分区
  lpmake.exe       - 打包 super.img（将多个分区合成一个）
  lpdumps.exe      - 查看 super.img 的分区布局信息
  ext2simg.exe     - ext2/ext4 文件系统镜像 ↔ sparse 转换
  payload-dumper-go - 从 OTA 刷机包中提取分区镜像
"""

import sys
import os
import struct
import json
import subprocess
import shutil
from pathlib import Path


# ============================================
#   常量定义
# ============================================

# Android sparse image 
SPARSE_MAGIC = 0xED26FF3A

# super.img 分区类型
LP_PARTITION_TYPES = {
    "readonly": "只读分区（system, vendor 等）",
    "readwrite": "可读写分区（userdata）",
}

# 已知的 Android 分区名
KNOWN_PARTITIONS = [
    "system", "vendor", "product", "odm", "system_ext",
    "vendor_dlkm", "system_dlkm", "odm_dlkm",
    "mi_ext", "cust", "preload",
]


def detect_image_format(filepath):
    """
    检测镜像文件格式
    
    Android 镜像有两种主要格式：
    1. Raw (原始格式) - 完整的磁盘镜像，可以直接 mount
    2. Sparse (稀疏格式) - 压缩格式，跳过全零块，节省空间
    
    检测方法：读取文件头部 4 字节的魔数
    - 0xED26FF3A = Sparse 格式
    - 其他 = Raw 格式（通常以 ext4/squashfs 等文件系统头开始）
    """
    try:
        with open(filepath, 'rb') as f:
            header = f.read(4)
            if len(header) < 4:
                return "UNKNOWN", "文件太小"
            
            magic = struct.unpack('<I', header)[0]
            
            if magic == SPARSE_MAGIC:
                return "SPARSE", "Android Sparse Image（稀疏镜像）"
            else:
                # 检查是否为 ext4
                # ext4 超级块魔数位于偏移 0x438，值为 0xEF53
                f.seek(0x438)
                ext4_magic = f.read(2)
                if len(ext4_magic) == 2 and struct.unpack('<H', ext4_magic)[0] == 0xEF53:
                    return "RAW_EXT4", "Raw EXT4 镜像"
                
                # 检查是否为 erofs
                # erofs 超级块魔数位于偏移 0x400，值为 0xE0F5E1E2
                f.seek(0x400)
                erofs_magic = f.read(4)
                if len(erofs_magic) == 4 and struct.unpack('<I', erofs_magic)[0] == 0xE0F5E1E2:
                    return "RAW_EROFS", "Raw EROFS 镜像"
                
                return "RAW", "Raw 镜像（未知文件系统）"
    except Exception as e:
        return "ERROR", f"检测失败: {e}"


def get_file_size_str(size_bytes):
    """将字节数转换为人类可读的大小字符串"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / 1024 / 1024:.1f} MB"
    else:
        return f"{size_bytes / 1024 / 1024 / 1024:.2f} GB"


def scan_directory_images(dirpath):
    """扫描目录中的所有 img 文件，返回格式和大小信息"""
    results = []
    if not os.path.isdir(dirpath):
        return results
    
    for f in sorted(os.listdir(dirpath)):
        if f.lower().endswith('.img'):
            fpath = os.path.join(dirpath, f)
            fmt, desc = detect_image_format(fpath)
            size = os.path.getsize(fpath)
            results.append({
                "name": f,
                "path": fpath,
                "format": fmt,
                "format_desc": desc,
                "size": size,
                "size_str": get_file_size_str(size),
            })
    
    return results


def super_info(filepath, lpdumps_path):
    """获取 super.img 的分区信息"""
    try:
        result = subprocess.run(
            [lpdumps_path, filepath],
            capture_output=True, text=True, timeout=30
        )
        return result.stdout + result.stderr
    except Exception as e:
        return f"获取信息失败: {e}"


def check_tool_exists(tool_path):
    """检查工具是否存在且可执行"""
    return os.path.isfile(tool_path) and os.path.getsize(tool_path) > 0


def get_tools_status(tools_dir):
    """检查所有工具的状态"""
    tools = {
        "simg2img.exe": "Sparse → Raw 格式转换",
        "img2simg.exe": "Raw → Sparse 格式转换",
        "lpunpack.exe": "解包 Super 分区",
        "lpmake.exe": "打包 Super 分区",
        "lpdumps.exe": "查看 Super 分区信息",
        "ext2simg.exe": "EXT4 ↔ Sparse 转换",
        "payload-dumper-go.exe": "OTA payload 提取",
    }
    
    status = {}
    for tool, desc in tools.items():
        path = os.path.join(tools_dir, tool)
        exists = check_tool_exists(path)
        size = os.path.getsize(path) if exists else 0
        status[tool] = {
            "exists": exists,
            "size": size,
            "size_str": get_file_size_str(size) if exists else "缺失",
            "desc": desc,
        }
    
    return status


def batch_convert_s2r(input_dir, output_dir, simg2img_path):
    """批量将 Sparse 镜像转换为 Raw 格式"""
    results = []
    os.makedirs(output_dir, exist_ok=True)
    
    images = scan_directory_images(input_dir)
    for img in images:
        if img["format"] == "SPARSE":
            out_path = os.path.join(output_dir, img["name"])
            try:
                subprocess.run(
                    [simg2img_path, img["path"], out_path],
                    check=True, timeout=300
                )
                results.append({
                    "name": img["name"],
                    "status": "成功",
                    "input_size": img["size_str"],
                    "output_size": get_file_size_str(os.path.getsize(out_path)),
                })
            except Exception as e:
                results.append({
                    "name": img["name"],
                    "status": f"失败: {e}",
                    "input_size": img["size_str"],
                    "output_size": "-",
                })
        else:
            results.append({
                "name": img["name"],
                "status": "跳过（非 Sparse）",
                "input_size": img["size_str"],
                "output_size": "-",
            })
    
    return results


def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("用法:")
        print("  python img_helper.py detect <file.img>     检测镜像格式")
        print("  python img_helper.py scan <directory>       扫描目录中的镜像")
        print("  python img_helper.py tools <tools_dir>      检查工具状态")
        print("  python img_helper.py super_info <file> <lpdumps>  查看 Super 信息")
        return
    
    cmd = sys.argv[1]
    
    if cmd == "detect" and len(sys.argv) >= 3:
        filepath = sys.argv[2]
        if not os.path.isfile(filepath):
            print(f"ERROR: 文件不存在: {filepath}")
            return
        fmt, desc = detect_image_format(filepath)
        size = get_file_size_str(os.path.getsize(filepath))
        print(f"FORMAT:{fmt}")
        print(f"DESC:{desc}")
        print(f"SIZE:{size}")
    
    elif cmd == "scan" and len(sys.argv) >= 3:
        dirpath = sys.argv[2]
        results = scan_directory_images(dirpath)
        for r in results:
            print(f"{r['name']}|{r['format']}|{r['format_desc']}|{r['size_str']}")
    
    elif cmd == "tools" and len(sys.argv) >= 3:
        tools_dir = sys.argv[2]
        status = get_tools_status(tools_dir)
        for name, info in status.items():
            state = "OK" if info["exists"] else "MISSING"
            print(f"{name}|{state}|{info['size_str']}|{info['desc']}")
    
    elif cmd == "super_info" and len(sys.argv) >= 4:
        filepath = sys.argv[2]
        lpdumps = sys.argv[3]
        print(super_info(filepath, lpdumps))
    
    else:
        print(f"未知命令: {cmd}")


if __name__ == "__main__":
    main()
