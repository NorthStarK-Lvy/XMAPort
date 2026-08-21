#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import shutil
import subprocess
import time
from pathlib import Path

# Powered By ClaudeCode, DeepSeek, Xiaomi MiMO, GLM and TiramisuX.

# Global state
g_os_version = ""


# -----------------------------------------------------------------------------
# Logging helpers (ANSI escape codes, works in terminal + CI)
# -----------------------------------------------------------------------------
_G = "\033[92m"   # green
_R = "\033[91m"   # red
_Y = "\033[93m"   # yellow
_D = "\033[90m"   # gray
_B = "\033[94m"   # blue
_N = "\033[0m"    # reset


def LOG_INFO(msg):
    print("  " + _G + "[INFO]" + _N + "  " + str(msg))


def LOG_ERROR(msg):
    print("  " + _R + "[ERROR]" + _N + " " + str(msg), file=sys.stderr)


def LOG_DEBUG(msg):
    print("  " + _D + "[DEBUG]" + _N + " " + str(msg))


def _log_info_blue(msg):
    print("  " + _G + "[INFO]" + _N + "  " + _B + str(msg) + _N)


# -----------------------------------------------------------------------------
# Path / file helpers
# -----------------------------------------------------------------------------
def int_to_str(n):
    return str(n)


def get_exe_directory():
    return os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep


def get_parent_dir(exe_dir):
    return os.path.dirname(exe_dir.rstrip(os.sep)) + os.sep


def copy_file_overwrite(src, dest):
    try:
        shutil.copy2(src, dest)
        return True
    except Exception:
        pass
    if os.path.exists(dest):
        try:
            os.remove(dest)
            shutil.copy2(src, dest)
            return True
        except Exception:
            return False
    return False


def copy_file_nooverwrite(src, dest):
    if os.path.exists(dest):
        LOG_DEBUG("  File already exists, skipping: " + dest)
        return True
    try:
        shutil.copy2(src, dest)
        return True
    except Exception:
        return False


def move_file_overwrite(src, dest):
    try:
        os.replace(src, dest)
        return True
    except Exception:
        try:
            shutil.move(src, dest)
            return True
        except Exception:
            return False


def get_files_in_dir(dir_path):
    files = []
    if not os.path.isdir(dir_path):
        return files
    for name in os.listdir(dir_path):
        full = os.path.join(dir_path, name)
        if os.path.isfile(full):
            files.append(full)
    return files


def get_file_name(full_path):
    return os.path.basename(full_path)


def find_directory(start_dir, target_dir_name):
    if not os.path.isdir(start_dir):
        return ""
    for root, dirs, files in os.walk(start_dir):
        if target_dir_name in dirs:
            return os.path.join(root, target_dir_name) + os.sep
    return ""


def find_file(start_dir, target_file_name):
    if not os.path.isdir(start_dir):
        return ""
    target = target_file_name.lower()
    for root, dirs, files in os.walk(start_dir):
        for name in files:
            if name.lower() == target:
                return os.path.join(root, name)
    return ""


def find_file_any(start_dir, target_names):
    if not os.path.isdir(start_dir):
        return ""
    targets = [n.lower() for n in target_names]
    for root, dirs, files in os.walk(start_dir):
        for name in files:
            if name.lower() in targets:
                return os.path.join(root, name)
    return ""


def trim_str(s):
    return s.strip(" \t\r\n")


def to_lower_str(s):
    return s.lower()


def contains_ignore_case(s, pat):
    if not pat:
        return False
    s = s.lower()
    pat = pat.lower()
    return pat in s


def starts_with_ignore_case(s, prefix):
    return s.lower().startswith(prefix.lower())


def ends_with_xml_ignore_case(s):
    return s.lower().endswith(".xml")


def collect_matching_files(dir_path, patterns):
    matches = []
    if not os.path.isdir(dir_path):
        return matches
    for root, dirs, files in os.walk(dir_path):
        for name in files:
            for pat in patterns:
                if contains_ignore_case(name, pat):
                    matches.append(os.path.join(root, name))
                    break
    return matches


def remove_dir_recursive(dir_path):
    if not os.path.isdir(dir_path):
        return True
    try:
        shutil.rmtree(dir_path, ignore_errors=True)
        return True
    except Exception:
        return False


def copy_dir_recursive(src_dir, dest_dir):
    if not os.path.isdir(src_dir):
        return False
    os.makedirs(dest_dir, exist_ok=True)
    for item in os.listdir(src_dir):
        s = os.path.join(src_dir, item)
        d = os.path.join(dest_dir, item)
        if os.path.isdir(s):
            if not copy_dir_recursive(s, d):
                return False
        else:
            try:
                shutil.copy2(s, d)
            except Exception:
                return False
    return True


# -----------------------------------------------------------------------------
# Java lookup: look for a bundled JRE under tools/jre, otherwise fall back
# to JAVA_HOME / system PATH / common install directories.
# -----------------------------------------------------------------------------
def find_java_path():
    exe_dir = get_exe_directory()

    bundled = os.path.join(exe_dir, "jre", "bin", "java.exe")
    if os.path.exists(bundled):
        return bundled

    java_home = os.environ.get("JAVA_HOME", "")
    if java_home:
        jh_java = os.path.join(java_home, "bin", "java.exe")
        if os.path.exists(jh_java):
            return jh_java

    try:
        ret = subprocess.call("java -version >nul 2>nul", shell=True)
        if ret == 0:
            return "java"
    except Exception:
        pass

    search_paths = [
        r"C:\Program Files\Java",
        r"C:\Program Files (x86)\Java",
        r"C:\Program Files\OpenJDK",
    ]
    for sp in search_paths:
        if not os.path.isdir(sp):
            continue
        for name in os.listdir(sp):
            lower = name.lower()
            if lower.startswith("jdk") or lower.startswith("jre") or lower.startswith("openjdk"):
                candidate = os.path.join(sp, name, "bin", "java.exe")
                if os.path.exists(candidate):
                    return candidate

    LOG_ERROR("Java runtime not found. Please place jre under tools/jre or install Java / set JAVA_HOME.")
    return ""


# -----------------------------------------------------------------------------
# OS version detection
# -----------------------------------------------------------------------------
def read_build_prop_key(path, key):
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.rstrip("\r\n")
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip().lower() == key.lower():
                    return v.strip()
    except Exception:
        pass
    return ""


def detect_os_version(parent_dir):
    global g_os_version
    g_os_version = ""
    mi_ext_prop = os.path.join(parent_dir, "workspace", "source_filesystem", "mi_ext", "etc", "build.prop")
    val = read_build_prop_key(mi_ext_prop, "ro.mi.os.version.code")
    if val:
        g_os_version = val
        _log_info_blue("OS version: " + val + " [mi_ext build.prop]")
        return
    product_prop = os.path.join(parent_dir, "workspace", "source_filesystem", "product", "etc", "build.prop")
    val = read_build_prop_key(product_prop, "ro.product.build.version.incremental")
    if val:
        g_os_version = val
        _log_info_blue("OS version: " + val + " [product build.prop]")
        return
    _log_info_blue("OS version: unknown (no mi_ext/product build.prop found)")


# -----------------------------------------------------------------------------
# Pipeline steps
# -----------------------------------------------------------------------------
def sync_features(parent_dir):
    LOG_INFO("")
    LOG_INFO("========================================")
    LOG_INFO("  Synchronize device_features")
    LOG_INFO("========================================")

    config_path = os.path.join(parent_dir, "workspace", "config.txt")
    LOG_INFO("Reading config: " + config_path)
    target_name = ""
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.rstrip("\r\n")
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if trim_str(k).lower() == "target_device":
                    target_name = trim_str(v)
                    break

    if not target_name:
        LOG_INFO("TARGET_DEVICE not set or empty in config.txt, no modification made, skipping.")
        return 0
    LOG_INFO("TARGET_DEVICE: " + target_name)

    source_dir = os.path.join(parent_dir, "workspace", "source_filesystem", "product", "etc", "device_features")
    if not os.path.isdir(source_dir):
        LOG_INFO("Could not find 'device_features' under " + parent_dir + "workspace\\source_filesystem\\product\\etc, skipping.")
        return 0
    LOG_INFO("Found source directory: " + source_dir)

    dest_path = os.path.join(source_dir, target_name + ".xml")
    if os.path.exists(dest_path):
        LOG_INFO("Target file already exists, skipping: " + dest_path)
        return 0

    source_files = get_files_in_dir(source_dir)
    source_files.sort()

    for src in source_files:
        fname = get_file_name(src)
        if len(fname) < 4 or fname[-4:].lower() != ".xml":
            continue
        if src == dest_path:
            continue
        LOG_INFO("  Rename: " + src + " -> " + dest_path)
        if move_file_overwrite(src, dest_path):
            LOG_INFO("device_features synchronization completed.")
            LOG_INFO("========================================")
            return 0
        else:
            LOG_ERROR("  Rename failed.")
            return 1

    LOG_ERROR("No .xml file found in " + source_dir)
    return 1


def clean_miui_booster(parent_dir):
    LOG_INFO("")
    LOG_INFO("========================================")
    LOG_INFO("  Clean MiuiBooster (DeviceLevelUtils/LiteUtils)")
    LOG_INFO("========================================")

    lower_osv = g_os_version.lower()
    is_os4 = (lower_osv == "4" or lower_osv == "4.0" or lower_osv == "os4.0"
              or lower_osv.startswith("os4"))
    if is_os4:
        LOG_INFO("OS version = " + g_os_version + ", skip CleanMiuiBooster.")
        return 0

    build_prop_path = os.path.join(parent_dir, "workspace", "source_filesystem", "product", "etc", "build.prop")
    if os.path.exists(build_prop_path):
        with open(build_prop_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.rstrip("\r\n")
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if trim_str(k).lower() == "ro.product.build.version.incremental":
                    val = trim_str(v).lower()
                    if "v13" in val and "dev" in val:
                        LOG_INFO("ro.product.build.version.incremental=" + trim_str(v) + " (DEV build), skip CleanMiuiBooster.")
                        return 0
                    break

    search_root = os.path.join(parent_dir, "workspace", "source_filesystem")
    exe_dir = get_exe_directory()
    LOG_INFO("Searching for MiuiBooster.jar under: " + search_root)

    jar_path = ""
    if os.path.isdir(search_root):
        for root, dirs, files in os.walk(search_root):
            for name in files:
                if name.lower() == "miuibooster.jar":
                    full = os.path.join(root, name)
                    if os.path.getsize(full) > 1024:
                        jar_path = full
                        break
            if jar_path:
                break
        if jar_path:
            pass

    if not jar_path:
        LOG_INFO("No valid MiuiBooster.jar found (all candidates are empty stubs).")
        return 0
    LOG_INFO("Found: " + jar_path)

    apktool_path = os.path.join(exe_dir, "apktool.jar")
    if not os.path.exists(apktool_path):
        LOG_ERROR("apktool.jar not found at: " + apktool_path)
        return 1
    LOG_INFO("apktool: " + apktool_path)

    java_path = find_java_path()
    if not java_path:
        LOG_ERROR("Cannot run apktool: Java not found. Install Java or set JAVA_HOME.")
        return 1
    LOG_INFO("java:   " + java_path)

    temp_dir = os.path.join(parent_dir, "workspace", "temp_miubooster_" + int_to_str(os.getpid()))
    remove_dir_recursive(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)

    out_path = jar_path + ".cleaned"
    if os.path.exists(out_path):
        os.remove(out_path)
    sys.stdout.flush()

    # Decode
    cmd = 'cmd.exe /c ""{}" -jar "{}" d -f "{}" -o "{}""'.format(java_path, apktool_path, jar_path, temp_dir)
    LOG_INFO("Decoding: " + cmd)
    ret = subprocess.call(cmd, shell=True)
    if ret != 0:
        LOG_ERROR("apktool decode failed with code: " + int_to_str(ret))
        remove_dir_recursive(temp_dir)
        return 1
    LOG_INFO("apktool decode done.")

    # Delete DeviceLevelUtils and LiteUtils smali
    smali_root = os.path.join(temp_dir, "smali")
    to_delete = collect_matching_files(smali_root, ["DeviceLevelUtils", "LiteUtils"])
    to_delete.sort()
    if not to_delete:
        LOG_INFO("No DeviceLevelUtils/LiteUtils smali files found.")
    else:
        for item in to_delete:
            try:
                os.remove(item)
                LOG_INFO("  Removed: " + item)
            except Exception:
                LOG_ERROR("  Delete failed: " + item)
        LOG_INFO("Removed " + int_to_str(len(to_delete)) + " DeviceLevelUtils/LiteUtils smali file(s).")

    # Rebuild
    cmd = 'cmd.exe /c ""{}" -jar "{}" b "{}" -o "{}""'.format(java_path, apktool_path, temp_dir, out_path)
    LOG_INFO("Rebuilding: " + cmd)
    ret = subprocess.call(cmd, shell=True)
    if ret != 0:
        LOG_ERROR("apktool rebuild failed with code: " + int_to_str(ret))
        remove_dir_recursive(temp_dir)
        return 1
    LOG_INFO("apktool rebuild done.")

    remove_dir_recursive(temp_dir)

    if not os.path.exists(out_path):
        LOG_ERROR("apktool output not found: " + out_path)
        return 1

    backup_path = jar_path + ".bak"
    if os.path.exists(backup_path):
        os.remove(backup_path)
    if not move_file_overwrite(jar_path, backup_path):
        LOG_ERROR("Could not create the original JAR backup.")
        return 1
    if not move_file_overwrite(out_path, jar_path):
        LOG_ERROR("Could not install the cleaned MiuiBooster.jar; restoring backup.")
        move_file_overwrite(backup_path, jar_path)
        return 1
    LOG_INFO("MiuiBooster.jar cleaned and installed successfully.")
    LOG_INFO("Original backup: " + backup_path)
    LOG_INFO("========================================")
    return 0


def sync_apex(parent_dir):
    LOG_INFO("")
    LOG_INFO("========================================")
    LOG_INFO("  Synchronize VNDK apex + vintf")
    LOG_INFO("========================================")

    source_root = os.path.join(parent_dir, "workspace", "source_filesystem")
    target_root = os.path.join(parent_dir, "workspace", "target_filesystem")

    vndk_version = ""
    vndk_prop_file = ""
    prop_files = collect_matching_files(os.path.join(target_root, "odm", "etc"), [".prop"])
    prop_files.sort()
    for pf in prop_files:
        if vndk_version:
            break
        try:
            with open(pf, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.rstrip("\r\n")
                    if "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    if trim_str(k) == "ro.odm.build.version.sdk":
                        vndk_version = trim_str(v)
                        vndk_prop_file = pf
                        break
        except Exception:
            pass

    if not vndk_version:
        LOG_INFO("ro.odm.build.version.sdk not found in base ROM (target) odm\\etc *.prop, no modification made, skipping.")
        return 0
    LOG_INFO("VNDK version: " + vndk_version + " (from " + vndk_prop_file + ")")

    apex_file_name = "com.android.vndk.v" + vndk_version + ".apex"
    source_apex_dir = os.path.join(source_root, "system_ext", "apex")
    target_apex_dir = os.path.join(target_root, "system_ext", "apex")

    source_apex = ""
    if os.path.isdir(source_apex_dir):
        LOG_INFO("Port ROM (source) apex dir: " + source_apex_dir)
        cand = os.path.join(source_apex_dir, apex_file_name)
        if os.path.exists(cand):
            source_apex = cand
    else:
        LOG_INFO("No 'apex' directory found in source (port ROM) system_ext.")

    target_apex = ""
    if os.path.isdir(target_apex_dir):
        LOG_INFO("Base ROM (target) apex dir: " + target_apex_dir)
        cand = os.path.join(target_apex_dir, apex_file_name)
        if os.path.exists(cand):
            target_apex = cand
    else:
        LOG_INFO("No 'apex' directory found in base ROM (target) system_ext.")

    if source_apex:
        LOG_INFO("Port ROM already has " + apex_file_name + ", no copy needed.")
    elif not target_apex:
        LOG_INFO("Base ROM has no " + apex_file_name + " either, nothing to copy.")
    elif not os.path.isdir(source_apex_dir):
        LOG_INFO("No 'apex' directory in port ROM to place the VNDK apex into, skipping copy.")
    else:
        dest_path = os.path.join(source_apex_dir, apex_file_name)
        LOG_INFO("VNDK apex missing in port ROM, copying from base ROM: " + target_apex + " -> " + dest_path)
        if copy_file_overwrite(target_apex, dest_path):
            LOG_INFO("VNDK apex copied.")
        else:
            LOG_ERROR("Failed to copy VNDK apex: " + target_apex)
            return 1

    manifest_path = os.path.join(source_root, "system_ext", "etc", "vintf", "manifest.xml")
    if not os.path.exists(manifest_path):
        LOG_INFO("No system_ext/etc/vintf/manifest.xml in port ROM (source), no modification made, skipping vintf patch.")
        return 0
    LOG_INFO("Vintf manifest: " + manifest_path)

    has_version = False
    needle = "<version>" + vndk_version + "</version>"
    try:
        with open(manifest_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if needle in line:
                    has_version = True
                    break
    except Exception:
        pass

    if has_version:
        LOG_INFO("VNDK version " + vndk_version + " already declared in manifest, no modification made, skipping.")
        return 0

    closer_count = 0
    try:
        with open(manifest_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "</vendor-ndk>" in line:
                    closer_count += 1
    except Exception:
        pass

    if closer_count == 0:
        LOG_INFO("No existing </vendor-ndk> block found in manifest, no modification made, skipping.")
        return 0

    backup_path = manifest_path + ".bak"
    if os.path.exists(backup_path):
        os.remove(backup_path)
    try:
        shutil.copy2(manifest_path, backup_path)
    except Exception:
        LOG_ERROR("Could not create backup: " + manifest_path)
        return 1

    ndk_block = "<vendor-ndk>\n     <version>" + vndk_version + "</version>\n </vendor-ndk>"
    appended = 0
    kept_lines = []
    try:
        with open(manifest_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.rstrip("\r\n")
                kept_lines.append(line)
                if "</vendor-ndk>" in line:
                    kept_lines.append(ndk_block)
                    appended += 1
    except Exception:
        LOG_ERROR("Could not open manifest for rewriting: " + manifest_path)
        return 1

    try:
        with open(manifest_path, "w", encoding="utf-8", errors="ignore") as f:
            for line in kept_lines:
                f.write(line + "\n")
    except Exception:
        LOG_ERROR("Write failed; restoring backup: " + manifest_path)
        move_file_overwrite(backup_path, manifest_path)
        return 1

    LOG_INFO("VNDK apex sync done. <vendor-ndk> blocks appended: " + int_to_str(appended) + ". Backup: " + backup_path)
    LOG_INFO("========================================")
    return 0


def clean_vk_props(parent_dir):
    LOG_INFO("")
    LOG_INFO("========================================")
    LOG_INFO("  Remove vk props from product build.prop")
    LOG_INFO("========================================")

    prop_path = os.path.join(parent_dir, "workspace", "source_filesystem", "product", "etc", "build.prop")
    if not os.path.exists(prop_path):
        LOG_INFO("build.prop not found: " + prop_path + ", skipping.")
        return 0
    LOG_INFO("Found: " + prop_path)

    try:
        with open(prop_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        LOG_ERROR("Could not open build.prop for reading.")
        return 1

    kept_lines = []
    removed = 0
    for line in lines:
        original = line.rstrip("\r\n")
        drop = False
        if original and not original.startswith("#"):
            eq = original.find("=")
            key = original[:eq] if eq != -1 else original
            if "vk" in key.lower():
                drop = True
        if drop:
            removed += 1
            LOG_INFO("  Removing prop: " + original)
        else:
            kept_lines.append(original)

    if removed == 0:
        LOG_INFO("No vk props found, build.prop left untouched.")
        return 0

    backup_path = prop_path + ".bak"
    try:
        shutil.copy2(prop_path, backup_path)
    except Exception:
        LOG_ERROR("Could not create build.prop backup.")
        return 1

    try:
        with open(prop_path, "w", encoding="utf-8", errors="ignore") as f:
            for line in kept_lines:
                f.write(line + "\n")
    except Exception:
        LOG_ERROR("Write failed; restoring backup.")
        move_file_overwrite(backup_path, prop_path)
        return 1

    LOG_INFO("Removed " + int_to_str(removed) + " vk prop(s). Backup: " + backup_path)
    LOG_INFO("========================================")
    return 0


def clean_data_apps(parent_dir, extreme=False):
    LOG_INFO("")
    LOG_INFO("========================================")
    LOG_INFO("  Remove preinstalled apps from data-app")
    if extreme:
        LOG_INFO("  *** EXTREME SLIMMING MODE ***")
    LOG_INFO("========================================")

    base_dir = os.path.join(parent_dir, "workspace", "source_filesystem", "product")
    data_app_dir = os.path.join(base_dir, "data-app")
    if not os.path.isdir(data_app_dir):
        data_app_dir = os.path.join(base_dir, "data_app")
        if not os.path.isdir(data_app_dir):
            LOG_INFO("No data-app or data_app found under " + base_dir)
            return 0
    LOG_INFO("Found: " + data_app_dir)

    targets = ["music", "video", "youpin", "newhome", "game", "duokan", "iflytek", "mishop"]
    if extreme:
        extra = ["home", "extraphoto", "wps", "control", "baidu"]
        targets += extra
        LOG_INFO("Extreme mode additional keywords: " + ", ".join(extra))
    LOG_INFO("Target keywords: " + ", ".join(targets))

    removed = 0
    for name in os.listdir(data_app_dir):
        full = os.path.join(data_app_dir, name)
        if not os.path.isdir(full):
            continue
        lower = name.lower()
        matched = any(t in lower for t in targets)
        if matched:
            LOG_INFO("  Removing: " + name)
            if remove_dir_recursive(full):
                removed += 1
            else:
                LOG_ERROR("  Failed to remove: " + name)

    LOG_INFO("Removed " + int_to_str(removed) + " preinstalled app(s).")
    LOG_INFO("========================================")
    return 0


def patch_build_prop(parent_dir):
    LOG_INFO("")
    LOG_INFO("========================================")
    LOG_INFO("  Patch build prop from config.ini")
    LOG_INFO("========================================")

    ini_path = os.path.join(parent_dir, "config.ini")
    target_prop = os.path.join(parent_dir, "workspace", "target_filesystem", "odm", "etc", "build.prop")
    LOG_INFO("config.ini: " + ini_path)
    LOG_INFO("target build.prop: " + target_prop)

    patch_lines = []
    if os.path.exists(ini_path):
        with open(ini_path, "r", encoding="utf-8", errors="ignore") as f:
            in_patch = False
            for line in f:
                line = line.rstrip("\r\n")
                if not in_patch:
                    if trim_str(line).lower() == "; patch build prop list":
                        in_patch = True
                    continue
                if line and line.startswith("["):
                    break
                patch_lines.append(line)

    if not patch_lines:
        LOG_INFO("No '; patch build prop list' section found in config.ini, no modification made, skipping.")
        return 0

    if not os.path.exists(target_prop):
        LOG_INFO("Target build.prop not found, no modification made, skipping: " + target_prop)
        return 0

    need_newline = True
    try:
        with open(target_prop, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size > 0:
                f.seek(-1, 2)
                last = f.read(1)
                if last == b"\n":
                    need_newline = False
    except Exception:
        pass

    extra = 0
    try:
        with open(target_prop, "a", encoding="utf-8", errors="ignore") as f:
            if need_newline:
                f.write("\n")
            for line in patch_lines:
                f.write(line + "\n")

            lower_osv = g_os_version.lower()
            is_os4 = (lower_osv == "4" or lower_osv == "4.0" or lower_osv == "os4.0"
                      or lower_osv.startswith("os4"))
            if is_os4:
                LOG_INFO("OS4 detected, appending Vulkan/Skia renderer props:")
                f.write("debug.renderengine.vulkan=true\n")
                LOG_INFO("  + debug.renderengine.vulkan=true")
                f.write("debug.hwui.renderer=skiavk\n")
                LOG_INFO("  + debug.hwui.renderer=skiavk")
                f.write("ro.hwui.use_vulkan=true\n")
                LOG_INFO("  + ro.hwui.use_vulkan=true")
                f.write("debug.renderengine.backend=skiavkthreaded\n")
                LOG_INFO("  + debug.renderengine.backend=skiavkthreaded")
                f.write("debug.stagefright.renderengine.backend=threaded\n")
                LOG_INFO("  + debug.stagefright.renderengine.backend=threaded")
                extra = 5
    except Exception:
        LOG_ERROR("Write failed for target build.prop.")
        return 1

    LOG_INFO("Appended " + int_to_str(len(patch_lines) + extra) + " line(s) to target build.prop.")
    LOG_INFO("========================================")
    return 0


def extract_int_attr_value(line, attr_name):
    key = 'name="' + attr_name + '"'
    pos = line.find(key)
    if pos == -1:
        return ""
    pos = line.find(">", pos)
    if pos == -1:
        return ""
    end = line.find("</integer>", pos)
    if end == -1:
        return ""
    return line[pos + 1:end]


def replace_int_attr_value(line, attr_name, new_value):
    key = 'name="' + attr_name + '"'
    pos = line.find(key)
    if pos == -1:
        return line
    pos = line.find(">", pos)
    if pos == -1:
        return line
    end = line.find("</integer>", pos)
    if end == -1:
        return line
    return line[:pos + 1] + new_value + line[end:]


def sync_fps_list(parent_dir):
    LOG_INFO("")
    LOG_INFO("========================================")
    LOG_INFO("  Synchronize fpsList + smart_fps_value")
    LOG_INFO("========================================")

    target_name = ""
    config_path = os.path.join(parent_dir, "workspace", "config.txt")
    LOG_INFO("Reading config: " + config_path)
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.rstrip("\r\n")
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if trim_str(k).lower() == "target_device":
                    target_name = trim_str(v)
                    break

    if not target_name:
        LOG_INFO("TARGET_DEVICE not set or empty in config.txt, no modification made, skipping.")
        return 0
    LOG_INFO("TARGET_DEVICE: " + target_name)

    target_xml = os.path.join(parent_dir, "workspace", "target_filesystem", "product", "etc", "device_features", target_name + ".xml")
    if not os.path.exists(target_xml):
        LOG_INFO("Target device_features XML not found, no modification made, skipping: " + target_xml)
        return 0
    LOG_INFO("Target XML: " + target_xml)

    target_items = []
    target_smart_fps = ""
    try:
        with open(target_xml, "r", encoding="utf-8", errors="ignore") as f:
            in_array = False
            for line in f:
                line = line.rstrip("\r\n")
                trimmed = trim_str(line)
                if not in_array:
                    if '<integer-array name="fpsList">' in trimmed:
                        in_array = True
                        continue
                    sf = extract_int_attr_value(trimmed, "smart_fps_value")
                    if sf:
                        target_smart_fps = sf
                    continue
                if "</integer-array>" in trimmed:
                    break
                if "<item>" in trimmed and "</item>" in trimmed:
                    target_items.append(trimmed)
    except Exception:
        pass

    if not target_items:
        LOG_INFO("No fpsList items found in target XML, no modification made, skipping.")
        return 0
    LOG_INFO("Target fpsList items (" + int_to_str(len(target_items)) + "):")
    for item in target_items:
        LOG_INFO("  " + item)
    LOG_INFO("Target smart_fps_value: " + (target_smart_fps if target_smart_fps else "(not found)"))

    source_xml = os.path.join(parent_dir, "workspace", "source_filesystem", "product", "etc", "device_features", target_name + ".xml")
    if not os.path.exists(source_xml):
        LOG_INFO("Source device_features XML not found (was it renamed?), no modification made, skipping: " + source_xml)
        return 0
    LOG_INFO("Source XML: " + source_xml)

    source_items = []
    source_smart_fps = ""
    try:
        with open(source_xml, "r", encoding="utf-8", errors="ignore") as f:
            in_array = False
            for line in f:
                line = line.rstrip("\r\n")
                trimmed = trim_str(line)
                if not in_array:
                    if '<integer-array name="fpsList">' in trimmed:
                        in_array = True
                        continue
                    sf = extract_int_attr_value(trimmed, "smart_fps_value")
                    if sf:
                        source_smart_fps = sf
                    continue
                if "</integer-array>" in trimmed:
                    break
                if "<item>" in trimmed and "</item>" in trimmed:
                    source_items.append(trimmed)
    except Exception:
        pass

    if not source_items:
        LOG_INFO("No fpsList found in source XML, no modification made, skipping.")
        return 0

    fps_differ = source_items != target_items
    smart_differ = (target_smart_fps and source_smart_fps and source_smart_fps != target_smart_fps)
    if not fps_differ and not smart_differ:
        LOG_INFO("Source fpsList and smart_fps_value already match target, no modification made, skipping.")
        return 0

    LOG_INFO("Source fpsList items (" + int_to_str(len(source_items)) + "):")
    for item in source_items:
        LOG_INFO("  " + item)
    LOG_INFO("Source smart_fps_value: " + (source_smart_fps if source_smart_fps else "(not found)"))

    backup_path = source_xml + ".bak"
    if os.path.exists(backup_path):
        os.remove(backup_path)
    try:
        shutil.copy2(source_xml, backup_path)
    except Exception:
        LOG_ERROR("Could not create backup: " + source_xml)
        return 1

    replaced_smart = 0
    try:
        with open(source_xml, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        LOG_ERROR("Could not open source XML for rewriting: " + source_xml)
        return 1

    kept_lines = []
    in_array = False
    indent = ""
    indent_set = False
    for raw in lines:
        line = raw.rstrip("\r\n")
        if not in_array:
            if target_smart_fps:
                new_line = replace_int_attr_value(line, "smart_fps_value", target_smart_fps)
                if new_line != line:
                    line = new_line
                    replaced_smart += 1
            kept_lines.append(line)
            trimmed = trim_str(line)
            if '<integer-array name="fpsList">' in trimmed:
                in_array = True
            continue
        trimmed = trim_str(line)
        if not indent_set:
            pos = line.find("<item>")
            if pos != -1:
                indent = line[:pos]
                indent_set = True
        if "</integer-array>" in trimmed:
            for it in target_items:
                kept_lines.append(indent + it)
            in_array = False
            kept_lines.append(line)
            continue
        if "<item>" in trimmed and "</item>" in trimmed:
            continue
        kept_lines.append(line)

    try:
        with open(source_xml, "w", encoding="utf-8", errors="ignore") as f:
            for line in kept_lines:
                f.write(line + "\n")
    except Exception:
        LOG_ERROR("Write failed; restoring backup: " + source_xml)
        move_file_overwrite(backup_path, source_xml)
        return 1

    LOG_INFO("fpsList synchronized in " + source_xml + " (fpsList items: " + int_to_str(len(target_items)) + ", smart_fps_value replaced: " + int_to_str(replaced_smart) + "). Backup: " + backup_path)
    LOG_INFO("========================================")
    return 0


def sync_display_config(parent_dir):
    LOG_INFO("")
    LOG_INFO("========================================")
    LOG_INFO("  Synchronize display_id configs")
    LOG_INFO("========================================")

    source_dir = os.path.join(parent_dir, "workspace", "source_filesystem", "product", "etc", "displayconfig")
    target_dir = os.path.join(parent_dir, "workspace", "target_filesystem", "product", "etc", "displayconfig")

    if not os.path.isdir(source_dir):
        LOG_INFO("Source (port ROM) displayconfig directory not found, no modification made, skipping: " + source_dir)
        return 0
    if not os.path.isdir(target_dir):
        LOG_INFO("Base ROM (target) displayconfig directory not found, no modification made, skipping: " + target_dir)
        return 0

    source_files = get_files_in_dir(source_dir)
    target_files = get_files_in_dir(target_dir)

    S = []
    T = []
    for sf in source_files:
        fname = get_file_name(sf)
        if starts_with_ignore_case(fname, "display_id") and ends_with_xml_ignore_case(fname):
            S.append(fname)
    for tf in target_files:
        fname = get_file_name(tf)
        if starts_with_ignore_case(fname, "display_id") and ends_with_xml_ignore_case(fname):
            T.append(fname)
    S.sort()
    T.sort()

    LOG_INFO("Source (port ROM) display_id files: " + int_to_str(len(S)))
    for s in S:
        LOG_INFO("  - " + s)
    LOG_INFO("Base ROM (target) display_id files: " + int_to_str(len(T)))
    for t in T:
        LOG_INFO("  - " + t)

    if not S:
        LOG_INFO("No display_id*.xml in source (port ROM), no modification made, skipping.")
        return 0
    if not T:
        LOG_INFO("No display_id*.xml in base ROM (target), no modification made, skipping.")
        return 0

    duplicated = max(0, len(T) - len(S))
    LOG_INFO("Plan: " + int_to_str(len(T)) + " target id(s), " + int_to_str(len(S)) + " source file(s) used, " + int_to_str(duplicated) + " duplicated from source[0].")

    stage_files = []
    for i in range(len(T)):
        stage_name = ".__dc_stage_" + int_to_str(i) + ".xml"
        stage_path = os.path.join(source_dir, stage_name)
        src_path = os.path.join(source_dir, S[i] if i < len(S) else S[0])
        LOG_INFO("  Stage copy [" + int_to_str(i) + "]: " + (S[i] if i < len(S) else S[0]) + " -> " + stage_name)
        try:
            shutil.copy2(src_path, stage_path)
        except Exception:
            LOG_ERROR("  Stage copy failed: " + src_path)
            for prev in stage_files:
                try:
                    os.remove(prev)
                except Exception:
                    pass
            return 1
        stage_files.append(stage_path)

    consumed_count = min(len(S), len(T))
    to_delete = set()
    for t in T:
        to_delete.add(os.path.join(source_dir, t))
    for i in range(consumed_count):
        to_delete.add(os.path.join(source_dir, S[i]))
    for p in to_delete:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

    renamed = 0
    for i in range(len(T)):
        dest = os.path.join(source_dir, T[i])
        LOG_INFO("  Rename [" + int_to_str(i) + "]: " + get_file_name(stage_files[i]) + " -> " + T[i])
        if move_file_overwrite(stage_files[i], dest):
            renamed += 1
        else:
            LOG_ERROR("  Rename failed: " + stage_files[i] + " -> " + dest)

    LOG_INFO("display_id sync done. Renamed: " + int_to_str(renamed) + ", duplicated: " + int_to_str(duplicated) + ".")
    LOG_INFO("========================================")
    return 0


def sync_miui_camera(parent_dir):
    LOG_INFO("")
    LOG_INFO("========================================")
    LOG_INFO("  Migrate MiuiCamera + TURN_SCREEN_ON perm")
    LOG_INFO("========================================")

    source_product = os.path.join(parent_dir, "workspace", "source_filesystem", "product")
    target_product = os.path.join(parent_dir, "workspace", "target_filesystem", "product")

    target_camera_dir = ""
    source_camera_dir = ""
    for cand in [os.path.join(target_product, "app", "MiuiCamera"), os.path.join(target_product, "priv-app", "MiuiCamera")]:
        if os.path.isdir(cand):
            target_camera_dir = cand
            break
    for cand in [os.path.join(source_product, "app", "MiuiCamera"), os.path.join(source_product, "priv-app", "MiuiCamera")]:
        if os.path.isdir(cand):
            source_camera_dir = cand
            break

    if not target_camera_dir:
        LOG_INFO("Base ROM (target) has no MiuiCamera directory under product/app or product/priv-app, skipping camera replacement.")
    elif not source_camera_dir:
        LOG_INFO("Port ROM (source) has no MiuiCamera directory under product/app or product/priv-app, skipping camera replacement.")
    else:
        LOG_INFO("Base ROM (target) MiuiCamera: " + target_camera_dir)
        LOG_INFO("Port ROM (source) MiuiCamera: " + source_camera_dir)
        if remove_dir_recursive(source_camera_dir):
            if copy_dir_recursive(target_camera_dir, source_camera_dir):
                LOG_INFO("MiuiCamera replaced with base ROM version.")
            else:
                LOG_ERROR("Failed to copy MiuiCamera from base ROM: " + target_camera_dir)
                return 1
        else:
            LOG_ERROR("Failed to remove port ROM MiuiCamera directory: " + source_camera_dir)
            return 1

    perm_path = os.path.join(source_product, "etc", "permissions", "privapp-permissions-product.xml")
    if not os.path.exists(perm_path):
        LOG_INFO("Port ROM (source) privapp-permissions-product.xml not found, no modification made, skipping permission patch.")
        return 0
    LOG_INFO("Permission file: " + perm_path)

    has_turn_screen_on = False
    has_system_camera = False
    try:
        with open(perm_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "TURN_SCREEN_ON" in line:
                    has_turn_screen_on = True
                if "SYSTEM_CAMERA" in line:
                    has_system_camera = True
    except Exception:
        pass

    if has_turn_screen_on:
        LOG_INFO("TURN_SCREEN_ON already present in permission file, no modification made, skipping.")
        return 0
    if not has_system_camera:
        LOG_INFO("No SYSTEM_CAMERA anchor found in permission file, no modification made, skipping.")
        return 0

    backup_path = perm_path + ".bak"
    if os.path.exists(backup_path):
        os.remove(backup_path)
    try:
        shutil.copy2(perm_path, backup_path)
    except Exception:
        LOG_ERROR("Could not create backup: " + perm_path)
        return 1

    inserted = 0
    kept_lines = []
    try:
        with open(perm_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.rstrip("\r\n")
                kept_lines.append(line)
                if "SYSTEM_CAMERA" in line:
                    kept_lines.append('\t\t<permission name="android.permission.TURN_SCREEN_ON" />')
                    inserted += 1
    except Exception:
        LOG_ERROR("Could not open permission file for rewriting: " + perm_path)
        return 1

    try:
        with open(perm_path, "w", encoding="utf-8", errors="ignore") as f:
            for line in kept_lines:
                f.write(line + "\n")
    except Exception:
        LOG_ERROR("Write failed; restoring backup: " + perm_path)
        move_file_overwrite(backup_path, perm_path)
        return 1

    LOG_INFO("TURN_SCREEN_ON permission inserted (" + int_to_str(inserted) + " time(s)). Backup: " + backup_path)
    LOG_INFO("========================================")
    return 0


# -----------------------------------------------------------------------------
# Fix face unlock
# -----------------------------------------------------------------------------
def fix_face_unlock(parent_dir):
    LOG_INFO("")
    LOG_INFO("========================================")
    LOG_INFO("  Fix face unlock (biometric apps + tee_face)")
    LOG_INFO("========================================")

    target_app = os.path.join(parent_dir, "workspace", "target_filesystem", "product", "app")
    source_app = os.path.join(parent_dir, "workspace", "source_filesystem", "product", "app")

    if not os.path.isdir(target_app):
        LOG_INFO("Target app directory not found, no modification made, skipping: " + target_app)
        return 0

    biometric_dirs = []
    if os.path.isdir(target_app):
        for name in os.listdir(target_app):
            full = os.path.join(target_app, name)
            if os.path.isdir(full) and "biometric" in name.lower():
                biometric_dirs.append(name)

    if not biometric_dirs:
        LOG_INFO("No folder with 'Biometric' found in target app, no modification made, skipping.")
        return 0
    biometric_dirs.sort()
    LOG_INFO("Found " + int_to_str(len(biometric_dirs)) + " Biometric folder(s):")
    for d in biometric_dirs:
        LOG_INFO("  - " + d)

    if not os.path.isdir(source_app):
        LOG_ERROR("Source app directory not found: " + source_app)
        return 1

    for d in biometric_dirs:
        src = os.path.join(target_app, d)
        dest = os.path.join(source_app, d)
        if os.path.exists(dest):
            LOG_INFO("  Already exists, skipping: " + dest)
            continue
        LOG_INFO("  Copy: " + src + " -> " + dest)
        if not copy_dir_recursive(src, dest):
            LOG_ERROR("  Copy failed: " + src)
            return 1

    feature_dir = os.path.join(parent_dir, "workspace", "source_filesystem", "product", "etc", "device_features")
    if not os.path.isdir(feature_dir):
        LOG_INFO("device_features directory not found, no modification made: " + feature_dir)
        return 0

    xml_files = get_files_in_dir(feature_dir)
    xml_files.sort()
    edited_files = 0
    for path in xml_files:
        fname = get_file_name(path)
        if len(fname) < 4 or fname[-4:].lower() != ".xml":
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception:
            LOG_ERROR("Could not open: " + path)
            continue

        kept = []
        removed = 0
        for raw in lines:
            line = raw.rstrip("\r\n")
            if "tee_face" in line.lower():
                removed += 1
                LOG_INFO("  Removing from " + fname + ": " + line)
            else:
                kept.append(line)

        if removed == 0:
            LOG_INFO("No 'tee_face' in " + fname + ", left untouched.")
            continue

        backup_path = path + ".bak"
        if os.path.exists(backup_path):
            os.remove(backup_path)
        try:
            shutil.copy2(path, backup_path)
        except Exception:
            LOG_ERROR("Could not create backup: " + path)
            continue

        try:
            with open(path, "w", encoding="utf-8", errors="ignore") as f:
                for line in kept:
                    f.write(line + "\n")
        except Exception:
            LOG_ERROR("Write failed for " + path)
            continue

        LOG_INFO("Removed " + int_to_str(removed) + " tee_face line(s) from " + fname + ". Backup: " + backup_path)
        edited_files += 1

    if edited_files == 0:
        LOG_INFO("No device_features XML was modified.")
    else:
        LOG_INFO("Modified " + int_to_str(edited_files) + " device_features XML file(s).")
    LOG_INFO("========================================")
    return 0


# -----------------------------------------------------------------------------
# Patch SurfaceFlinger for MTK devices (Android 16 / OS 3.0.x)
# Only runs when device_platform=MTK in config.ini; skipped on Qualcomm.
# See: sf修复文档.md
# -----------------------------------------------------------------------------
def patch_surfaceflinger(parent_dir):
    LOG_INFO("")
    LOG_INFO("========================================")
    LOG_INFO("  Patch SurfaceFlinger (MTK only)")
    LOG_INFO("========================================")

    device_platform = get_device_platform(parent_dir)
    if device_platform.lower() != "mtk":
        LOG_INFO("device_platform=" + device_platform + ", skipping SurfaceFlinger patch.")
        return 0

    search_root = os.path.join(parent_dir, "workspace", "source_filesystem", "system_ext", "lib64")
    if not os.path.isdir(search_root):
        LOG_INFO("system_ext/lib64 directory not found: " + search_root)
        return 0

    candidates = []
    for root, dirs, files in os.walk(search_root):
        for name in files:
            if name.lower() == "libsurfaceflinger.so":
                candidates.append(os.path.join(root, name))

    if not candidates:
        LOG_INFO("No libsurfaceflinger.so found under " + search_root + ", skipping.")
        return 0

    if len(candidates) > 1:
        LOG_ERROR("Multiple libsurfaceflinger.so found, cannot determine target:")
        for c in candidates:
            LOG_ERROR("  " + c)
        return 1

    target = candidates[0]
    LOG_INFO("Target: " + target)

    exe_dir = get_exe_directory()
    patcher = os.path.join(exe_dir, "patch_sf.py")
    if not os.path.isfile(patcher):
        LOG_ERROR("patch_sf.py not found: " + patcher)
        return 1

    cmd = [sys.executable, patcher, target]
    LOG_INFO("Running: " + subprocess.list2cmdline(cmd))
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", env=env)
    except Exception as e:
        LOG_ERROR("Failed to run patch_sf.py: " + str(e))
        return 1

    # patch_sf.py outputs Chinese; save full UTF-8 output to log, print English summary only
    out = proc.stdout or ""
    log_path = os.path.join(parent_dir, "workspace", "sf_patch.log")
    try:
        with open(log_path, "w", encoding="utf-8") as lf:
            lf.write(out)
            if proc.stderr:
                lf.write("\n--- stderr ---\n")
                lf.write(proc.stderr)
    except Exception:
        pass

    if proc.returncode != 0:
        LOG_ERROR("patch_sf.py failed (exit " + int_to_str(proc.returncode) + "), see: " + log_path)
        LOG_INFO("========================================")
        return 1

    if "已是补丁状态" in out:
        LOG_INFO("SurfaceFlinger already patched, skipping.")
    else:
        LOG_INFO("SurfaceFlinger patched successfully.")
    LOG_INFO("Details: " + log_path)
    LOG_INFO("========================================")
    return 0


# -----------------------------------------------------------------------------
# Pipeline and main
# -----------------------------------------------------------------------------
StepFunc = type("StepFunc", (), {})


def get_device_platform(parent_dir):
    """Read device_platform from config.ini, default to qualcomm."""
    ini_path = os.path.join(parent_dir, "config.ini")
    try:
        with open(ini_path, "rb") as f:
            raw = f.read()
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        text = raw.decode("gbk", errors="ignore")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith(";") or line.startswith("["):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                if k.strip().lower() == "device_platform":
                    return v.strip()
    except Exception:
        pass
    return "qualcomm"


def run_speed_pipeline(parent_dir):
    steps = [
        ("Synchronize device_features", sync_features),
        ("Fix face unlock (biometric apps + tee_face)", fix_face_unlock),
        ("Synchronize VNDK apex + vintf", sync_apex),
        ("Clean MiuiBooster (DeviceLevelUtils/LiteUtils)", clean_miui_booster),
        ("Remove vk props from product build.prop", clean_vk_props),
        ("Remove preinstalled apps from data-app/data_app", clean_data_apps),
        ("Patch build prop from config.ini", patch_build_prop),
        ("Synchronize fpsList + smart_fps_value", sync_fps_list),
        ("Synchronize display_id configs", sync_display_config),
        ("Migrate MiuiCamera + TURN_SCREEN_ON perm", sync_miui_camera),
        ("Patch SurfaceFlinger (MTK only)", patch_surfaceflinger),
    ]
    step_count = len(steps)

    device_platform = get_device_platform(parent_dir)
    platform_label = {"mtk": "MTK", "qualcomm": "Qualcomm"}.get(device_platform.lower(), device_platform.title())
    LOG_INFO("HyperOS port mode for " + platform_label + " started.")

    results = [0] * step_count
    failed = 0
    for i in range(step_count):
        LOG_INFO("")
        LOG_INFO("Step " + int_to_str(i + 1) + "/" + int_to_str(step_count) + ": " + steps[i][0])
        results[i] = steps[i][1](parent_dir)
        if results[i] != 0:
            failed += 1
            LOG_ERROR("Step " + int_to_str(i + 1) + " failed, continuing with remaining steps.")
        time.sleep(1.0)

    LOG_INFO("")
    LOG_INFO("========== port mode for " + platform_label + " summary ==========")
    for i in range(step_count):
        status = "[OK]  " if results[i] == 0 else "[FAIL]"
        LOG_INFO(status + " " + steps[i][0])
    LOG_INFO("=========================================")

    if failed == 0:
        LOG_INFO("HyperOS port mode speed completed successfully.")
    else:
        LOG_ERROR(int_to_str(failed) + " step(s) failed.")
    return failed


def main():
    if len(sys.argv) != 2:
        LOG_ERROR("Supported commands: make_hyper.py speed")
        return 1

    exe_dir = get_exe_directory()
    parent_dir = get_parent_dir(exe_dir)
    detect_os_version(parent_dir)
    result = 1

    cmd = sys.argv[1].lower()
    if cmd == "speed":
        result = run_speed_pipeline(parent_dir)
    elif cmd == "extreme":
        result = clean_data_apps(parent_dir, extreme=True)
    elif cmd == "clean_apps":
        result = clean_data_apps(parent_dir)
    elif cmd == "clean_vk":
        result = clean_vk_props(parent_dir)
    elif cmd == "sync_fps":
        result = sync_fps_list(parent_dir)
    elif cmd == "sync_display":
        result = sync_display_config(parent_dir)
    elif cmd == "sync_camera":
        result = sync_miui_camera(parent_dir)
    elif cmd == "sync_apex":
        result = sync_apex(parent_dir)
    else:
        LOG_ERROR("Unknown command: " + sys.argv[1])
        LOG_ERROR("Supported commands: make_hyper.py speed")
        result = 1

    return result


if __name__ == "__main__":
    sys.exit(main())
