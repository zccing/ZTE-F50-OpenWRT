# F50 公共底包

| 公共文件 | 用途 | 来源 |
| --- | --- | --- |
| `Image` | Linux 5.4 内核 | [MU300 Linux Releases](https://github.com/dikeckaan/mu300-linux/releases) 的 `mu300-kernel.tar.gz` 内的 `Image` |
| `common.lz4` | 基础 ramdisk，含 BusyBox 和内核模块 | 同一内核包内的 `ramdisk-generic.lz4` |
| `rescue.lz4` | F50 救援启动 | 基于 [MU300 Linux 的 boot/init](https://github.com/dikeckaan/mu300-linux/blob/main/boot/init) 制作。更新系统底包时同步写入 eMMC 镜像的校验值 |
| `normal.lz4` | F50 正式启动 | 基于同一 `boot/init` 制作，含本仓库的 F50 启动逻辑 |
| `emmc.img.gz` | 2 GiB eMMC 系统底包 | 用同一发行版的 `mu300-openwrt-luci-rootfs.tar.gz` 构建 |

五个文件的校验值保存在 [SHA256SUMS](SHA256SUMS)。把整个 `payload` 目录传到 F50 后，进入该目录运行 `sha256sum -c SHA256SUMS`。

## 更新底包

在装有 Python 3.9+、`e2fsprogs`、`fakeroot` 和 `lz4` 的 Debian、Ubuntu 或 WSL 中，从仓库根目录运行：

```sh
python3 payload/update-payload.py
```

脚本默认使用 MU300 Linux 最新正式版，也可用 `--release` 指定发行标签。运行时会显示所用版本，并同时生成校验清单。当前底包已对应同一组上游文件且通过校验时，会跳过重建。只想为已有文件生成清单时，添加 `--checksums-only`。

「更新刷机文件」工作流每周一北京时间 08:23 并行检查底包和工具，也可在 Actions 页面手动运行。任一项有变动就创建或刷新同一个 PR。仓库需要开启 **Allow GitHub Actions to create and approve pull requests**。合并前请在 F50 上验证镜像制作和启动。
