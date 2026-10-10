"""Read numeric Windows version resources from the selected QQ.exe only.

No execution, registry search, package-version guessing, or private logging.
Absent, contradictory, incomplete, or unreadable metadata is unknown.
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path


class _FixedFileInfo(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in (
        "signature", "structure_version", "file_ms", "file_ls", "product_ms",
        "product_ls", "flags_mask", "flags", "os", "file_type", "subtype",
        "date_ms", "date_ls",
    )]


def _version(ms: int, ls: int) -> tuple[int, int, int, int]:
    return (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)


def read_qq_version(path: Path) -> tuple[int, int, int, int] | None:
    """Return a full QQ NT Windows version, or None without guessing a build.

    Fixed file/product versions may omit the build (zero); use the other only
    when the release components agree. Conflicting full versions are unknown.
    Other product families are outside the known 9.9.x Windows build contract.
    """
    if sys.platform != "win32":
        return None
    try:
        if path.name.lower() != "qq.exe" or not path.is_file():
            return None
        before = path.stat()
        api = ctypes.WinDLL("version", use_last_error=True)
        api.GetFileVersionInfoSizeW.argtypes = [
            ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32),
        ]
        api.GetFileVersionInfoSizeW.restype = ctypes.c_uint32
        api.GetFileVersionInfoW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
        ]
        api.GetFileVersionInfoW.restype = ctypes.c_int
        api.VerQueryValueW.argtypes = [
            ctypes.c_void_p, ctypes.c_wchar_p,
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint),
        ]
        api.VerQueryValueW.restype = ctypes.c_int
        handle = ctypes.c_uint32()
        size = api.GetFileVersionInfoSizeW(str(path), ctypes.byref(handle))
        # Version resources are small; corrupt sizes must not allocate gigabytes.
        if size < ctypes.sizeof(_FixedFileInfo) or size > 1024 * 1024:
            return None
        buffer = ctypes.create_string_buffer(size)
        if not api.GetFileVersionInfoW(str(path), 0, size, buffer):
            return None
        pointer = ctypes.c_void_p()
        length = ctypes.c_uint()
        if not api.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)):
            return None
        address = pointer.value
        start = ctypes.addressof(buffer)
        if (
            address is None or length.value < ctypes.sizeof(_FixedFileInfo)
            or address < start or address + length.value > start + size
        ):
            return None
        info = _FixedFileInfo.from_buffer_copy(
            ctypes.string_at(address, ctypes.sizeof(_FixedFileInfo))
        )
        after = path.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (
            after.st_size, after.st_mtime_ns, after.st_ino,
        ):
            return None
        if info.signature != 0xFEEF04BD or info.file_type != 1:
            return None
        file = _version(info.file_ms, info.file_ls)
        product = _version(info.product_ms, info.product_ls)
        if file[:3] != product[:3]:
            return None
        if file[3] and product[3] and file != product:
            return None
        version = file if file[3] else product
        return version if version[:2] == (9, 9) and version[3] > 0 else None
    except Exception:
        # A failure to identify a version is neither a compatibility verdict
        # nor a launch failure. Never log the path or raw native exception.
        return None
