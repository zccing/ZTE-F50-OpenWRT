# 安装工具
1. cmd 执行 `winget install --exact Google.PlatformTools` 安装 adb
2. 从[google usb 驱动](https://developer.android.com/studio/run/win-usb?hl=zh-cn)下载 google usb 驱动，然后在`设备管理器`中加载下载的驱动
3. 从[spd_dump](https://github.com/TomKing062/spreadtrum_flash)下载spd_dump 工具，解压放到当前目录的 ./tools 下
4. 从[zadig](https://zadig.akeo.ie/)下载 usb 驱动安装程序，解压放到当前目录的 ./tools 下。打开 zadig，插拔设备，等待界面出现设备后点击安装即可。

# 开启 usb 调试

中兴 F50：后台 http://192.168.0.1/index.html#usb_port 打开 USB 调试后重启。设备启动后，执行 adb devices -l 查看设备

# 备份&恢复

1. 测试 spd_dump

   断电 10 秒 → 先启动命令 → 再插 USB：
      
   启动命令： `.\tools\spd_dump.exe --wait 60 --kickto 2 chip_uid reset`
   
   正常情况会出现很多回显内容。
2. 备份，无法备份 userdata (用户数据和设备配置等)

   断电 10 秒 → 先启动命令 → 再插 USB：
   
   启动命令： `.\tools\spd_dump.exe --wait 300 --kickto 2 exec path backup r all reset`

   会在当前目录下生成一个`年份日期_时间\backup`的目录(如 261118_105152\backup )，记下这个目录，后续都将这个目录称为`备份目录`


3. 根据备份恢复

   断电 10 秒 → 先启动命令 → 再插 USB：

   启动命令：`.\tools\spd_dump.exe --wait 300 --kickto 2 exec write_parts "D:\刷机\**\backup" reset`，

   注意替换`**`为临时生成的目录名称（日期）

# 解锁

1. 写工程 U-Boot 到 uboot_a
   断电 10 秒 → 先启动命令 → 再插 USB：

   启动命令:`./tools/spd_dump --wait 300 --kickto 2 exec timeout 30000 write_part uboot_a "D:\刷机\unlock\F50_uboot_eng.bin" reset`

2. 进入 fastboot

   如果一次没有进入成功，多试几次
   ```sh
   # 进入 fastboot
   adb reboot bootloader
   # 等待设备启动成功
   fastboot devices
   ```

   应看到：
   324452943817    fastboot

3. subut 解锁

   Chrome/Edge 打开：
   https://unisoc-android.github.io/subut/

   Connect → 选择 Android Bootloader Interface → Unlock
   等到页面显示：
   Device status: Unlocked!

4. 退出 fastboot

   设备断电 10 秒

5. 验证,需要重新开启 usb 调试
   ```bash
   adb shell getprop ro.boot.flash.locked          # 0
   adb shell getprop ro.boot.verifiedbootstate     # orange
   adb shell getprop ro.boot.vbmeta.device_state   # unlocked
   ```

# 准备 F50 构建 openwrt 镜像环境

* 上传工具

```powershell
adb shell mkdir -p /data/local/tmp/
# 上传工具
adb push .\tools\f50-image-tools /data/local/tmp/
# 增加执行权限
adb shell chmod 700 /data/local/tmp/f50-image-tools/lz4 /data/local/tmp/f50-image-tools/debugfs /data/local/tmp/f50-image-tools/cpio

# 测试，以下命令都能执行
adb shell /data/local/tmp/f50-image-tools/lz4 --version
adb shell /data/local/tmp/f50-image-tools/cpio --version
adb shell 'LD_LIBRARY_PATH=/data/local/tmp/f50-image-tools /data/local/tmp/f50-image-tools/debugfs -V'
```

* 上传公共组件
```powershell
adb shell mkdir -p /data/local/tmp/f50-openwrt-build/payload
adb push .\payload /data/local/tmp/f50-openwrt-build/

# 验证
adb shell 'cd /data/local/tmp/f50-openwrt-build/payload && sha256sum Image common.lz4 rescue.lz4 normal.lz4 emmc.img.gz'
```


* 从原厂备份中提取封装数据
```powershell
$F50Backup = (Resolve-Path -LiteralPath '.\261118_105152\backup' -ErrorAction Stop).Path
$F50BootPath = Join-Path $F50Backup 'boot_a'
$F50Boot = [IO.File]::ReadAllBytes($F50BootPath)
$F50Footer = $F50Boot.Length - 64

if ($F50Boot.Length -ne 64MB -or
    [Text.Encoding]::ASCII.GetString($F50Boot, 0, 8) -ne 'ANDROID!' -or
    [BitConverter]::ToUInt32($F50Boot, 40) -ne 4 -or
    [Text.Encoding]::ASCII.GetString($F50Boot, $F50Footer, 4) -ne 'AVBf') {
    throw '原厂 boot_a 格式不符合预期'
}

# AVB footer 中的 vbmeta 偏移和长度是大端整数。
$F50AvbFields = New-Object byte[] 16
[Buffer]::BlockCopy($F50Boot, ($F50Footer + 20), $F50AvbFields, 0, 16)
[Array]::Reverse($F50AvbFields, 0, 8)
[Array]::Reverse($F50AvbFields, 8, 8)
$F50AvbOffset = [BitConverter]::ToUInt64($F50AvbFields, 0)
$F50AvbSize = [BitConverter]::ToUInt64($F50AvbFields, 8)

if ($F50AvbOffset -lt 4096 -or $F50AvbOffset -ge $F50Footer -or
    $F50AvbSize -lt 256 -or $F50AvbSize -gt ($F50Footer - $F50AvbOffset) -or
    [Text.Encoding]::ASCII.GetString($F50Boot, [int]$F50AvbOffset, 4) -ne 'AVB0') {
    throw '原厂 vbmeta 位置或格式异常'
}

$F50Meta = New-Object byte[] (4160 + [int]$F50AvbSize)
[Buffer]::BlockCopy($F50Boot, 0, $F50Meta, 0, 4096)
[Buffer]::BlockCopy($F50Boot, [int]$F50AvbOffset, $F50Meta, 4096, [int]$F50AvbSize)
[Buffer]::BlockCopy($F50Boot, $F50Footer, $F50Meta, (4096 + [int]$F50AvbSize), 64)

$F50Misc = [IO.File]::ReadAllBytes((Join-Path $F50Backup 'misc'))
$F50Bcb = New-Object byte[] 32
[Buffer]::BlockCopy($F50Misc, 2048, $F50Bcb, 0, 32)
if ([Text.Encoding]::ASCII.GetString($F50Bcb, 0, 2) -ne '_a' -or
    [Text.Encoding]::ASCII.GetString($F50Bcb, 4, 4) -ne 'BCAB' -or
    ($F50Bcb[12] -band 128) -eq 0) {
    throw '备份中的槽位记录不符合 Android A 槽的预期'
}

# 保存到当前目录下的 tmp 目录内
$F50Temp = Join-Path (Get-Location).Path ('tmp\f50-stock-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $F50Temp -ErrorAction Stop | Out-Null
[IO.File]::WriteAllBytes("$F50Temp\stock-v4-meta.bin", $F50Meta)
[IO.File]::WriteAllBytes("$F50Temp\stock-bcb.bin", $F50Bcb)
$F50Hash = (Get-FileHash -LiteralPath $F50BootPath -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText("$F50Temp\f50-stock.sha256", "$F50Hash`n", [Text.Encoding]::ASCII)


# 上传到 F50
adb push "$F50Temp\stock-v4-meta.bin" /data/local/tmp/f50-openwrt-build/stock/stock-v4-meta.bin
adb push "$F50Temp\stock-bcb.bin" /data/local/tmp/f50-openwrt-build/stock/stock-bcb.bin
adb push "$F50Temp\f50-stock.sha256" /data/local/tmp/f50-openwrt-build/stock/f50-stock.sha256
# 校验,sha256 一致
Get-ChildItem -LiteralPath $F50Temp -File | Get-FileHash -Algorithm SHA256
adb shell 'cd /data/local/tmp/f50-openwrt-build/stock && sha256sum stock-v4-meta.bin stock-bcb.bin f50-stock.sha256'
```

* 准备 Android 运行文件
现在把基带和看门狗所需的程序、运行库及 Android 属性直接复制到 F50 的打包目录。属性逐个连续读取两次，遇到变化就只重试该区域
```shell
# 首先进入 android shell
adb shell

# 复制和提取需要的信息放到 /data/local/tmp/f50-openwrt-build 下
(
    set -e
    umask 022
    cd /data/local/tmp/f50-openwrt-build
    tree=$(mktemp -d "$PWD/.android-build.XXXXXX")

    mkdir -p "$tree"/apex/com.android.runtime/{bin,lib64} \
        "$tree"/system/{bin,lib64} "$tree"/vendor/{bin,etc,lib64} \
        "$tree"/linkerconfig "$tree"/dev/__properties__

    cp -L /apex/com.android.runtime/bin/linker64 "$tree/apex/com.android.runtime/bin/"
    cp -RL /apex/com.android.runtime/lib64/bionic "$tree/apex/com.android.runtime/lib64/"

    for lib in android.system.suspend-V1-ndk libandroid_runtime_lazy libbase \
        libbinder libbinder_ndk libc++ libcgrouprc libcrypto libcutils libexpat \
        libhardware_legacy libhidlbase liblog libpackagelistparser libpcre2 \
        libprocessgroup libselinux libtrusty libutils libvndksupport libz; do
        cp -L "/system/lib64/$lib.so" "$tree/system/lib64/"
    done

    for program in cp_diskserver getprop modem_control refnotify sh toybox_vendor; do
        cp -L "/vendor/bin/$program" "$tree/vendor/bin/"
    done

    cp -L /vendor/lib64/lib_crypto.so /vendor/lib64/libkernelbootcp.trusty.so "$tree/vendor/lib64/"
    cp -L /vendor/etc/cp_dump_info.xml /vendor/etc/modem_ch_info.xml \
        /vendor/etc/modem_cp_info.xml /vendor/etc/modem_sp_info.xml \
        /vendor/etc/ueventd.rc "$tree/vendor/etc/"
    if test -f /vendor/etc/wcn_to_mipi.xml; then
        cp -L /vendor/etc/wcn_to_mipi.xml "$tree/vendor/etc/"
    fi

    props=/dev/__properties__
    dest="$tree/dev/__properties__"
    scratch="$tree/.property-check"

    copy_property() {
        for attempt in 1 2 3 4 5; do
            cat "$props/$1" > "$dest/$1"
            cat "$props/$1" > "$scratch"
            if cmp -s "$dest/$1" "$scratch"; then
                return 0
            fi
        done
        echo "属性持续变化：$1"
        return 1
    }

    copy_property property_info
    contexts=$(toybox strings "$dest/property_info" |
        toybox grep -E '^u:object_r:[A-Za-z0-9_]+:s0$' | toybox sort -u)

    count=0
    for context in $contexts; do
        test -f "$props/$context" || continue
        copy_property "$context"
        count=$((count + 1))
    done
    test "$count" -gt 0 || { echo '没有读到属性区域'; exit 1; }
    cat "$props/properties_serial" > "$dest/properties_serial"
    rm -f "$scratch"

    ln -s /apex/com.android.runtime/bin/linker64 "$tree/system/bin/linker64"
    touch "$tree/linkerconfig/ld.config.txt"
    find "$tree" -type d -exec chmod 755 {} +
    find "$tree" -type f -exec chmod 644 {} +
    chmod 755 "$tree/apex/com.android.runtime/bin/linker64" "$tree"/vendor/bin/*
    chmod 444 "$dest"/*

    if test -e android; then
        mv android "android.previous-${tree##*.}"
    fi
    mv "$tree" android
    printf 'ANDROID_RUNTIME_READY 属性区域=%s\n' "$count"
)

# 返回一下内容，并且 属性区域 大于 0 代表完成
ANDROID_RUNTIME_READY 属性区域=332
```

# 构建 boot

* 生成本机 ramdisk
```bash
(
    set -e
    umask 022
    cd /data/local/tmp/f50-openwrt-build

    tools=/data/local/tmp/f50-image-tools
    stock=stock/stock-bcb.bin

    test "$(getprop ro.boot.slot_suffix)" = _a
    test -x android/vendor/bin/modem_control
    test "$(stat -c %s "$stock")" -eq 32

    crc_bytes() {
        head -c 28 "$1" | gzip -c | tail -c 8 | head -c 4
    }
    hex_bytes() {
        od -An -tx1 | tr -d ' \n'
    }

    test "$(crc_bytes "$stock" | hex_bytes)" = "$(tail -c 4 "$stock" | hex_bytes)" ||
        { echo '原厂槽位记录 CRC 不一致'; exit 1; }

    mkdir -p etc
    printf 'f50\n' > etc/mu300-device
    printf 'b\n' > etc/mu300-linux-slot
    printf 'emmc\n' > etc/f50-medium
    cp stock/f50-stock.sha256 etc/f50-stock.sha256

    unit=$(getprop ro.boot.serialno)
    if test -z "$unit"; then unit=$(getprop ro.serialno); fi
    test -n "$unit"
    printf '%s' "$unit" | sha256sum | cut -d ' ' -f 1 > etc/f50-unit.sha256

    make_bcb() {
        cp "$stock" "$1"
        printf '_%s\000\000' "$2" | dd of="$1" bs=1 conv=notrunc 2>/dev/null
        printf '%s' "$3" | xxd -r -p | dd of="$1" bs=1 seek=12 conv=notrunc 2>/dev/null
        printf '%s' "$4" | xxd -r -p | dd of="$1" bs=1 seek=14 conv=notrunc 2>/dev/null
        crc_bytes "$1" > bcb-crc.bin
        dd if=bcb-crc.bin of="$1" bs=1 seek=28 conv=notrunc 2>/dev/null
        test "$(crc_bytes "$1" | hex_bytes)" = "$(tail -c 4 "$1" | hex_bytes)"
    }

    make_bcb etc/misc-bc-slot-a.bin a 9f 1e
    make_bcb etc/misc-bc-slot-b-trial.bin b 9e 2f

    find android etc -print0 |
        "$tools/cpio" --null -o -H newc --owner=0:0 --quiet > boot-local.cpio
    "$tools/lz4" -l -c boot-local.cpio > boot-local.lz4
    cat boot-local.lz4 payload/common.lz4 payload/normal.lz4 > boot-ramdisk.lz4

    stat -c '%n %s bytes' boot-ramdisk.lz4
    echo BOOT_RAMDISK_READY
)

# 返回 BOOT_RAMDISK_READY 代表完成
```

* 构建 boot
```bash

(
    set -e
    cd /data/local/tmp/f50-openwrt-build

    meta=stock/stock-v4-meta.bin
    image=f50-boot-b.img.part
    footer=boot-avb-footer.bin

    kernel_size=$(stat -c %s payload/Image)
    ramdisk_size=$(stat -c %s boot-ramdisk.lz4)
    vbmeta_size=$(($(stat -c %s "$meta") - 4160))
    ramdisk_offset=$((4096 + (kernel_size + 4095) / 4096 * 4096))
    vbmeta_offset=$((ramdisk_offset + (ramdisk_size + 4095) / 4096 * 4096))

    test "$vbmeta_size" -ge 256
    test "$((vbmeta_offset + vbmeta_size))" -le 50331648 ||
        { echo '镜像载荷超出 48 MiB 边界'; exit 1; }
    test "$(head -c 8 "$meta")" = 'ANDROID!'
    test "$(od -An -j 40 -N 4 -tu4 "$meta" | tr -d ' \n')" = 4
    test "$(tail -c 64 "$meta" | head -c 4)" = 'AVBf'

    le32() {
        printf '%08x' "$1" |
            sed 's/^\(..\)\(..\)\(..\)\(..\)$/\4\3\2\1/' |
            xxd -r -p
    }

    head -c 4096 "$meta" > "$image"
    { le32 "$kernel_size"; le32 "$ramdisk_size"; } |
        dd of="$image" bs=1 seek=8 conv=notrunc 2>/dev/null
    head -c 1540 /dev/zero |
        dd of="$image" bs=1 seek=44 conv=notrunc 2>/dev/null
    printf 'loglevel=5' |
        dd of="$image" bs=1 seek=44 conv=notrunc 2>/dev/null

    cat payload/Image >> "$image"
    truncate -s "$ramdisk_offset" "$image"
    cat boot-ramdisk.lz4 >> "$image"
    truncate -s "$vbmeta_offset" "$image"
    dd if="$meta" bs=1 skip=4096 count="$vbmeta_size" 2>/dev/null >> "$image"

    tail -c 64 "$meta" > "$footer"
    printf '%016x%016x%016x' "$vbmeta_offset" "$vbmeta_offset" "$vbmeta_size" |
        xxd -r -p |
        dd of="$footer" bs=1 seek=12 conv=notrunc 2>/dev/null

    truncate -s 67108800 "$image"
    cat "$footer" >> "$image"
    test "$(stat -c %s "$image")" -eq 67108864
    test "$(dd if="$image" bs=1 skip="$vbmeta_offset" count=4 2>/dev/null)" = 'AVB0'
    test "$(tail -c 64 "$image" | head -c 4)" = 'AVBf'

    mv "$image" f50-boot-b.img
    printf 'vbmeta_offset=%s\n' "$vbmeta_offset"
    stat -c '%n %s bytes' f50-boot-b.img
    sha256sum f50-boot-b.img
)
```

* 校验 boot
使用 `exit` 退出安卓 shell
```powershell
# 拉取刚刚构建的 boot 到 windows。sha256 和构建的时候一致
adb pull /data/local/tmp/f50-openwrt-build/f50-boot-b.img .\tmp\f50-boot-b.img
(Get-FileHash -Algorithm SHA256 -LiteralPath '.\tmp\f50-boot-b.img').Hash

# 写入 b 槽
adb reboot bootloader
fastboot getvar current-slot
fastboot getvar partition-size:boot_b
fastboot flash boot_b .\tmp\f50-boot-b.img
fastboot set_active b # 使用 b 槽启动

# 可以进入救援 shell，电脑 usb 网卡自动获取 192.168.77.1， telnet 可以登录到救援 shell
```

# 构建 openwrt

```bash
# 先进入 安卓 shell
adb shell

# 构建 ext4
(
    set -e
    cd /data/local/tmp/f50-openwrt-build

    gzip -dc payload/emmc.img.gz > system.img.part
    test "$(stat -c %s system.img.part)" -eq 2147483648 ||
        { echo '系统镜像应为 2 GiB'; exit 1; }

    label=$(dd if=system.img.part bs=1 skip=1144 count=16 2>/dev/null | tr -d '\000')
    test "$label" = mu300root ||
        { echo '系统镜像标签应为 mu300root'; exit 1; }

    e2fsck -fn system.img.part

    if test -e system.img; then
        previous=$(mktemp -d "$PWD/system-previous.XXXXXX")
        mv system.img "$previous/system.img"
    fi
    mv system.img.part system.img
    echo SYSTEM_BASE_READY
)

# 加入本机运行文件和无线固件

(
    set -e
    cd /data/local/tmp/f50-openwrt-build

    tools=/data/local/tmp/f50-image-tools
    root=/system.pending
    dest="$root/opt/mu300/android"

    if test ! -f system.img || test -L system.img; then
        echo '找不到普通镜像文件 system.img'
        exit 1
    fi
    test "$(stat -c %s system.img)" -eq 2147483648
    test -x android/vendor/bin/modem_control

    find android -print > runtime-paths.txt
    find /odm/firmware -mindepth 1 -maxdepth 1 -print > firmware-paths.txt
    test -s firmware-paths.txt

    {
        while IFS= read -r source; do
            case "$source" in
                android/dev) continue ;;
                android/dev/__properties__|android/dev/__properties__/*)
                    target="$dest/dev-properties${source#android/dev/__properties__}" ;;
                *) target="$dest${source#android}" ;;
            esac

            if test -L "$source"; then
                printf 'symlink %s %s\n' "$target" "$(readlink "$source")"
            elif test -d "$source"; then
                printf 'mkdir %s\n' "$target"
                printf 'set_inode_field %s mode 040755\n' "$target"
            else
                test -f "$source" && test -r "$source" ||
                    { echo "运行文件不可读：$source" >&2; exit 1; }
                printf 'write %s %s\n' "$source" "$target"
                printf 'set_inode_field %s mode 0100%s\n' "$target" "$(stat -c %a "$source")"
            fi
            printf 'set_inode_field %s uid 0\nset_inode_field %s gid 0\n' "$target" "$target"
        done < runtime-paths.txt

        while IFS= read -r source; do
            if test ! -f "$source" || test -L "$source" || test ! -r "$source"; then
                echo "固件不是可读的普通文件：$source" >&2
                exit 1
            fi

            target="$root/lib/firmware/${source##*/}"
            printf 'write %s %s\n' "$source" "$target"
            printf 'set_inode_field %s uid 0\nset_inode_field %s gid 0\n' "$target" "$target"
            printf 'set_inode_field %s mode 0100644\n' "$target"
        done < firmware-paths.txt
    } > debugfs-runtime.txt

    if ! LC_ALL=C LD_LIBRARY_PATH="$tools" "$tools/debugfs" \
        -w -f debugfs-runtime.txt system.img > debugfs-runtime.log 2> debugfs-runtime.err; then
        cat debugfs-runtime.err
        exit 1
    fi

    if grep -Ev '^(debugfs [0-9]|[[:space:]]*$)' debugfs-runtime.err; then
        echo '有文件写入失败'
        exit 1
    fi

    e2fsck -fn system.img
    printf 'SYSTEM_RUNTIME_READY 固件=%s\n' "$(wc -l < firmware-paths.txt)"
)
```

* 设置 openwrt 密码
```bash
(
    set -e
    umask 077
    cd /data/local/tmp/f50-openwrt-build

    tools=/data/local/tmp/f50-image-tools
    scratch=$(mktemp -d "$PWD/.password.XXXXXX")
    terminal=$(stty -g)
    trap 'stty "$terminal"; rm -rf "$scratch"' EXIT

    "$tools/lz4" -dc payload/common.lz4 > "$scratch/common.cpio"
    (
        cd "$scratch"
        "$tools/cpio" -id --no-preserve-owner --quiet -F common.cpio bin/busybox
    )
    chmod 700 "$scratch/bin/busybox"

    stty -echo
    printf '输入新的 OpenWrt root 密码：'
    IFS= read -r password
    printf '\n再输入一次：'
    IFS= read -r confirm
    stty "$terminal"
    printf '\n'
    test -n "$password" && test "$password" = "$confirm" ||
        { echo '两次密码必须一致且非空'; exit 1; }

    printf '%s\n' "$password" |
        "$scratch/bin/busybox" mkpasswd -m sha512 > "$scratch/hash"
    unset password confirm
    grep -q '^\$6\$' "$scratch/hash" ||
        { echo '未生成 SHA-512 密码散列'; exit 1; }

    debugfs_run() {
        LC_ALL=C LD_LIBRARY_PATH="$tools" "$tools/debugfs" "$@"
    }
    apply_batch() {
        debugfs_run -w -f "$1" system.img > "$scratch/batch.log" 2> "$scratch/batch.err" ||
            { cat "$scratch/batch.err"; return 1; }
        if grep -Ev '^(debugfs [0-9]|[[:space:]]*$)' "$scratch/batch.err"; then
            return 1
        fi
    }

    shadow=/system.pending/etc/shadow
    staged=/system.pending/etc/.f50-shadow-new
    debugfs_run -R "dump $shadow $scratch/shadow" system.img
    test -s "$scratch/shadow"

    awk -F: -v OFS=: '
        NR == FNR { hash = $0; next }
        $1 == "root" { $2 = hash; count++ }
        { print }
        END { if (count != 1) exit 1 }
    ' "$scratch/hash" "$scratch/shadow" > "$scratch/shadow.new"

    {
        printf 'write %s %s\n' "$scratch/shadow.new" "$staged"
        printf 'set_inode_field %s uid 0\n' "$staged"
        printf 'set_inode_field %s gid 0\n' "$staged"
        printf 'set_inode_field %s mode 0100600\n' "$staged"
    } > "$scratch/stage.cmd"
    apply_batch "$scratch/stage.cmd"

    debugfs_run -R "dump $staged $scratch/check" system.img
    cmp -s "$scratch/shadow.new" "$scratch/check"

    printf 'rm %s\nln %s %s\nunlink %s\n' "$shadow" "$staged" "$shadow" "$staged" \
        > "$scratch/replace.cmd"
    apply_batch "$scratch/replace.cmd"

    debugfs_run -R "dump $shadow $scratch/final" system.img
    cmp -s "$scratch/shadow.new" "$scratch/final"
    e2fsck -fn system.img
    echo SYSTEM_PASSWORD_READY
)
```

* 激活并压缩 openwrt 系统镜像

```bash
(
    set -e
    cd /data/local/tmp/f50-openwrt-build
    tools=/data/local/tmp/f50-image-tools

    debugfs_run() {
        LC_ALL=C LD_LIBRARY_PATH="$tools" "$tools/debugfs" "$@"
    }
    inode_for() {
        debugfs_run -R "stat $1" system.img 2>/dev/null |
            awk '/^Inode:/ { print $2; exit }'
    }

    pending=$(inode_for /system.pending)
    active=$(inode_for /openwrt-luci)

    if test -n "$pending"; then
        if test -z "$active"; then
            debugfs_run -w -R 'ln /system.pending /openwrt-luci' system.img
        fi
        test "$(inode_for /openwrt-luci)" = "$pending" ||
            { echo '两个目录指向不同的 inode，停止'; exit 1; }
        debugfs_run -w -R 'unlink /system.pending' system.img
        test -z "$(inode_for /system.pending)"
    fi

    test -n "$(inode_for /openwrt-luci/sbin/init)"
    test -n "$(inode_for /openwrt-luci/etc/shadow)"
    test -n "$(inode_for /openwrt-luci/opt/mu300/android/vendor/bin/modem_control)"
    test "$(stat -c %s system.img)" -eq 2147483648
    e2fsck -fn system.img

    gzip -c system.img > system.img.gz.part
    mv system.img.gz.part system.img.gz
    sha256sum system.img system.img.gz > system.sha256
    stat -c '%n %s bytes' system.img system.img.gz
    echo SYSTEM_IMAGE_READY
)
```

* 复制镜像到 windows
先用 `exit` 退出安卓 shell
```powershell

adb pull /data/local/tmp/f50-openwrt-build/system.img.gz .\tmp\system.img.gz
adb pull /data/local/tmp/f50-openwrt-build/system.sha256 .\tmp\system.sha256

Get-FileHash -Algorithm SHA256 -LiteralPath '.\tmp\system.img.gz'
Get-Content -LiteralPath '.\tmp\system.sha256'
```

# 刷入 openwrt

* 切换到 b 槽 boot 启动, 会进入救援模式
```powershell
adb reboot bootloader
fastboot getvar current-slot
fastboot set_active b
```

* 传入 openwrt
```bash
# 救援模式默认是 192.168.77.1 的
telnet 192.168.77.1 
# 关闭看门狗
touch /run/stay

umount /disk && losetup -d /dev/loop0
grep ' /disk ' /proc/mounts
losetup -a

# 开启一个监听端口获取文件，此时需要在 windows 上执行命令传到救援系统中，在下一个代码块
nc -l -p 8081 192.168.77.1 > /run/f50-system.img.gz

# 文件获取完成后校验 hash
stat -c '%s bytes' /run/f50-system.img.gz
sha256sum /run/f50-system.img.gz
(set -o pipefail; gzip -dc /run/f50-system.img.gz | sha256sum)
```

windows 命令
```powershell
# 在刷机目录下执行
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

* 写入 openwrt 镜像
```bash
# 在救援系统中执行
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

```bash
# 确认救援 Shell 最后一行是 SYSTEM_WRITE_OK，然后执行 reboot -f
reboot -f
```

* 使用新的 openwrt 启动
```powershell
# 等进入安卓 adb
adb shell getprop ro.boot.slot_suffix
adb reboot bootloader
fastboot getvar current-slot
# 设置 b 启动槽， 会直接用 b 启动。
fastboot set_active b
```

* 进入 openwrt，设置下次启动默认 openwrt
```bash
# 登录
ssh root@192.168.77.1
# 设置
mu300-next-boot linux && mu300-next-boot status
```