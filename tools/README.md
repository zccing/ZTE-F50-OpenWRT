# 刷机工具来源

| 文件 | 上游来源 | 更新方式 |
| --- | --- | --- |
| `platform-tools/` | [Google 的 Windows Platform-Tools ZIP](https://dl.google.com/android/repository/platform-tools-latest-windows.zip) | 自动更新，包含 ADB、Fastboot、配套 DLL 和许可声明 |
| `zadig-*.exe` | [pbatard/libwdi Releases](https://github.com/pbatard/libwdi/releases)，2.9 对应 `v1.5.1` | 自动更新，保留上游文件名 |
| `f50-image-tools/cpio`、`debugfs`、`lz4` | [Termux AArch64 仓库](https://packages.termux.dev/apt/termux-main/)，分别来自 `cpio`、`e2fsprogs`、`lz4` | 自动更新 |
| `f50-image-tools/libandroid-posix-semaphore.so`、`libblkid.so`、`libuuid.so` | 同一 Termux 仓库的 `libandroid-posix-semaphore`、`libblkid`、`libuuid` 包 | 与镜像工具一起更新 |
| `spd_dump.exe`、`libusb-1.0.dll` | [TomKing062 的构建记录](https://github.com/TomKing062/action_spd_dump_it/actions/runs/40104709624)中的 `spd_dump_it_main_250_88f7ca6_x64_Release`。DLL 同时匹配 [libusb 1.0.30](https://github.com/libusb/libusb/releases/tag/v1.0.30) 的 `VS2025/MS64-hotplug/dll/libusb-1.0.dll` | 固定当前配套版本。上游的 Windows 构建产物会过期，新版本需在 F50 上验证备份和恢复命令后成对替换 |

## 校验工具

在 Git Bash、WSL 或 Linux 中，从仓库根目录运行：

```sh
(cd tools && sha256sum -c SHA256SUMS)
```

镜像工具目录也有自己的清单。把 `f50-image-tools` 传到 F50 后，进入该目录运行 `sha256sum -c SHA256SUMS`。

## 更新工具

默认分支上的「更新刷机文件」工作流每周一北京时间 08:23 并行检查工具和底包，也可在 Actions 页面手动运行。任一项有变动就创建或刷新同一个 PR。需要在仓库的 Settings > Actions > General 中启用 **Allow GitHub Actions to create and approve pull requests**。

本地可在装有 Python 3.9+ 和 `dpkg-deb` 的 Debian、Ubuntu 或 WSL 中，从仓库根目录运行：

```sh
python3 tools/update-tools.py
```

脚本先下载并核对文件，再把更新和两份校验清单一起写入 `tools`。重复运行时，内容相同的文件会跳过。合并 PR 前，按[制作镜像指南](../docs/build.md)检查更新后的镜像工具能否在 F50 的原厂 Android 上运行。
