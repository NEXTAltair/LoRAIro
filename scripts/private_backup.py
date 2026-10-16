"""Create user-only migration backups before any sensitive bytes are written."""

from __future__ import annotations

import ctypes
import os
import stat
from ctypes import wintypes
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO


class _SecurityAttributes(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.DWORD),
        ("descriptor", wintypes.LPVOID),
        ("inherit_handle", wintypes.BOOL),
    ]


class _AclSize(ctypes.Structure):
    _fields_ = [("count", wintypes.DWORD), ("used", wintypes.DWORD), ("free", wintypes.DWORD)]


class _WindowsSecurity:
    """Apply a protected current-user DACL atomically, including on Python 3.12.0."""

    def __init__(self):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.security = ctypes.WinDLL("advapi32", use_last_error=True)
        pointer = ctypes.POINTER
        signatures = (
            (self.kernel.GetCurrentProcess, [], wintypes.HANDLE),
            (self.kernel.CloseHandle, [wintypes.HANDLE], wintypes.BOOL),
            (self.kernel.LocalFree, [wintypes.LPVOID], wintypes.LPVOID),
            (
                self.kernel.CreateDirectoryW,
                [wintypes.LPCWSTR, pointer(_SecurityAttributes)],
                wintypes.BOOL,
            ),
            (
                self.kernel.CreateFileW,
                [
                    wintypes.LPCWSTR,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    pointer(_SecurityAttributes),
                    wintypes.DWORD,
                    wintypes.DWORD,
                    wintypes.HANDLE,
                ],
                wintypes.HANDLE,
            ),
            (
                self.security.OpenProcessToken,
                [wintypes.HANDLE, wintypes.DWORD, pointer(wintypes.HANDLE)],
                wintypes.BOOL,
            ),
            (
                self.security.GetTokenInformation,
                [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, pointer(wintypes.DWORD)],
                wintypes.BOOL,
            ),
            (
                self.security.ConvertSidToStringSidW,
                [wintypes.LPVOID, pointer(wintypes.LPWSTR)],
                wintypes.BOOL,
            ),
            (
                self.security.ConvertStringSecurityDescriptorToSecurityDescriptorW,
                [wintypes.LPCWSTR, wintypes.DWORD, pointer(wintypes.LPVOID), pointer(wintypes.DWORD)],
                wintypes.BOOL,
            ),
            (
                self.security.GetSecurityInfo,
                [
                    wintypes.HANDLE,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    pointer(wintypes.LPVOID),
                    pointer(wintypes.LPVOID),
                    pointer(wintypes.LPVOID),
                    pointer(wintypes.LPVOID),
                    pointer(wintypes.LPVOID),
                ],
                wintypes.DWORD,
            ),
            (
                self.security.GetSecurityDescriptorControl,
                [wintypes.LPVOID, pointer(wintypes.WORD), pointer(wintypes.DWORD)],
                wintypes.BOOL,
            ),
            (
                self.security.GetAclInformation,
                [wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD],
                wintypes.BOOL,
            ),
            (
                self.security.GetAce,
                [wintypes.LPVOID, wintypes.DWORD, pointer(wintypes.LPVOID)],
                wintypes.BOOL,
            ),
            (self.security.EqualSid, [wintypes.LPVOID, wintypes.LPVOID], wintypes.BOOL),
        )
        for function, arguments, result in signatures:
            function.argtypes = arguments
            function.restype = result
        token = wintypes.HANDLE()
        self.check(
            self.security.OpenProcessToken(self.kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token))
        )
        try:
            size = wintypes.DWORD()
            self.security.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            self.token_user = ctypes.create_string_buffer(size.value)
            self.check(
                self.security.GetTokenInformation(token, 1, self.token_user, size, ctypes.byref(size))
            )
        finally:
            self.kernel.CloseHandle(token)
        self.sid = ctypes.c_void_p.from_buffer(self.token_user).value
        sid_text = wintypes.LPWSTR()
        self.check(self.security.ConvertSidToStringSidW(self.sid, ctypes.byref(sid_text)))
        try:
            self.sid_text = sid_text.value
        finally:
            self.kernel.LocalFree(ctypes.cast(sid_text, wintypes.LPVOID))

    @staticmethod
    def check(success):
        if not success:
            raise ctypes.WinError(ctypes.get_last_error())

    def create(self, path: Path, *, directory: bool):
        flags = "OICI" if directory else ""
        descriptor = wintypes.LPVOID()
        self.check(
            self.security.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                f"O:{self.sid_text}D:P(A;{flags};FA;;;{self.sid_text})", 1, ctypes.byref(descriptor), None
            )
        )
        attributes = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), descriptor, False)
        try:
            if directory:
                self.check(self.kernel.CreateDirectoryW(str(path), ctypes.byref(attributes)))
                self.verify_directory(path)
                return None
            # CREATE_NEW refuses existing files/links; zero sharing prevents another writer.
            handle = self.kernel.CreateFileW(
                str(path), 0x40000000 | 0x00020000, 0, ctypes.byref(attributes), 1, 0x80, None
            )
            if handle == ctypes.c_void_p(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                self.verify_handle(handle, directory=False)
                import msvcrt

                descriptor_fd = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
            except BaseException:
                self.kernel.CloseHandle(handle)
                raise
            # open_osfhandle transfers HANDLE ownership to the CRT descriptor.
            return descriptor_fd
        finally:
            self.kernel.LocalFree(descriptor)

    def verify_directory(self, path: Path) -> None:
        handle = self.kernel.CreateFileW(str(path), 0x00020000, 7, None, 3, 0x02000000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            self.verify_handle(handle, directory=True)
        finally:
            self.kernel.CloseHandle(handle)

    def verify_handle(self, handle, *, directory: bool) -> None:
        owner, dacl, descriptor = wintypes.LPVOID(), wintypes.LPVOID(), wintypes.LPVOID()
        error = self.security.GetSecurityInfo(
            handle, 1, 1 | 4, ctypes.byref(owner), None, ctypes.byref(dacl), None, ctypes.byref(descriptor)
        )
        if error:
            raise ctypes.WinError(error)
        try:
            control, revision, size = wintypes.WORD(), wintypes.DWORD(), _AclSize()
            self.check(
                self.security.GetSecurityDescriptorControl(
                    descriptor, ctypes.byref(control), ctypes.byref(revision)
                )
            )
            # A filesystem which ignores Windows security descriptors fails closed here.
            if (
                not owner
                or not self.security.EqualSid(owner, self.sid)
                or not control.value & 0x1000
                or not dacl
            ):
                raise PermissionError("Backup requires a protected current-user Windows DACL")
            self.check(self.security.GetAclInformation(dacl, ctypes.byref(size), ctypes.sizeof(size), 2))
            if size.count != 1:
                raise PermissionError("Backup DACL must grant access only to the current user")
            ace = wintypes.LPVOID()
            self.check(self.security.GetAce(dacl, 0, ctypes.byref(ace)))
            ace_type = ctypes.c_ubyte.from_address(ace.value).value
            ace_flags = ctypes.c_ubyte.from_address(ace.value + 1).value
            access = wintypes.DWORD.from_address(ace.value + 4).value
            if (
                ace_type != 0
                or ace_flags != (3 if directory else 0)
                or access != 0x001F01FF
                or not self.security.EqualSid(ace.value + 8, self.sid)
            ):
                raise PermissionError("Backup DACL must explicitly grant current-user full control")
        finally:
            self.kernel.LocalFree(descriptor)


@lru_cache(maxsize=1)
def _windows_security() -> _WindowsSecurity:
    return _WindowsSecurity()


def validate_private_directory(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise PermissionError("Backup directory must be a regular directory, not a filesystem link")
    if os.name == "nt":
        _windows_security().verify_directory(path)
    elif info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise PermissionError("Backup directory must belong to the current user with mode 0700")


def create_private_directory(path: Path) -> None:
    """Create a new protected leaf; preserve every existing destination."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        _windows_security().create(path, directory=True)
    else:
        path.mkdir(mode=0o700)
        path.chmod(0o700)
        validate_private_directory(path)


def open_private_file(path: Path) -> BinaryIO:
    """Create an exclusive protected binary stream before passing it to a writer."""
    validate_private_directory(path.parent)
    if os.name == "nt":
        descriptor = _windows_security().create(path, directory=False)
    else:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
        except BaseException:
            os.close(descriptor)
            raise
    try:
        return os.fdopen(descriptor, "wb")
    except BaseException:
        os.close(descriptor)
        raise
