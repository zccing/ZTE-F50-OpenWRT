# 中兴 F50 刷 OpenWrt

用 Windows 电脑给 F50 刷 OpenWrt。原厂 Android 从 A 槽启动，OpenWrt 从 B 槽启动。

## 1. 克隆仓库

在电脑上选个放刷机文件的位置，打开 PowerShell，运行下面两行。如果提示找不到 `git`，运行 `winget install --id Git.Git -e`，装好后重新打开 PowerShell 再试。

```powershell
git clone https://github.com/zccing/ZTE-F50-OpenWRT.git
cd .\ZTE-F50-OpenWRT
```

现在所在的目录就是「刷机文件夹」。后面的命令都在这里运行，直接用 `tools\platform-tools` 里的 ADB 和 Fastboot。

### 先用 ADB 看看这台能不能刷

1. 用 USB 线连接 F50，在 [F50 后台](http://192.168.0.1/index.html#usb_port) 打开「USB 调试」，重启 F50。运行 `.\tools\platform-tools\adb.exe devices -l`，看到设备号旁边显示 `device` 就连好了。电脑认不出设备时，在设备管理器安装 [Google USB 驱动](https://dl.google.com/android/repository/usb_driver_r13-windows.zip)。
2. 在 PowerShell 输入 `.\tools\platform-tools\adb.exe shell`，进入 F50 后粘贴下面的命令。

```sh
cat /sys/block/mmcblk0/device/type
end=$(for p in /sys/block/mmcblk0/mmcblk0p*; do paste "$p/start" "$p/size"; done | awk '$1+$2>m {m=$1+$2} END {printf "%.0f",m}')
sector=$(( (end / 4096 + 1) * 4096 ))
echo "可用扇区 $(( $(cat /sys/block/mmcblk0/size) - sector ))"
info=$(mktemp /data/local/tmp/f50-check.XXXXXX)
dd if=/dev/block/mmcblk0 of="$info" bs=512 skip="$sector" count=8
toybox blkid -s LABEL -s TYPE "$info"
od -An -tu4 -j 1028 -N 4 "$info"
od -An -tu4 -j 1048 -N 4 "$info"
od -An -tu4 -j 1360 -N 4 "$info"
rm -f "$info"
```

**怎么看结果？** 第一行是 `MMC`，可用扇区至少有 `4194304`，且看到 `LABEL="mu300root"`、`TYPE="ext4"`，最后三个数依次是 `524288`、`2`、`0`，就找到了教程要用的 2 GiB 区域。刷入时会覆盖里面的内容。

结果对不上，就只做备份。如果报 `Permission denied` 或其他读取错误，说明这次没查出来，也先停在备份这步。输入 `exit` 回到 PowerShell。

## 2. 安装备份驱动

打开 `tools` 里的 Zadig，拔插 F50，选中随它出现的设备，再点安装驱动。

## 3. 备份原厂系统

每次用 `spd_dump`，都要**拔线断电 10 秒，先运行命令，再插 USB**。下面两行分开执行。第一行测连接，看到设备信息后，再按同样顺序运行第二行做备份。

```powershell
.\tools\spd_dump.exe --wait 60 --kickto 2 chip_uid reset
.\tools\spd_dump.exe --wait 300 --kickto 2 exec path backup r all reset
```

备份完成后，记下新生成的 `日期_时间\backup` 文件夹的完整路径。后面会用到里面的 `boot_a` 和 `misc`。备份不含 `userdata`，重要的个人数据和设备设置请另外保存。

## 4. 解锁 F50

1. 确认备份已保存，按上面的断电顺序运行 `.\tools\spd_dump.exe --wait 300 --kickto 2 exec timeout 30000 write_part uboot_a .\unlock\F50_uboot_eng.bin reset`。
2. 等 F50 启动，在 PowerShell 运行 `.\tools\platform-tools\adb.exe reboot bootloader`，再运行 `.\tools\platform-tools\fastboot.exe devices`。看到设备号和 `fastboot` 后继续。
3. 用 Chrome 或 Edge 打开 [解锁页面](https://unisoc-android.github.io/subut/)，点 **Connect**，选 **Android Bootloader Interface**，再点 **Unlock**。
4. 看到 `Device status: Unlocked!` 后，断电 10 秒，重新启动并打开 USB 调试。运行 `.\tools\platform-tools\adb.exe shell getprop ro.boot.vbmeta.device_state`，看到 `unlocked` 就可以继续。

## 5. 制作镜像，再刷入

- [制作这台 F50 的镜像](docs/build.md) — 在原厂 Android 里制作启动镜像和系统镜像，设置登录密码，再把两个文件存到电脑。
- [刷入并登录 OpenWrt](docs/flash.md) — 从 B 槽进入救援模式，传入系统。看到 `SYSTEM_WRITE_OK` 后再重启，最后用 `ssh root@192.168.77.1` 登录。

<details>
<summary>需要恢复原厂系统时</summary>

恢复会覆盖备份对应的分区。把下面的示例路径换成这台 F50 自己的备份目录，再按第 3 步的断电顺序执行。

```powershell
.\tools\spd_dump.exe --wait 300 --kickto 2 exec write_parts "D:\刷机\261118_105152\backup" reset
```

</details>
