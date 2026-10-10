"""Windows version resources from synthetic buffers and fictional files only."""

import ctypes
import importlib
import importlib.util
import sys

import pytest


def _module():
    name = "qq_chat_analyzer.application.qq.qq_version"
    assert importlib.util.find_spec(name) is not None, "QQ executable version reader is missing"
    return importlib.import_module(name)


class _FixedInfo(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in (
        "signature", "structure_version", "file_ms", "file_ls", "product_ms",
        "product_ls", "flags_mask", "flags", "os", "file_type", "subtype", "date_ms", "date_ls",
    )]


class _Function:
    def __init__(self, call):
        self.call = call

    def __call__(self, *args):
        return self.call(*args)


class _VersionApi:
    def __init__(self, file_version=(9, 9, 15, 27597), product_version=None, fault=None):
        product_version = file_version if product_version is None else product_version
        self.info = _FixedInfo()
        self.info.signature = 0 if fault == "signature" else 0xFEEF04BD
        self.info.file_type = 1
        self.info.file_ms = (file_version[0] << 16) | file_version[1]
        self.info.file_ls = (file_version[2] << 16) | file_version[3]
        self.info.product_ms = (product_version[0] << 16) | product_version[1]
        self.info.product_ls = (product_version[2] << 16) | product_version[3]
        self.fault = fault
        self.paths = []
        self.GetFileVersionInfoSizeW = _Function(self.size)
        self.GetFileVersionInfoW = _Function(self.read)
        self.VerQueryValueW = _Function(self.query)

    def size(self, path, handle):
        self.paths.append(path)
        return 0 if self.fault == "size" else 80

    def read(self, path, handle, size, buffer):
        assert path == self.paths[0]
        assert handle == 0 and size == 80
        ctypes.memmove(ctypes.addressof(buffer) + 8, ctypes.byref(self.info), 52)
        return self.fault != "read"

    def query(self, buffer, key, pointer, length):
        assert key == "\\"
        address = ctypes.addressof(buffer) + 8
        if self.fault == "pointer":
            address = ctypes.addressof(buffer) + 80
        if self.fault == "null":
            address = 0
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p))[0] = address
        ctypes.cast(length, ctypes.POINTER(ctypes.c_uint))[0] = 1 if self.fault == "length" else 52
        return self.fault != "query"


def _read(tmp_path, monkeypatch, api):
    module = _module()
    path = tmp_path / "QQ.exe"
    path.write_bytes(b"fictional executable; no real QQ")
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module.ctypes, "WinDLL", lambda name, **kwargs: api, raising=False)
    result = module.read_qq_version(path)
    return result, path, api


@pytest.mark.parametrize("version", [(9, 9, 15, 27597), (9, 9, 36, 53644), (9, 9, 0, 40768)])
def test_reads_fixed_numeric_version_from_the_selected_executable(tmp_path, monkeypatch, version):
    result, path, api = _read(tmp_path, monkeypatch, _VersionApi(version))
    assert result == version
    assert api.paths == [str(path)]
    # Output pointers must be pointer-sized; WINAPI DWORDs remain 32 bits.
    assert api.GetFileVersionInfoSizeW.restype is ctypes.c_uint32
    assert api.GetFileVersionInfoW.argtypes[3] is ctypes.c_void_p
    assert api.VerQueryValueW.argtypes[2] is ctypes.POINTER(ctypes.c_void_p)


@pytest.mark.parametrize("fault", ["size", "read", "query", "length", "pointer", "null", "signature"])
def test_bad_api_results_are_unknown_and_never_dereferenced(tmp_path, monkeypatch, fault):
    result, _, _ = _read(tmp_path, monkeypatch, _VersionApi(fault=fault))
    assert result is None


@pytest.mark.parametrize("file,product,want", [
    ((9, 9, 15, 0), (9, 9, 15, 27597), (9, 9, 15, 27597)),
    ((9, 9, 15, 27597), (9, 9, 15, 0), (9, 9, 15, 27597)),
    ((9, 9, 15, 27597), (9, 9, 36, 53644), None),
    ((9, 9, 15, 27597), (9, 9, 15, 53644), None),
    ((9, 9, 15, 0), (9, 9, 15, 0), None),
    ((0, 0, 0, 0), (0, 0, 0, 0), None),
    ((8, 9, 15, 27597), (8, 9, 15, 27597), None),
])
def test_ambiguous_or_incomplete_metadata_cannot_be_a_build_gate(tmp_path, monkeypatch, file, product, want):
    result, _, _ = _read(tmp_path, monkeypatch, _VersionApi(file, product))
    assert result == want


def test_version_api_exception_is_unknown_and_never_logs_raw_error(tmp_path, monkeypatch, caplog):
    module = _module()
    path = tmp_path / "QQ.exe"
    path.write_bytes(b"fictional")
    monkeypatch.setattr(module.sys, "platform", "win32")

    def fail(*a, **k):
        raise OSError(f"{path} fictional-account fictional-secret")

    monkeypatch.setattr(module.ctypes, "WinDLL", fail, raising=False)
    assert module.read_qq_version(path) is None
    assert str(path) not in caplog.text
    assert "fictional-secret" not in caplog.text


def test_missing_file_is_unknown_without_querying_another_install(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setattr(module.ctypes, "WinDLL", lambda *a, **k: pytest.fail("missing file must not query API"), raising=False)
    assert module.read_qq_version(tmp_path / "QQ.exe") is None


def test_non_windows_is_unknown(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setattr(module.sys, "platform", "linux")
    assert module.read_qq_version(tmp_path / "QQ.exe") is None


def test_executable_changed_during_read_is_unknown(tmp_path, monkeypatch):
    module = _module()
    path = tmp_path / "QQ.exe"
    path.write_bytes(b"fictional original")
    api = _VersionApi()
    original_read = api.read

    def changed(*args):
        result = original_read(*args)
        path.write_bytes(b"fictional replacement with different size")
        return result

    api.GetFileVersionInfoW = _Function(changed)
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module.ctypes, "WinDLL", lambda *a, **k: api, raising=False)
    assert module.read_qq_version(path) is None


def test_corrupt_resource_size_is_unknown_without_allocation(tmp_path, monkeypatch):
    api = _VersionApi()
    api.GetFileVersionInfoSizeW = _Function(lambda *a: 0xFFFFFFFF)
    api.GetFileVersionInfoW = _Function(lambda *a: pytest.fail("must not read oversized resource"))
    result, _, _ = _read(tmp_path, monkeypatch, api)
    assert result is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows version.dll required")
def test_real_windows_api_rejects_fictional_file_without_version_resource(tmp_path):
    path = tmp_path / "QQ.exe"
    path.write_bytes(b"fictional file without any PE or version resource")
    assert _module().read_qq_version(path) is None
