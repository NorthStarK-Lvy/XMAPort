# XMAPort

Xiaomi HyperOS 跨设备移植工具（Python + Win32 exe）

## 简介

XMAPort 是一个面向Xiaomi/REDMI手机的，用于移植 HyperOS (Android 15/16) 的自动化 ROM 移植工具。只需提供源设备（Source）与目标设备（Target）的官方 ROM 完整包直链，即可一键完成「下载 → 解压 → payload 解包 → 镜像解包 → 分区迁移 → 重打包」全流程，输出可刷入目标机的镜像文件。

## 致谢

>本项目使用了 Vibe Coding，参与的 AI 包括 Deepseek, GLM, Xiaomi Mimo

## 功能特性

正在测试Github Actions

## 快速开始

1. 确保电脑环境内有python
2. 编辑 `config.ini`：
   - `[source] url =` 源设备 ROM 完整包直链（被移植的系统来源）
   - `[target] url =` 目标设备 ROM 完整包直链（要刷入的设备）
3. 双击运行 `XMAport.py`
4. 主菜单选择 `[1] Done Port HyperOS`
5. 首次运行需输入目标设备代号（如 `sky`、`sheng`、`fuxi`）
6. 确认参数无误后开始，最终镜像输出到 `workspace\packed\`

>如果您想下载工具到本地跑包的同时偷个懒的话，您现在可以使用python XMAPort.py --auto --device sheng来一键流水线完成。


>同时，如果您懒得编辑config.ini，也可以使用python XMAPort.py --auto --device sheng \
  --source https://.../source_rom.zip \
  --target https://.../target_rom.zip

## 适用机型

### 已经经过测试的包括
- REDMI Note12R 移植 REDMI K70(Android16)

- REDMI Note12R 移植 REDMI Note12Turbo(Android15)

- REDMI Note12R 移植 REDMI Note17(Android16)

- REDMI Note12R 移植 Xiaomi 12(Android13)

- REDMI Note12R 移植 Xiaomi 17 Ultra(Android17)

### 理论支持的包括
- Xiaomi 11/12/13/14/15全系列

- REDMI K50/60/70/80/90全系列

- Note 12/13/14/15全系列

- REDMI 12/13/14/15全系列


>不建议6.6及以上内核版本的机型(如Xiaomi 17系列)使用本工具


## 环境要求

| 依赖 | 说明 |
|---|---|
| Windows 10/11 (64 位) | 脚本为 Windows Batch，依赖 7z、cygwin 等 Windows 二进制 |
| Python 3.8+ | 需已加入系统 PATH（解包/打包脚本依赖） |
| 磁盘空间 | 建议 40GB 以上（两份 ROM 包 + 解包产物 + 打包产物） |
| 网络 | 可访问 ROM 下载直链（小米/Redmi 阿里云 OSS） |
## 配置说明（config.ini）

### [source] / [target]

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `url` | 无 | ROM 完整包直链（请不要带 ultimateota 前缀） |

### [settings]

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `threads` | 16 | 下载线程数 |
| `max-connection` | 16 | 每任务最大连接数 |
| `timeout` | 300 | 下载超时（秒） |
| `retry` | 5 | 下载失败重试次数 |

### [packing]

### 请务必调整 `device_size` 为您的super分区的正确大小，否则容易出现super空间不足而报错！

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `pack_super` | false | 是否打包 super.img（false 仅打包分区） |
| `format` | erofs | 打包文件系统：erofs / ext4 |
| `readonly` | true | 是否只读方式打包 |
| `compression` | lz4hc | 压缩算法（erofs 用）：lz4hc / lz4 / zstd / lzma / deflate |
| `compression_level` | 9 | 压缩等级 0-9（仅 erofs 有效） |
| `device_size` | 6979321856 | super 总大小（字节），可用 lpdumps.exe 查看原机 |
| `metadata_size` | 65536 | 元数据大小（字节） |
| `sparse` | true | 是否以 sparse 格式输出 super |
| `super_name` | super | super 设备名 |
| `super_group` | qti_dynamic_partitions | 动态分区组名 |
| `metadata_slots` | 3 | 元数据槽位：2=A-only / 3=AB |
| `virtual_ab` | true | 是否开启 AB 虚拟分区 |
| `ext4_packer` | make_ext4fs | ext4 打包器：make_ext4fs / mke2fs |
| `is_skip_apex` | true | 是否跳过 system_ext apex 重打包 |
| `enable_adb_debug` | false | 是否注入 adb debug 属性（刷入后默认开 USB 调试） |
| `patch_vbmeta` | true | 是否禁验 vbmeta（disable-verity + disable-verification），刷第三方 ROM 建议 true |
| `utc_stamp` | 空 | 打包用固定 UTC 时间戳（整数，留空 = 当前时间，便于可复现打包） |
| `erofs_old_kernel` | false | erofs 打包附加 `-E legacy-compress`（兼容旧内核） |

### build.prop 补丁列表

`[packing]` 段末尾可直接追加 `persist.vendor.*` / `ro.vendor.*` 属性行，打包时自动写入系统 build.prop。内置示例：夜间充电、快充加速、电池健康


## 目录结构

```
XMAPort/
├── XMAport.py           主脚本（菜单 + 流水线）
├── config.ini           配置文件
├── tools/               工具目录
│   ├── *.py             Python 脚本
│   ├── zero/            Python 模块（ext4 解析、镜像提取等）
│   └── *.exe / *.jar    二进制工具
└── workspace/           工作区（自动生成）
    ├── download_source/ 源 ROM 下载缓存
    ├── download_target/ 目标 ROM 下载缓存
    ├── source_rom/      源 ROM 解压产物
    ├── target_rom/      目标 ROM 解压产物
    ├── source_payload/  源 payload 解包产物
    ├── target_payload/  目标 payload 解包产物
    ├── source_filesystem/  源分区文件系统（解包后）
    ├── target_filesystem/  目标分区文件系统（解包后）
    ├── packed/          打包输出（*.img）
    └── *.log            运行日志
```

## tools 说明

**Python 脚本**（位于 `tools\`）：

- `pack_partitions.py` — 分区打包核心（erofs / ext4），自动补全 system_ext / product 分区的 file_contexts、lost+found 与特殊权限/标签名单
- `make_hyper.py` — 定制化处理核心程序
- `img_helper.py` — 镜像/格式辅助工具
- `vbmeta_patch.py` — vbmeta 禁验补丁（AVB0 校验 + flags 0x03）

**第三方组件**（版权归原作者，详见「第三方组件与许可」）：

7z、aria2c、payload-dumper-go、simg2img / img2simg、lpunpack / lpmake / lpdumps、extract.erofs、mkfs.erofs、make_ext4fs、mke2fs、e2fsdroid、apktool，以及 `tools\zero\` 下的 Python 模块（ext4.py、imgextractor.py、posix.py、img_init.py，源自 MIO-KITCHEN-SOURCE）

## 第三方组件与许可

| 组件 | 用途 | 协议 | 来源 |
|---|---|---|---|
| aria2c | ROM 多线程下载 | GPL v2 | https://github.com/aria2/aria2 |
| 7-Zip (7z.exe) | 压缩包解压 | GNU LGPL | https://www.7-zip.org/ |
| payload-dumper-go | payload.bin 解包 | MIT | https://github.com/ssut/payload-dumper-go |
| AOSP partition tools（lpunpack / lpmake / lpdumps） | super 分区处理 | Apache 2.0 | https://github.com/nicktal01/aosp15_partition_tools |
| MIO-KITCHEN-SOURCE（img2simg、`zero\ext4.py`、`zero\imgextractor.py` 等） | 镜像转换 / 提取 | AGPL-3.0（文件头声明） | https://github.com/ColdWindScholar/MIO-KITCHEN-SOURCE |
| simg2img / img2simg | sparse 镜像转换 | AOSP / MIO-KITCHEN | AOSP、MIO-KITCHEN-SOURCE |
| extract.erofs / mkfs.erofs | erofs 解包 / 打包 | GPL v2+ | erofs-utils 官方 |
| make_ext4fs / mke2fs / e2fsdroid | ext4 打包 | GPL v2 / Apache 2.0 | AOSP、e2fsprogs |

以上第三方组件均未修改，随本仓库原样分发；各协议全文见项目根目录：

- `LICENSE` — MIT（本工具原创部分：XMAport.bat、Python 脚本、配置与文档）
- `LICENSE-AGPL-3.0.txt` — 对应 MIO-KITCHEN-SOURCE 的 `zero\` Python 模块
- `LICENSE-GPL-2.0.txt` — 对应 aria2c 等 GPL v2 组件
- `LICENSE-LGPL-2.1.txt` — 对应 7-Zip


## 免责声明

- 本工具仅用于个人学习与测试研究，没有也不会对Xiaomi HyperOS内的系统应用进行任何修改操作
- 刷机有风险，可能造成变砖或数据丢失，后果自负
- HyperOS 及其相关商标、ROM 版权归小米（Xiaomi / Redmi）所有，本工具与官方无任何关联
- 请勿将本工具用于任何商业用途

## License

本项目为多协议分发：

- 原创部分（XMAport.py、Python 脚本、配置与文档）：[MIT](LICENSE)
- 第三方组件：协议归各自作者所有，全文见 [第三方组件与许可](#第三方组件与许可)


