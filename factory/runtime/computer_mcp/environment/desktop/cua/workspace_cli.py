#!/usr/bin/python3
"""Launch the desktop workspace shell without access to live service sockets."""

import ctypes
import errno
import os
import resource


def restrict_process():
    lib = ctypes.CDLL("libseccomp.so.2")
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    context = lib.seccomp_init(0x7FFF0000)  # Allow normal local file and process operations.
    if not context:
        raise SystemExit("Cannot initialize the workspace CLI filter")
    try:
        for name in (b"socket", b"socketpair", b"io_uring_setup", b"pidfd_getfd"):
            syscall = lib.seccomp_syscall_resolve_name(name)
            if syscall >= 0 and lib.seccomp_rule_add(context, 0x00050000 | errno.EPERM, syscall, 0):
                raise SystemExit(f"Cannot restrict {name.decode()}")
        if lib.seccomp_load(context):
            raise SystemExit("Cannot restrict the workspace CLI")
    finally:
        lib.seccomp_release(context)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def main():
    if os.geteuid() == 0:
        raise SystemExit("The workspace CLI requires an unprivileged user")
    restrict_process()
    os.chdir("/workspace")
    os.umask(0o002)
    env = {
        "HOME": os.environ["HOME"], "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
        "TERM": os.environ.get("TERM", "xterm-256color"), "PS1": "workspace$ ",
    }
    os.execve("/bin/bash", ["bash", "--noprofile", "--norc", "-i"], env)


if __name__ == "__main__":
    main()
