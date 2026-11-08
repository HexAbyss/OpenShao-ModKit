"""The native window's title bar colors and icon (Windows) and the signal to the launcher that the window is up (both systems). Every call is
best effort, because older Windows versions lack some of the attributes and the window is usable without them."""
import ctypes
import os
import sys

# the launcher's title bar
CAPTION = (0x25, 0x28, 0x2C)
CAPTION_TEXT = (0xEC, 0xE5, 0xD6)
ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.ico')


def signal_ready():
    """Tells the launcher (OpenShao-ModKit), which shows a splash screen, that the window is up. On Windows MODKIT_READY names an event; on
    Linux MODKIT_READY_FD is a pipe the launcher left open, and a byte is written to it."""
    if sys.platform != 'win32':
        descriptor = os.environ.pop('MODKIT_READY_FD', '')
        if descriptor.isdigit():
            try:
                os.write(int(descriptor), b'1')
                os.close(int(descriptor))
            except OSError:
                pass
        return
    name = os.environ.get('MODKIT_READY')
    if not name:
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
        center(hwnd)
    except Exception:
        pass


def center(hwnd):
    """Puts the window in the middle of the work area of the screen the user is on (the one with the active window)"""
    from ctypes import wintypes
    user32 = ctypes.windll.user32

    class Info(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT), ('work', wintypes.RECT), ('flags', wintypes.DWORD)]

    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    monitor = user32.MonitorFromWindow(user32.GetForegroundWindow() or hwnd, 2)  # MONITOR_DEFAULTTONEAREST
    info = Info(ctypes.sizeof(Info))
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Info)]
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    x = info.work.left + (info.work.right - info.work.left - w) // 2
    y = info.work.top + (info.work.bottom - info.work.top - h) // 2
    user32.SetWindowPos(hwnd, None, x, y, 0, 0, 0x15)  # SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE


def bring_to_front(title):
    """Puts the window above every other and gives it the focus. Windows lets only the foreground process do that, so the launcher allows it
    (AllowSetForegroundWindow) and the topmost flag is set and cleared as a second way to raise it."""
    if sys.platform != 'win32':
        return
    try:
        user32 = ctypes.windll.user32
        hwnd = _window(title)
        if not hwnd:
            return
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x13)  # HWND_TOPMOST; SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
        user32.SetWindowPos(hwnd, ctypes.c_void_p(-2), 0, 0, 0, 0, 0x03)  # HWND_NOTOPMOST; the window stays where it is in the order
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
