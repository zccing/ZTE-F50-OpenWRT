# 制作这台 F50 的镜像

先让 F50 启动到原厂 Android，打开 USB 调试。在电脑的刷机文件夹里打开 PowerShell。下面每次只复制一段，报错就停在当前步骤。

## 1. 把工具和底包传到 F50

```powershell
.\tools\platform-tools\adb.exe shell mkdir -p /data/local/tmp/
# 上传工具
.\tools\platform-tools\adb.exe push .\tools\f50-image-tools /data/local/tmp/
# 增加执行权限
.\tools\platform-tools\adb.exe shell chmod 700 /data/local/tmp/f50-image-tools/lz4 /data/local/tmp/f50-image-tools/debugfs /data/local/tmp/f50-image-tools/cpio

# 测试，以下命令都能执行
.\tools\platform-tools\adb.exe shell /data/local/tmp/f50-image-tools/lz4 --version
.\tools\platform-tools\adb.exe shell /data/local/tmp/f50-image-tools/cpio --version
.\tools\platform-tools\adb.exe shell 'LD_LIBRARY_PATH=/data/local/tmp/f50-image-tools /data/local/tmp/f50-image-tools/debugfs -V'
```

```powershell
.\tools\platform-tools\adb.exe shell mkdir -p /data/local/tmp/f50-openwrt-build/payload
.\tools\platform-tools\adb.exe push .\payload /data/local/tmp/f50-openwrt-build/

# 验证
.\tools\platform-tools\adb.exe shell 'cd /data/local/tmp/f50-openwrt-build/payload && sha256sum Image common.lz4 rescue.lz4 normal.lz4 emmc.img.gz'
```

把最后显示的五个 SHA-256 值按文件名和清单对照。全部一致再继续。[底包校验清单](../payload/README.md)

## 2. 读取本机备份和运行文件

先在 PowerShell 运行下面的命令。按提示输入备份目录的完整路径，例如 `D:\刷机\261118_105152\backup`。核对最后列出的三个文件，电脑和 F50 上同名文件的 SHA-256 应一致。

<details>
<summary>展开 PowerShell 命令</summary>

```powershell
$F50Backup = (Resolve-Path -LiteralPath (Read-Host '输入这台 F50 的备份目录（完整路径）') -ErrorAction Stop).Path
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
.\tools\platform-tools\adb.exe shell mkdir -p /data/local/tmp/f50-openwrt-build/stock
.\tools\platform-tools\adb.exe push "$F50Temp\stock-v4-meta.bin" /data/local/tmp/f50-openwrt-build/stock/stock-v4-meta.bin
.\tools\platform-tools\adb.exe push "$F50Temp\stock-bcb.bin" /data/local/tmp/f50-openwrt-build/stock/stock-bcb.bin
.\tools\platform-tools\adb.exe push "$F50Temp\f50-stock.sha256" /data/local/tmp/f50-openwrt-build/stock/f50-stock.sha256
# 校验,sha256 一致
Get-ChildItem -LiteralPath $F50Temp -File | Get-FileHash -Algorithm SHA256
.\tools\platform-tools\adb.exe shell 'cd /data/local/tmp/f50-openwrt-build/stock && sha256sum stock-v4-meta.bin stock-bcb.bin f50-stock.sha256'
```

</details>

然后在 PowerShell 输入 `.\tools\platform-tools\adb.exe shell` 进入 F50。运行下面这段，看到 `ANDROID_RUNTIME_READY` 且属性区域数量大于 0，再继续。

<details>
<summary>展开 F50 命令</summary>

```sh
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
```

</details>

## 3. 制作启动镜像

留在 F50 里，依次运行下面两段。第一段会显示 `BOOT_RAMDISK_READY`。第二段会显示 `f50-boot-b.img` 的大小和 SHA-256，记下这个值。

<details>
<summary>第 1 段：打包启动文件</summary>

```sh
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
```

</details>

<details>
<summary>第 2 段：生成启动镜像</summary>

```sh
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

</details>

## 4. 制作 OpenWrt 系统镜像

继续在 F50 里按顺序运行。每段结束时，确认出现标题里的完成标记。第 3 段会让你输入两次密码，输入时屏幕不会显示字符。记住这个密码，稍后用它登录。

<details>
<summary>第 1 段：解压系统底包（SYSTEM_BASE_READY）</summary>

```sh
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
```

</details>

<details>
<summary>第 2 段：加入本机文件和无线固件（SYSTEM_RUNTIME_READY）</summary>

```sh
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

</details>

<details>
<summary>第 3 段：设置 OpenWrt 登录密码（SYSTEM_PASSWORD_READY）</summary>

```sh
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

</details>

<details>
<summary>第 4 段：压缩系统镜像（SYSTEM_IMAGE_READY）</summary>

```sh
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

</details>

## 5. 把两个镜像存到电脑

输入 `exit` 回到 PowerShell，再运行下面的命令。

```powershell
.\tools\platform-tools\adb.exe pull /data/local/tmp/f50-openwrt-build/f50-boot-b.img .\tmp\f50-boot-b.img
(Get-FileHash -Algorithm SHA256 -LiteralPath '.\tmp\f50-boot-b.img').Hash

.\tools\platform-tools\adb.exe pull /data/local/tmp/f50-openwrt-build/system.img.gz .\tmp\system.img.gz
.\tools\platform-tools\adb.exe pull /data/local/tmp/f50-openwrt-build/system.sha256 .\tmp\system.sha256

Get-FileHash -Algorithm SHA256 -LiteralPath '.\tmp\system.img.gz'
Get-Content -LiteralPath '.\tmp\system.sha256'
```

核对两个 SHA-256 值。启动镜像要和第 3 步的输出一致，系统压缩包要和 `system.sha256` 中 `system.img.gz` 那一行一致。两项都对上，就可以[刷入系统](flash.md)。
