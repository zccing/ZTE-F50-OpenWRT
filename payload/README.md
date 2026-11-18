| 公共文件 | 用途 | SHA-256 | 获取链接 |
|---|---|---|---|
| Image | Linux 内核 | `94240dff47e5cbffd969d43049512a4f13f75b76298b1769f186fc98e6da5de8` |  [mu300-kernel.tar.gz 包内的 Image](https://github.com/dikeckaan/mu300-linux/releases)。|
| common.lz4 | 基础 ramdisk，含 BusyBox 和内核模块 | `c72b25fb9f8bddd771c6d1df835fc543e5c4a43b84de9324b98ae26e6c7df36e` | [mu300-kernel.tar.gz 包内的 ramdisk-generic.lz4](https://github.com/dikeckaan/mu300-linux/releases)。|
| rescue.lz4 | 救援启动逻辑 | `79f2cfafcfd83d33c80d290de6a5fb1364a6085fc65cb2f43c6dd003d4dbbe25` | [基于 boot/init 源码生成的](https://github.com/dikeckaan/mu300-linux/blob/main/boot/init)。 |
| normal.lz4 | 正式启动逻辑 | `a797ffcc74f3b9006521fa5762b844c9eb63aa5fa1d4fc472ef9ae03e5948134` | [基于 boot/init 源码生成的](https://github.com/dikeckaan/mu300-linux/blob/main/boot/init)。 |
| emmc.img.gz | 内置 eMMC 的 OpenWrt 系统底包 | `28f43ed3c83839e303c22a626e20dbb7b498c1472e4282b3136d90dddc527f64` | [mu300-openwrt-luci-rootfs.tar.gz](https://github.com/dikeckaan/mu300-linux/releases)。|


TODO:
需要新增一个自动更新这些内容的脚本，然后自动生成一个 sha256 校验文件， F50 上直接使用 sha256sum 来校验