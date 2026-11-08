"""The look of the native window on Windows: title bar colors and icon. Every call is best effort, because older Windows versions lack some of
the attributes and the window is usable without them."""
import ctypes
import os
import sys

# the launcher's title bar
CAPTION = (0x25, 0x28, 0x2C)
CAPTION_TEXT = (0xEC, 0xE5, 0xD6)
ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.ico')


def signal_ready():
    """Tells the launcher (OpenShao-ModKit.exe), which shows a splash screen, that the window is up. It names an event in MODKIT_READY."""
    name = os.environ.get('MODKIT_READY')
    if sys.platform != 'win32' or not name:
        return
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenEventW.restype = ctypes.c_void_p
        event = kernel32.OpenEventW(0x0002, False, name)  # EVENT_MODIFY_STATE
        if event:
            kernel32.SetEvent(ctypes.c_void_p(event))
            kernel32.CloseHandle(ctypes.c_void_p(event))
    except Exception:
        pass


def _window(title):
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd, _):
        buffer = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buffer, 256)
        if buffer.value == title:
            found.append(hwnd)
        return True

    user32.EnumThreadWindows(ctypes.windll.kernel32.GetCurrentThreadId(), callback_type(visit), 0)
    return found[0] if found else None


def style(title):
    if sys.platform != 'win32':
        return
    try:
        from ctypes import wintypes
        hwnd = _window(title)
        if not hwnd:
            return
        dwm, user32 = ctypes.windll.dwmapi, ctypes.windll.user32
        for attribute, value in ((20, 1), (35, CAPTION[0] | CAPTION[1] << 8 | CAPTION[2] << 16),
                                 (36, CAPTION_TEXT[0] | CAPTION_TEXT[1] << 8 | CAPTION_TEXT[2] << 16)):
            number = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(number), ctypes.sizeof(number))
        user32.LoadImageW.restype = wintypes.HANDLE
        for kind, metric_x, metric_y in ((1, 11, 12), (0, 49, 50)):  # ICON_BIG, ICON_SMALL: the system's sizes for each
            icon = user32.LoadImageW(None, ICON, 1, user32.GetSystemMetrics(metric_x), user32.GetSystemMetrics(metric_y), 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
            if icon:
                user32.SendMessageW(hwnd, 0x80, kind, icon)  # WM_SETICON
        # the title bar is repainted with the new colors
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x27)  # SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED
    except Exception:
        pass
