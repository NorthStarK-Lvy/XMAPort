# Third-Party Notices

本文件列出 XMAPort 项目中引用的全部第三方组件、其开源协议、版权声明与来源。
这些组件均未做任何修改，以原样随项目分发。

项目原创部分（XMAport.bat、自研 Python 脚本、config.ini、README 等）采用 MIT 协议，见根目录 `LICENSE`。

---

## 1. aria2

- **文件**: `tools\aria2c.exe`
- **用途**: ROM 多线程下载（断点续传、多连接）
- **协议**: GNU General Public License v2 (GPL v2)
- **来源**: https://github.com/aria2/aria2
- **协议全文**: `LICENSE-GPL-2.0.txt`
- **版权**: Copyright (C) 2006-2024 Tatsuhiro Tsujikawa

## 2. 7-Zip

- **文件**: `tools\7z.exe`, `tools\7z.dll`, `tools\7-zip.dll`, `tools\7-zip32.dll`
- **用途**: ROM 压缩包解压
- **协议**: GNU Lesser General Public License v2.1 (LGPL v2.1)，含 unRAR 等例外条款
- **来源**: https://www.7-zip.org/
- **协议全文**: `LICENSE-LGPL-2.1.txt`
- **版权**: Copyright (C) 1999-2024 Igor Pavlov

## 3. payload-dumper-go

- **文件**: `tools\payload-dumper-go.exe`
- **用途**: 解包 Android OTA payload.bin
- **协议**: MIT
- **来源**: https://github.com/ssut/payload-dumper-go
- **版权**: Copyright (c) 2022-2024 ssut

## 4. AOSP partition tools

- **文件**: `tools\lpunpack.exe`, `tools\lpmake.exe`, `tools\lpdumps.exe`
- **用途**: Android dynamic partition (super.img) 解包、打包与信息查看
- **协议**: Apache License 2.0
- **来源**: https://github.com/nicktal01/aosp15_partition_tools （基于 AOSP）
- **协议全文**: https://www.apache.org/licenses/LICENSE-2.0

## 5. MIO-KITCHEN-SOURCE

- **文件**:
  - `tools\img2simg.exe`
  - `tools\zero\ext4.py` — ext4 文件系统解析库
  - `tools\zero\imgextractor.py` — 分区镜像提取器
  - `tools\zero\posix.py` — Windows 下 symlink 兼容支持
  - `tools\zero\img_init.py` — sparse 镜像初始化（未带许可头，保守按同源协议处理）
- **用途**: 镜像格式转换与分区内容提取
- **协议**: 文件头声明为 GNU Affero General Public License v3.0 (AGPL-3.0)
- **来源**: https://github.com/ColdWindScholar/MIO-KITCHEN-SOURCE
- **协议全文**: `LICENSE-AGPL-3.0.txt`
- **版权**: Copyright (C) ColdWindScholar 及 MIO-KITCHEN-SOURCE 各贡献者

## 6. AOSP / e2fsprogs 打包与转换工具

- **文件**: `tools\simg2img.exe`, `tools\img2simg.exe`, `tools\make_ext4fs.exe`,
  `tools\mke2fs.exe`, `tools\e2fsdroid.exe`
- **用途**: sparse 镜像转换、ext4 文件系统打包（Android build 工具链）
- **协议**: Apache License 2.0（AOSP 工具） / GPL v2（e2fsprogs）
- **来源**: https://android.googlesource.com/ 、https://e2fsprogs.sourceforge.net/
- **协议全文**: `LICENSE-GPL-2.0.txt`（对应 GPL 部分）

## 7. erofs-utils

- **文件**: `tools\extract.erofs.exe`, `tools\mkfs.erofs.exe`
- **用途**: EROFS 文件系统解包与打包
- **协议**: GNU General Public License v2 or later (GPL v2+)
- **来源**: https://git.kernel.org/pub/scm/linux/kernel/git/xiang/erofs-utils.git/
- **协议全文**: `LICENSE-GPL-2.0.txt`

## 8. Cygwin

- **文件**: `tools\cygwin1.dll`
- **用途**: POSIX 环境兼容层（部分工具运行时依赖）
- **协议**: GNU General Public License v3 + Cygwin 例外条款
- **来源**: https://www.cygwin.com/
- **例外说明**: https://cygwin.com/cygwin-licensing.html

---

## 协议文件索引

| 文件 | 协议 | 覆盖组件 |
|---|---|---|
| `LICENSE` | MIT | 本工具原创部分 |
| `LICENSE-GPL-2.0.txt` | GPL v2 | aria2c、erofs-utils、e2fsprogs |
| `LICENSE-LGPL-2.1.txt` | LGPL v2.1 | 7-Zip |
| `LICENSE-AGPL-3.0.txt` | AGPL v3 | MIO-KITCHEN-SOURCE 组件 |

## 说明

- 所有第三方组件**原样分发，未修改**
- Apache 2.0 / MIT 组件的完整文本可从其官方地址获取（见上表）
- 依据 GPL/AGPL 的传染性约定，本仓库 Python 部分与 `zero\` 模块存在 import 关系，
  分发与再使用本项目时请自行评估协议兼容性
