# XMAPort

简体中文 | [English](README_EN.md)

[![GitHub Release](https://img.shields.io/badge/version-261001.Beta-blue)](../../releases)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey)](#%E7%B3%BB%E7%BB%9F%E8%A6%81%E6%B1%82)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](#%E8%AE%B8%E5%8F%AF%E8%AF%81)

**XMAPort** 是一款小米 HyperOS 自动化移植（Porting）工具：输入源机型 ROM 与目标底包 ROM 的官方完整包直链，即可自动完成下载、解包、分区迁移、打补丁与重打包，输出可直接刷写的目标机型镜像。

---


## 简介

XMAPort 面向小米 HyperOS 设备的移植玩法：把一台机型的 HyperOS 系统（system / system_ext / product / mi_ext 等分区）迁移到另一台机型的官方底包上，并自动完成特性同步、属性补丁与镜像重打包。

整个流程由主脚本 `XMAPort.py`（Python 3.8+，Windows 平台）驱动，核心迁移逻辑在 `tools/make_hyper.py`，打包逻辑在 `tools/pack_partitions.py`。既支持 Windows 交互式菜单 / 命令行一键模式，也可以直接使用仓库自带的 GitHub Actions 在云端完成构建。

## 特性

- **全自动 7 步流水线**：下载 → 解压卡刷包 → 解包 payload → 解包分区镜像 → 迁移打补丁 → 重打包 → 汇总输出，一条命令跑通
- **双包并行下载**：源 ROM 与底包并行下载，双行实时进度条（每秒刷新、显示瞬时速度），失败自动整体重试
- **失败即中断**：下载、解包、迁移、打包任一环节失败立即中止，汇总按真实结果显示成败
- **完整分区迁移**：迁移 system / system_ext / product / mi_ext 到目标底包，自动处理 odm / vendor / vbmeta 等
- **智能特性同步**：特性同步、清理 MIUI booster、同步 APEX、刷新率 / 相机 / 人脸解锁同步、build.prop 补丁
- **联发科支持**：针对天玑 8100 / 8200 的 HWC 补丁
- **灵活打包**：erofs（lz4hc / lz4 / zstd 等压缩算法）或 ext4，可选生成 super.img、sparse 格式、禁用 vbmeta 校验、注入 adb debug
- **命令执行器**：主菜单 [A] 支持用已打包的分区单独合成 super.img
- **云端构建**：自带 GitHub Actions workflow，无需本地环境即可构建并自动发布 Release

## 工作流程

1. **下载 ROM**：源包与底包并行，aria2c 多线程下载官方 ROM 完整包直链
2. **解压卡刷包**：使用 7-Zip 解压 ROM zip
3. **解包 payload**：使用 payload-dumper-go 解包 `payload.bin` / `.dat`
4. **解包分区镜像**：使用 simg2img / lpunpack / extract.erofs 等工具解包 system、vendor、odm 等分区镜像
5. **迁移打补丁**：核心逻辑在 `tools/make_hyper.py`，把源机型的 system / system_ext / product / mi_ext 迁移到目标底包上，包括特性同步、清理 MIUI booster、sync APEX、刷新率 / 相机 / 人脸解锁同步、build.prop 补丁，以及联发科天玑 8100 / 8200 的 HWC 补丁
6. **重打包**：`tools/pack_partitions.py` 按 erofs（支持 lz4hc / lz4 / zstd 等压缩）或 ext4 打包，可选生成 super.img、生成 sparse 格式、禁用 vbmeta 校验、注入 adb debug
7. **汇总输出**：汇总输出可刷写的目标机型镜像

## 已测试的移植路线

| 源机型 | 目标机型 |
| --- | --- |
| REDMI Note12R | K70 / Note12Turbo / Note17 / 小米12 / 小米17 Ultra |
| Note12T Pro | K90 Max |
| K100 Pro | 小米17 Ultra |

以上为已实测路线；其他同架构机型理论上也可行，但未经验证，请自行测试并承担风险。

## 系统要求

- Windows 10 / 11 64 位
- Python 3.8+
- 约 40GB 可用磁盘空间
- 可访问 GitHub 的网络环境

## 使用方法

### 方式一：Windows 交互式菜单

直接运行主脚本，按菜单提示操作：

```bat
python XMAPort.py
```

主菜单除一键移植外，还提供 **[A] 命令执行器**（1 = 用 `workspace/packed` 里已有的分区镜像单独合成 super.img，空间不足时仅提示不自动重试）、**[C] 开源致谢** 与 **[D] 清理 workspace**。

### 方式二：命令行一键模式

```bat
python XMAPort.py --auto --device <目标代号> --source <源ROM直链> --target <底包ROM直链>
```

示例：

```bat
python XMAPort.py --auto --device sky --source https://.../source-rom-full.zip --target https://.../target-rom-full.zip
```

- `--device`：目标设备代号（仅允许字母、数字、下划线、连字符）
- `--source`：源机型 ROM 完整包直链（不能以 `ultimateota` 开头；**留空可使用本地包，没有本地包时复用上次工作区数据**）
- `--target`：目标底包 ROM 完整包直链（不能以 `ultimateota` 开头；留空同上）

> 注意：使用前请先按 [配置说明](#配置说明) 检查 `config.ini`，特别是 `device_platform` 与 `device_size`。

### 方式三：GitHub Actions 云端构建

仓库自带 `.github/workflows/build.yml`，无需本地环境：

1. 打开仓库的 **Actions** 页面，选择 **build** workflow
2. 点击 **Run workflow**（`workflow_dispatch` 手动触发），填入：
   - `device`：目标设备代号
   - `source`：源 ROM 完整包直链
   - `target`：底包 ROM 完整包直链
3. 构建完成后会自动分卷压缩 super.img 并发布到 Release

此外，每次 push 也会自动打包源码并发布 `XMAPort-*-Beta` release。

## 配置说明

所有配置集中在 `config.ini`（GBK/ANSI 编码）：

### 基本设置（必须核对）

| 配置项 | 说明 |
| --- | --- |
| `device_platform` | 设备平台：`Qualcomm` / `MTK`，**必须如实填写，填错有变砖风险** |
| `device_size` | 目标设备 super 分区总大小（字节），默认 `6979321856`（6.5GB），**必须按设备如实填写** |

### 下载设置

`[source]` / `[target]` 填写源 / 底包 ROM 直链，**留空 = 不下载，优先解压对应下载目录中的本地包，没有本地包时复用上次工作区**；`[settings]` 控制 aria2c 的下载线程数（`threads`）、最大连接数（`max-connection`，官方 aria2 上限 16）、超时（`timeout`）与整体重试次数（`retry`，`0` = 只下载一次不重试）。

本地包使用方法：将源完整卡刷包放入 `workspace/download_source/`，目标底包放入 `workspace/download_target/`，清空对应 `[source]` / `[target]` 的 `url` 后照常运行。两侧可独立选择本地包或直链下载。链接留空时，每个下载目录只能有一个包；多个包会报错，不会合并解压。直链下载使用按 URL 生成的固定文件名，并只处理本次对应的包，其他下载文件保留。

本次提供包的一侧会重新创建 ROM 解压目录及 payload 镜像目录。没有链接也没有本地包的一侧复用已有镜像；镜像不足时尝试从已有 ROM 目录提取。解包失败或被中断的一侧会留下 `.incomplete` 标记，必须提供包重新解包后才能复用。

每次进入迁移前，两侧文件系统都会从选定的镜像重新解包，旧文件、旧补丁和自动生成的权限/SELinux 元数据会清除。**文件系统目录中的手动修改不会保留**；只有各自 `config/fs_special.conf` 和 `config/fc_special.conf` 自定义规则保留。下载包、项目 `config.ini`、设备配置及历史日志保留。清理失败时停止流程。菜单 `[D]` 仍仅删除提示列出的镜像、payload 和设备配置，不是整个工作区重置。

### 打包设置（`[packing]`）

| 配置项 | 说明 |
| --- | --- |
| `format` | `erofs` 或 `ext4` |
| `compression` / `compression_level` | erofs 压缩算法与等级（如 `lz4hc` + `8`） |
| `pack_super` | 是否打包生成 super.img；`false` 时可用主菜单 [A] 单独合成 |
| `sparse` | 是否生成 sparse 格式镜像 |
| `metadata_size` / `metadata_slots` | super metadata 大小与插槽数（建议默认 `65536` / `3`） |
| `virtual_ab` | 是否启用 Virtual A/B |
| `super_name` / `super_group` | super 分区名与动态分区组名（高通一般 `qti_dynamic_partitions`，MTK 一般 `main`） |
| `enable_adb_debug` | 是否注入 adb debug（调试用，日常包建议关闭） |
| `patch_vbmeta` | 是否禁用 vbmeta 校验 |
| `is_skip_apex` | 跳过 system_ext 重打包并直接复制源镜像 |
| `erofs_old_kernel` | 旧内核兼容布局（仅老内核设备开启） |
| `utc_stamp` | 镜像时间戳，留空自动用 UTC |

### build.prop 补丁列表

文件末尾 `; patch build prop list` 标记行以下的 prop 列表会在迁移时写入 build.prop，例如电池快充（`persist.vendor.accelerate.charge`）、夜间充电（`persist.vendor.night.charge`）、默认刷新率（`ro.vendor.display.default_fps`）等。可以自行添加 prop，但**自行添加不保证开机**。

## 注意事项与常见问题

- **ROM 直链**：`--source` / `--target` 必须是官方完整卡刷包（fastboot 线刷包不可用）的直接下载 URL，不能以 `ultimateota` 开头
- **平台填错会变砖**：`device_platform` 是高通还是联发科务必核实清楚
- **super 大小要准确**：`device_size` 与目标设备不符可能导致无法刷入或无法开机
- **磁盘空间**：下载、解包、打包的中间文件较多，建议预留约 40GB
- **杀毒软件误报**：目录中捆绑的第三方 exe（aria2c、7z、mkfs.erofs 等）可能被误报，请添加信任或临时关闭
- **理论支持范围**：小米 11–15、REDMI K50–K90、Note / REDMI 12–15 系列（详见下表实际测试情况）
- **命令行模式找不到设备代号**：目标设备代号即底包 ROM 中 MIUI/HyperOS 版本号后的设备代号（如 `OS2.0.204.0.VMWCNXM` 中的 `sky`）



## 免责声明

- 本项目**仅供个人学习与测试使用**，请于下载后 24 小时内自行删除相关文件
- 刷机有**变砖**与**数据丢失**风险，使用本项目造成的一切后果由使用者**自行承担**
- 本项目与小米官方**无关**，ROM 版权归小米公司所有
- 一切商用 / 售卖行为与本项目及作者无关。本项目禁止用于售卖盈利或用于盈利性质的ROM构建。行为人由此产生的一切后果由其自行承担，与作者和贡献者无任何关系。

## 许可证

- 项目主代码（`XMAPort.py`、`tools/*.py`）采用 [MIT](LICENSE) 许可证
- 目录中捆绑的第三方工具分别适用其原始许可证：AGPL-3.0 / GPL-2.0 / LGPL-2.1，仓库中有对应的 LICENSE 文件

## 致谢

- 本项目使用 AI 辅助编码（Vibe Coding，DeepSeek / GLM / 小米 MiMo 等）
- 感谢以下开源项目的支持：
  - [aria2](https://github.com/aria2/aria2)、[7-Zip](https://www.7-zip.org/)
  - [payload-dumper-go](https://github.com/ssut/payload-dumper-go)
  - [erofs-utils](https://github.com/erofs/erofs-utils)、[lpunpack / lpmake](https://android.googlesource.com/platform/system/extras/)、[e2fsprogs](https://github.com/tytso/e2fsprogs)
  - [Google Brotli](https://github.com/google/brotli)
  - [Magisk](https://github.com/topjohnwu/Magisk)（vbmeta 禁验参照其已验证做法）
  - 以及所有 HyperOS 移植社区的开发者们
