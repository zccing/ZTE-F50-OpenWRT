import gzip
import hashlib
import io
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path


PLATFORM_TOOLS_URL = (
    "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
)
LIBWDI_RELEASE_URL = "https://api.github.com/repos/pbatard/libwdi/releases/latest"
TERMUX_URL = "https://packages.termux.dev/apt/termux-main/"
TERMUX_FILES = {
    "cpio": "bin/cpio",
    "e2fsprogs": "bin/debugfs",
    "lz4": "bin/lz4",
    "libandroid-posix-semaphore": "lib/libandroid-posix-semaphore.so",
    "libblkid": "lib/libblkid.so",
    "libuuid": "lib/libuuid.so",
}
ZADIG_NAME = re.compile(r"zadig-\d+(?:\.\d+)+\.exe")


def download(url, *, size=None, sha256=None):
    request = urllib.request.Request(url, headers={"User-Agent": "F50-tool-updater"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()
    if size is not None and len(data) != size:
        raise ValueError(f"下载大小不符：{url}")
    if sha256 is not None and hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError(f"SHA-256 不符：{url}")
    return data


def windows_binary(data, name):
    if not data.startswith(b"MZ"):
        raise ValueError(f"文件不是 Windows 二进制文件：{name}")
    return data


def platform_tools():
    required = {
        "adb.exe", "fastboot.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll",
        "NOTICE.txt", "source.properties",
    }
    with zipfile.ZipFile(io.BytesIO(download(PLATFORM_TOOLS_URL))) as archive:
        files = {}
        for member in archive.infolist():
            if member.is_dir():
                continue
            match = re.fullmatch(r"platform-tools/([a-zA-Z0-9][a-zA-Z0-9_.-]*)", member.filename)
            if not match:
                raise ValueError(f"Platform-Tools 压缩包包含未知路径：{member.filename}")
            name = match[1]
            data = archive.read(member)
            if name.endswith((".exe", ".dll")):
                windows_binary(data, name)
            files[name] = data

    if missing := required - files.keys():
        raise ValueError(f"Platform-Tools 压缩包缺少文件：{', '.join(sorted(missing))}")
    print(files["source.properties"].decode().strip())
    return {Path("platform-tools", name): data for name, data in files.items()}


def zadig():
    release = json.loads(download(LIBWDI_RELEASE_URL))
    assets = [asset for asset in release["assets"] if ZADIG_NAME.fullmatch(asset["name"])]
    if len(assets) != 1:
        raise ValueError("libwdi 最新发行版应包含一个 Zadig Windows 安装程序")
    asset = assets[0]
    name = asset["name"]
    digest = asset.get("digest")
    sha256 = digest.removeprefix("sha256:") if digest else None
    data = download(asset["browser_download_url"], size=asset["size"], sha256=sha256)
    print(f"{name} ({release['tag_name']})")
    return {Path(name): windows_binary(data, name)}


def termux_tools():
    index_url = TERMUX_URL + "dists/stable/main/binary-aarch64/Packages.gz"
    packages = {}
    for paragraph in gzip.decompress(download(index_url)).decode().split("\n\n"):
        fields = dict(
            line.split(": ", 1) for line in paragraph.splitlines()
            if line and not line[0].isspace() and ": " in line
        )
        if fields.get("Package") in TERMUX_FILES:
            packages[fields["Package"]] = fields

    files = {}
    for name, path in TERMUX_FILES.items():
        package = packages[name]
        filename = package["Filename"]
        if not filename.startswith("pool/") or ".." in Path(filename).parts:
            raise ValueError(f"Termux 包索引包含未知路径：{filename}")
        deb = download(TERMUX_URL + filename, size=int(package["Size"]), sha256=package["SHA256"])
        # dpkg-deb 1.23.7 会把管道读入的包误判为截断。
        with tempfile.TemporaryDirectory() as directory:
            deb_path = Path(directory) / f"{name}.deb"
            deb_path.write_bytes(deb)
            contents = subprocess.check_output(["dpkg-deb", "--fsys-tarfile", str(deb_path)])
        with tarfile.open(fileobj=io.BytesIO(contents)) as archive:
            member = archive.getmember(f"./data/data/com.termux/files/usr/{path}")
            if not member.isfile():
                raise ValueError(f"Termux 包的目标文件类型有变：{path}")
            with archive.extractfile(member) as source:
                data = source.read()
        # 校验无需在 CI 上运行 Android 二进制文件。
        if not data.startswith(b"\x7fELF\x02\x01") or data[18:20] != b"\xb7\x00":
            raise ValueError(f"文件不是 Android 所用的 AArch64 ELF：{path}")
        files[Path("f50-image-tools", Path(path).name)] = data
        print(f"{name} {package['Version']}")
    return files


def sha256sums(files):
    return "".join(
        f"{hashlib.sha256(data).hexdigest()}  {path.as_posix()}\n"
        for path, data in sorted(files.items())
    ).encode("ascii")


def with_checksums(tools_dir, files):
    image_tools_dir = Path("f50-image-tools")
    image_tools = {
        path.relative_to(image_tools_dir): data
        for path, data in files.items()
        if path.parent == image_tools_dir
    }
    pinned_tools = {
        Path(name): (tools_dir / name).read_bytes()
        for name in ("spd_dump.exe", "libusb-1.0.dll")
    }
    return files | {
        Path("SHA256SUMS"): sha256sums(files | pinned_tools),
        image_tools_dir / "SHA256SUMS": sha256sums(image_tools),
    }


def install(tools_dir, files):
    changes = {}
    for path, data in files.items():
        target = tools_dir / path
        if not target.is_file() or target.read_bytes() != data:
            changes[path] = data
    for path in tools_dir.iterdir():
        if path.is_file() and ZADIG_NAME.fullmatch(path.name) and Path(path.name) not in files:
            changes[Path(path.name)] = None
    if not changes:
        print("工具已是最新版本")
        return

    # 在同一磁盘上备份旧文件，写入遇到错误时恢复本次已替换的文件。
    with tempfile.TemporaryDirectory(dir=tools_dir) as temp_dir:
        staging = Path(temp_dir)
        for index, (path, data) in enumerate(changes.items()):
            target = tools_dir / path
            if target.exists():
                shutil.copy2(target, staging / f"{index}.old")
            if data is not None:
                (staging / f"{index}.new").write_bytes(data)

        applied = []
        try:
            for index, (path, data) in enumerate(changes.items()):
                target = tools_dir / path
                target.parent.mkdir(parents=True, exist_ok=True)
                if data is None:
                    target.unlink()
                else:
                    (staging / f"{index}.new").replace(target)
                applied.append((index, target))
        except OSError:
            for index, target in reversed(applied):
                backup = staging / f"{index}.old"
                if backup.exists():
                    backup.replace(target)
                else:
                    target.unlink()
            raise

    for path, data in changes.items():
        action = "已移除" if data is None else "已更新"
        print(f"{action} {path}")


if __name__ == "__main__":
    tools_dir = Path(__file__).resolve().parent
    files = platform_tools() | zadig() | termux_tools()
    install(tools_dir, with_checksums(tools_dir, files))
