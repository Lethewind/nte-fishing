import ctypes

from src.tray import _configure_call_next_hook


def test_call_next_hook_uses_pointer_sized_lparam():
    function = ctypes.CFUNCTYPE(
        ctypes.c_ssize_t,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.c_ssize_t,
    )(lambda _hook, _code, _message, pointer: pointer)

    configured = _configure_call_next_hook(function)

    assert configured.restype is ctypes.c_ssize_t
    assert configured.argtypes[-1] is ctypes.c_ssize_t
