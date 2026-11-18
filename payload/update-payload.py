import argparse
import fcntl
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
import uuid
import zlib
from datetime import datetime
from pathlib import Path


RELEASES = "https://api.github.com/repos/dikeckaan/mu300-linux/releases/"
KERNEL = "mu300-kernel.tar.gz"
ROOTFS = "mu300-openwrt-luci-rootfs.tar.gz"
PAYLOAD_FILES = ("Image", "common.lz4", "rescue.lz4", "normal.lz4", "emmc.img.gz")
IMAGE_SIZE = 2 * 1024**3


def open_url(url):
    request = urllib.request.Request(url, headers={"User-Agent": "F50-payload-updater"})
    return urllib.request.urlopen(request, timeout=60)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024**2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_release(tag):
    endpoint = "tags/" + urllib.parse.quote(tag, safe="") if tag else "latest"
    with open_url(RELEASES + endpoint) as response:
        release = json.load(response)
    assets = {asset["name"]: asset for asset in release["assets"]}
    published = datetime.fromisoformat(release["published_at"].replace("Z", "+00:00"))
    return release["tag_name"], int(published.timestamp()), {name: assets[name] for name in (KERNEL, ROOTFS)}


def download_asset(asset, path):
    with open_url(asset["browser_download_url"]) as response, path.open("wb") as file:
        shutil.copyfileobj(response, file)
    if path.stat().st_size != asset["size"] or f"sha256:{sha256(path)}" != asset["digest"]:
        raise ValueError(f"发行文件校验失败：{path.name}")


def extract_kernel(archive_path, work):
    with tarfile.open(archive_path) as archive:
        for source, target in (("Image", "Image"), ("ramdisk-generic.lz4", "common.lz4")):
            member = archive.getmember(f"./{source}")
            if not member.isfile():
                raise ValueError(f"内核包的文件类型有变：{source}")
            with archive.extractfile(member) as file, (work / target).open("wb") as output:
                shutil.copyfileobj(file, output)
    with (work / "Image").open("rb") as image, (work / "common.lz4").open("rb") as ramdisk:
        image.seek(56)
        if image.read(4) != b"ARM\x64" or ramdisk.read(4) != b"\x02\x21\x4c\x18":
            raise ValueError("内核或基础 ramdisk 格式有变")


def build_image(rootfs, work, image_uuid, published):
    image = work / "emmc.img"
    with image.open("wb") as file:
        file.truncate(IMAGE_SIZE)
    # 只记录所有权，不在宿主文件系统上执行 chown。
    env = os.environ | {
        "FAKEROOTDONTTRYCHOWN": "1",
        "SOURCE_DATE_EPOCH": str(published),
        "E2FSPROGS_FAKE_TIME": str(published),
    }
    subprocess.run(["fakeroot", "--", "bash", "-euc", r'''
        root=$1
        pending="$root/system.pending"
        mkdir -p "$pending" "$root/.mu300" "$root/boot"
        tar --extract --gzip --file "$2" --directory "$pending" \
            --numeric-owner --same-owner --same-permissions
        test -x "$pending/sbin/init"
        test -d "$pending/opt/mu300" && test -d "$pending/lib/firmware"
        test -f "$pending/etc/shadow" && test ! -L "$pending/etc/shadow"
        awk -F: -v OFS=: '
            $1 == "root" { $2 = "!"; count++ }
            { print }
            END { if (count != 1) exit 1 }
        ' "$pending/etc/shadow" > "$pending/etc/shadow.f50"
        chmod 600 "$pending/etc/shadow.f50"
        mv "$pending/etc/shadow.f50" "$pending/etc/shadow"
        printf 'off\n' > "$pending/etc/mu300/adb"
        printf 'keys\n' > "$pending/etc/mu300/adb_auth"
        printf 'openwrt-luci\n' > "$root/.mu300/boot-os"
        printf '5\n' > "$root/.mu300/boot-attempts"
        printf '5.4\n' > "$root/boot/kernel"
        cp "$root/boot/kernel" "$root/boot/installed.kernel"
        # 旧内核需要兼容的 ext4 特性。构建指南会在注入本机文件后激活 system.pending。
        /usr/sbin/mke2fs -q -F -t ext4 -b 4096 -m 0 -L mu300root -U "$4" -E "hash_seed=$4" \
            -O '^orphan_file,^metadata_csum_seed' -d "$root" "$3"
    ''', "build-image", str(work / "root"), str(rootfs), str(image), str(image_uuid)], check=True, env=env)
    subprocess.run(["/usr/sbin/e2fsck", "-fn", str(image)], check=True)
    compressed = work / "emmc.img.gz"
    with image.open("rb") as source, compressed.open("wb") as output:
        with gzip.GzipFile(filename="", mode="wb", fileobj=output, compresslevel=6, mtime=0) as stream:
            shutil.copyfileobj(source, stream)
    return {
        b"etc/f50-emmc.img.sha256": sha256(image),
        b"etc/f50-emmc.gz.sha256": sha256(compressed),
    }


def refresh_rescue(rescue, output, hashes):
    archive = bytearray(subprocess.check_output(["lz4", "-dc", str(rescue)]))
    expected = hashes.copy()
    offset = 0
    while offset < len(archive):
        header = archive[offset:offset + 110]
        if header[:6] != b"070701":
            raise ValueError("救援 ramdisk 需要 newc 格式")
        size = int(header[54:62], 16)
        name_end = offset + 110 + int(header[94:102], 16)
        name = bytes(archive[offset + 110:name_end - 1])
        if name == b"TRAILER!!!":
            break
        start = (name_end + 3) & ~3
        end = start + size
        if not offset < start <= end <= len(archive):
            raise ValueError("救援 ramdisk 条目超出范围")
        if name in hashes:
            if not re.fullmatch(rb"[0-9a-f]{64}\n", archive[start:end]):
                raise ValueError(f"救援 ramdisk 的校验值格式有变：{name.decode()}")
            archive[start:end] = (expected.pop(name) + "\n").encode()
        offset = (end + 3) & ~3
    if expected:
        raise ValueError("救援 ramdisk 缺少 eMMC 镜像校验值")
    with output.open("wb") as file:
        subprocess.run(["lz4", "-lzc"], input=archive, stdout=file, check=True)


def manifest(payload, staged):
    return "".join(
        f"{sha256(staged.get(name, payload / name))}  {name}\n"
        for name in PAYLOAD_FILES
    ).encode()


def is_current(payload, image_uuid):
    sums = payload / "SHA256SUMS"
    if not sums.is_file() or not all((payload / name).is_file() for name in PAYLOAD_FILES):
        return False
    try:
        with gzip.open(payload / "emmc.img.gz", "rb") as image:
            superblock = image.read(1024 + 120)[1024:]
    except (gzip.BadGzipFile, EOFError, zlib.error):
        return False
    return (superblock[56:58] == b"\x53\xef" and superblock[104:120] == image_uuid.bytes
            and sums.read_bytes() == manifest(payload, {}))


def publish(payload, sources):
    # 先在目标磁盘准备新旧文件，再逐个替换。写入失败时恢复本次的改动。
    with tempfile.TemporaryDirectory(dir=payload, prefix=".update-") as directory:
        stage = Path(directory)
        updates = []
        for name, source in sources.items():
            target = payload / name
            if target.is_file() and sha256(target) == sha256(source):
                continue
            shutil.copyfile(source, stage / name)
            backup = stage / f"{name}.old"
            if target.exists():
                shutil.copy2(target, backup)
            updates.append((target, backup))
        applied = []
        try:
            for target, backup in updates:
                (stage / target.name).replace(target)
                applied.append((target, backup))
        except OSError:
            for target, backup in reversed(applied):
                if backup.exists():
                    backup.replace(target)
                else:
                    target.unlink()
            raise
    print("已更新 " + "、".join(target.name for target, _ in updates) if updates else "底包已是最新版本")


def update(args, payload, work):
    staged = {}
    if not args.checksums_only:
        tag, published, assets = get_release(args.release)
        print(f"MU300 Linux {tag}", flush=True)
        digests = [assets[name].get("digest") for name in (KERNEL, ROOTFS)]
        if not all(digest and re.fullmatch(r"sha256:[0-9a-f]{64}", digest) for digest in digests):
            raise ValueError("发行版缺少有效的上游校验值")
        # 用两个上游包的校验值确定镜像 UUID，借此识别同一组已经构建好的底包。
        image_uuid = uuid.uuid5(uuid.NAMESPACE_URL, "f50-emmc:" + ":".join(digests))
        if is_current(payload, image_uuid):
            print("底包已是最新版本")
            return

        for name, asset in assets.items():
            download_asset(asset, work / name)
        extract_kernel(work / KERNEL, work)
        hashes = build_image(work / ROOTFS, work, image_uuid, published)
        refresh_rescue(payload / "rescue.lz4", work / "rescue.lz4", hashes)
        staged.update({name: work / name for name in ("Image", "common.lz4", "emmc.img.gz", "rescue.lz4")})

    sums = work / "SHA256SUMS"
    sums.write_bytes(manifest(payload, staged))
    staged[sums.name] = sums
    publish(payload, staged)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="更新 F50 公共底包")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--release", help="使用指定的 MU300 Linux 发行标签，默认使用最新正式版")
    mode.add_argument("--checksums-only", action="store_true", help="只为现有底包生成校验清单")
    args = parser.parse_args()
    script = Path(__file__).resolve()
    with script.open("rb") as lock, tempfile.TemporaryDirectory() as directory:
        fcntl.flock(lock, fcntl.LOCK_EX)
        update(args, script.parent, Path(directory))
