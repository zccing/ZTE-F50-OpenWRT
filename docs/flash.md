# 从电脑刷入 OpenWrt

先完成[制作镜像](build.md)，确认电脑的 `tmp` 文件夹里有 `f50-boot-b.img`、`system.img.gz` 和 `system.sha256`。本页会覆盖设备上原有的 2 GiB OpenWrt 区域。

## 1. 写入启动镜像，进入救援模式

在刷机文件夹的 PowerShell 运行下面三行。确认当前槽位是 `a`，`boot_b` 的大小是 64 MiB（十六进制 `0x4000000`）。

```powershell
.\tools\platform-tools\adb.exe reboot bootloader
.\tools\platform-tools\fastboot.exe getvar current-slot
.\tools\platform-tools\fastboot.exe getvar partition-size:boot_b
```

把启动镜像写到 B 槽。等第一行显示成功，再执行第二行。

```powershell
.\tools\platform-tools\fastboot.exe flash boot_b .\tmp\f50-boot-b.img
.\tools\platform-tools\fastboot.exe set_active b
```

等 F50 启动后，在 PowerShell 输入 `telnet 192.168.77.1`，连到 F50 的救援终端。

## 2. 把系统镜像传给 F50

在救援终端运行下面的命令。先让设备停在救援模式，再卸载磁盘。最后两行都应没有输出。

```sh
touch /run/stay

umount /disk && losetup -d /dev/loop0
grep ' /disk ' /proc/mounts
losetup -a
```

在救援终端运行这一行，让 F50 等待接收文件。保留这个窗口。

```sh
nc -l -p 8081 192.168.77.1 > /run/f50-system.img.gz
```

在电脑的刷机文件夹里另开一个 PowerShell，执行下面这段。传完后回到救援终端。

```powershell
$F50Image = [IO.File]::OpenRead((Resolve-Path -LiteralPath '.\tmp\system.img.gz').Path)
$F50Client = [Net.Sockets.TcpClient]::new()
try {
    $F50Client.Connect('192.168.77.1', 8081)
    $F50Image.CopyTo($F50Client.GetStream())
} finally {
    $F50Client.Dispose()
    $F50Image.Dispose()
}
```

在救援终端核对文件。下面两个 SHA-256 值应分别对应电脑上 `tmp/system.sha256` 里的 `system.img.gz` 和 `system.img`。两项都一致再写入。

```sh
stat -c '%s bytes' /run/f50-system.img.gz
sha256sum /run/f50-system.img.gz
(set -o pipefail; gzip -dc /run/f50-system.img.gz | sha256sum)
```

## 3. 写入系统

等救援模式启动超过 320 秒，再在救援终端运行下面这段。它会检查写入位置，写完后再读一遍核对。如果提示找不到原有的 2 GiB OpenWrt 区域，请停在这里。

<details>
<summary>展开写入命令</summary>

```sh
(
    set -e
    set -o pipefail
    archive=/run/f50-system.img.gz
    disk=/dev/mmcblk0
    size=2147483648

    test -f /run/stay
    grep -q 'stage=linux-slot slot=b ' /run/stages
    grep -q 'stage=rootfs-unavailable' /run/stages
    grep -q 'stage=pmic-wdt-rstoff-ready ' /run/stages
    test "$(cut -d. -f1 /proc/uptime)" -gt 320 ||
        { echo '救援运行时间还不到 320 秒'; exit 1; }

    awk '$1 ~ /^\/dev\/(loop|mmcblk)/ || $3 ~ /^(ext[234]|f2fs|vfat)$/ { exit 1 }' /proc/mounts ||
        { echo '仍有存储挂载，停止'; exit 1; }
    active_loops=$(losetup -a)
    test -z "$active_loops" || { echo '仍有 loop 设备，停止'; exit 1; }

    test "$(cat /sys/block/mmcblk0/device/type)" = MMC
    geometry=$(f50-target gpt "$disk")
    set -- $geometry
    test "$#" -eq 2
    offset=$(( ($1 / 2097152 + 1) * 2097152 ))
    test "$((offset + size))" -le "$2"

    sb=/run/f50-old-superblock
    dd if="$disk" of="$sb" bs=512 skip=$((offset / 512 + 2)) count=2 2>/dev/null
    field() { od -An -j "$1" -N "$2" "$3" "$sb" | tr -d ' \n'; }
    label=$(dd if="$sb" bs=1 skip=120 count=16 2>/dev/null | tr -d '\000')
    test "$label" = mu300root &&
        test "$(field 56 2 -tx1)" = 53ef &&
        test "$(field 24 4 -tu4)" = 2 &&
        test "$(field 4 4 -tu4)" = 524288 &&
        test "$(field 336 4 -tu4)" = 0 ||
        { echo '目标不是先前确认的 2 GiB OpenWrt 区域'; exit 1; }

    check_boot_a() {
        actual=$(sha256sum /dev/block/by-name/boot_a)
        test "${actual%% *}" = "$(cat /etc/f50-stock.sha256)"
    }
    check_boot_a

    test "$(tail -c 4 "$archive" | od -An -tu4 | tr -d ' \n')" -eq "$size"
    expected=$(gzip -dc "$archive" | sha256sum | cut -d ' ' -f 1)

    printf '写入目标 %s offset=%s bytes=%s\n' "$disk" "$offset" "$size"
    loop=$(f50-target loop "$disk" "$offset" "$size")
    trap 'losetup -d "$loop"' EXIT

    gzip -dc "$archive" | dd of="$loop" bs=1M iflag=fullblock conv=fsync
    sync
    echo 3 > /proc/sys/vm/drop_caches

    actual=$(sha256sum "$loop")
    test "${actual%% *}" = "$expected" ||
        { echo '读回 SHA256 不一致'; exit 1; }
    e2fsck -fn "$loop"
    test "$(f50-target gpt "$disk")" = "$geometry"
    check_boot_a

    losetup -d "$loop"
    trap - EXIT
    echo SYSTEM_WRITE_OK
)
```

</details>

看到 `SYSTEM_WRITE_OK` 后，在救援终端输入 `reboot -f` 重启。

## 4. 启动并登录 OpenWrt

等 F50 回到 Android，在电脑的 PowerShell 运行下面的命令。第一行应显示 `_a`。

```powershell
.\tools\platform-tools\adb.exe shell getprop ro.boot.slot_suffix
.\tools\platform-tools\adb.exe reboot bootloader
.\tools\platform-tools\fastboot.exe getvar current-slot
.\tools\platform-tools\fastboot.exe set_active b
```

等 B 槽启动后，在 PowerShell 登录，输入制作镜像时设置的密码。

```powershell
ssh root@192.168.77.1
```

登录成功后，在 F50 里运行下面这行，把 OpenWrt 设为下次开机默认系统，并查看设置结果。

```sh
mu300-next-boot linux && mu300-next-boot status
```
