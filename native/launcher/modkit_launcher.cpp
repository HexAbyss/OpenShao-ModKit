// OpenShao-ModKit.exe: opens the ModKit window without a console and shows a splash screen until the window is ready.
//
// It starts modkit.exe (beside it) with the "gui" command and no console, and draws a splash on a transparent layered window: the interface's
// brush circle drawn in and then out again, the name, and "Starting" with three dots that appear and disappear in turn. modkit.exe tells it the
// window is up by setting the named event whose name is in MODKIT_READY; the splash then fades out and this program ends, leaving the ModKit running.
#define UNICODE
#define _UNICODE
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <objidl.h>
#include <gdiplus.h>

#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

namespace {

constexpr int kRing = 100, kFontRegular = 101, kFontSemiBold = 102;
constexpr int kWidth = 360, kHeight = 330;       // of the splash, in logical pixels
constexpr double kPhase = 1.0;                  // seconds to draw the circle in, and the same to draw it out
constexpr double kDotsCycle = 2.0;
constexpr double kFadeOut = 0.25;
constexpr double kGiveUp = 180.0;                // seconds without a signal after which the splash goes away anyway

struct Resource {
    const uint8_t* data = nullptr;
    DWORD size = 0;
};

Resource Load(int id) {
    Resource r;
    HRSRC found = FindResourceW(nullptr, MAKEINTRESOURCEW(id), RT_RCDATA);
    if (!found) return r;
    HGLOBAL loaded = LoadResource(nullptr, found);
    if (!loaded) return r;
    r.data = static_cast<const uint8_t*>(LockResource(loaded));
    r.size = SizeofResource(nullptr, found);
    return r;
}

double Smooth(double a, double b, double x) {
    double t = (x - a) / (b - a);
    t = t < 0 ? 0 : (t > 1 ? 1 : t);
    return t * t * (3 - 2 * t);
}

double Clamp01(double x) { return x < 0 ? 0 : (x > 1 ? 1 : x); }

// Slightly eased, so the stroke never stops: it only slows a little where it starts and ends.
double Ease(double p) { return 0.6 * p + 0.4 * (0.5 - 0.5 * std::cos(3.14159265358979 * p)); }

double Now() {
    static LARGE_INTEGER frequency = [] { LARGE_INTEGER f; QueryPerformanceFrequency(&f); return f; }();
    LARGE_INTEGER t;
    QueryPerformanceCounter(&t);
    return double(t.QuadPart) / double(frequency.QuadPart);
}

class Splash {
public:
    bool Create() {
        Resource ring = Load(kRing);
        if (ring.size < 8) return false;
        std::memcpy(&ring_w_, ring.data, 4);
        std::memcpy(&ring_h_, ring.data + 4, 4);
        const size_t pixels = size_t(ring_w_) * ring_h_;
        if (ring.size < 8 + pixels * 5) return false;
        rgba_ = ring.data + 8;
        along_ = ring.data + 8 + pixels * 4;
        premultiplied_.resize(pixels * 4);

        HDC screen = GetDC(nullptr);
        const int dpi = GetDeviceCaps(screen, LOGPIXELSX);
        scale_ = dpi / 96.0;
        width_ = int(kWidth * scale_ + 0.5);
        height_ = int(kHeight * scale_ + 0.5);

        BITMAPINFO info = {};
        info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
        info.bmiHeader.biWidth = width_;
        info.bmiHeader.biHeight = -height_;
        info.bmiHeader.biPlanes = 1;
        info.bmiHeader.biBitCount = 32;
        info.bmiHeader.biCompression = BI_RGB;
        memory_ = CreateCompatibleDC(screen);
        dib_ = CreateDIBSection(memory_, &info, DIB_RGB_COLORS, &bits_, nullptr, 0);
        ReleaseDC(nullptr, screen);
        if (!dib_) return false;
        SelectObject(memory_, dib_);

        canvas_ = new Gdiplus::Bitmap(width_, height_, PixelFormat32bppPARGB);
        Resource regular = Load(kFontRegular), semibold = Load(kFontSemiBold);
        if (regular.data) regular_fonts_.AddMemoryFont(regular.data, regular.size);
        if (semibold.data) semibold_fonts_.AddMemoryFont(semibold.data, semibold.size);

        WNDCLASSW wc = {};
        wc.lpfnWndProc = DefWindowProcW;
        wc.hInstance = GetModuleHandleW(nullptr);
        wc.lpszClassName = L"OpenShaoModKitSplash";
        RegisterClassW(&wc);
        RECT work;
        SystemParametersInfoW(SPI_GETWORKAREA, 0, &work, 0);
        x_ = work.left + (work.right - work.left - width_) / 2;
        y_ = work.top + (work.bottom - work.top - height_) / 2;
        window_ = CreateWindowExW(WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT, wc.lpszClassName,
                                  L"OpenShao ModKit", WS_POPUP, x_, y_, width_, height_, nullptr, nullptr, wc.hInstance, nullptr);
        if (!window_) return false;
        start_ = Now();
        Draw(0.0, 1.0);
        ShowWindow(window_, SW_SHOWNOACTIVATE);
        return true;
    }

    // `seconds` since the start, `opacity` of the whole splash (below 1 while it fades out)
    void Draw(double seconds, double opacity) {
        RenderRing(seconds);
        Gdiplus::Graphics g(canvas_);
        g.SetSmoothingMode(Gdiplus::SmoothingModeHighQuality);
        g.SetInterpolationMode(Gdiplus::InterpolationModeHighQualityBicubic);
        g.SetPixelOffsetMode(Gdiplus::PixelOffsetModeHighQuality);
        g.SetTextRenderingHint(Gdiplus::TextRenderingHintAntiAlias);
        g.Clear(Gdiplus::Color(0, 0, 0, 0));

        const float ring_side = float(226 * scale_ * 0.98);
        const float ring_x = (width_ - ring_side) / 2, ring_y = float(8 * scale_);
        Gdiplus::Bitmap ring(ring_w_, ring_h_, ring_w_ * 4, PixelFormat32bppPARGB, premultiplied_.data());
        g.DrawImage(&ring, Gdiplus::RectF(ring_x, ring_y, ring_side, ring_side), 0, 0, float(ring_w_), float(ring_h_), Gdiplus::UnitPixel);

        Gdiplus::FontFamily title_family, text_family;
        INT found = 0;
        const bool have_title = semibold_fonts_.GetFamilyCount() > 0 && (semibold_fonts_.GetFamilies(1, &title_family, &found), found > 0);
        found = 0;
        const bool have_text = regular_fonts_.GetFamilyCount() > 0 && (regular_fonts_.GetFamilies(1, &text_family, &found), found > 0);
        Gdiplus::FontFamily fallback(L"Segoe UI");
        Gdiplus::Font title_font(have_title ? &title_family : &fallback, float(28 * scale_), Gdiplus::FontStyleRegular, Gdiplus::UnitPixel);
        Gdiplus::Font text_font(have_text ? &text_family : &fallback, float(20 * scale_), Gdiplus::FontStyleRegular, Gdiplus::UnitPixel);
        Gdiplus::StringFormat center;
        center.SetAlignment(Gdiplus::StringAlignmentCenter);
        Gdiplus::StringFormat near_edge(Gdiplus::StringFormat::GenericTypographic());  // no padding around the text, so the dots sit against the word
        near_edge.SetAlignment(Gdiplus::StringAlignmentNear);

        // a soft dark edge keeps the light text readable on any desktop
        const auto text = [&](const wchar_t* s, const Gdiplus::Font& font, const Gdiplus::RectF& box, const Gdiplus::StringFormat& format,
                              BYTE r, BYTE gr, BYTE b, double alpha) {
            for (int i = 0; i < 3; ++i) {
                const float d = float((1 + i) * scale_ * 0.8);
                Gdiplus::SolidBrush shadow(Gdiplus::Color(BYTE(120 * alpha / (1 + i)), 0, 0, 0));
                g.DrawString(s, -1, &font, Gdiplus::RectF(box.X, box.Y + d, box.Width, box.Height), &format, &shadow);
            }
            Gdiplus::SolidBrush brush(Gdiplus::Color(BYTE(255 * alpha), r, gr, b));
            g.DrawString(s, -1, &font, box, &format, &brush);
        };
        const float title_y = ring_y + ring_side + float(6 * scale_);
        text(L"OpenShao ModKit", title_font, Gdiplus::RectF(0, title_y, float(width_), float(40 * scale_)), center, 0xEC, 0xE5, 0xD6, 1.0);

        // "Starting" with its dots at fixed places, so the word does not move while they come and go
        Gdiplus::RectF word_size;
        g.MeasureString(L"Starting", -1, &text_font, Gdiplus::PointF(0, 0), &near_edge, &word_size);
        Gdiplus::RectF dot_size;
        g.MeasureString(L"...", -1, &text_font, Gdiplus::PointF(0, 0), &near_edge, &dot_size);
        const float dot_w = dot_size.Width / 3.0f;
        const float line_x = (width_ - (word_size.Width + dot_w * 3)) / 2, line_y = title_y + float(44 * scale_);
        text(L"Starting", text_font, Gdiplus::RectF(line_x, line_y, word_size.Width + 10, float(30 * scale_)), near_edge, 0xA9, 0xA4, 0x98, 1.0);
        const double phase = std::fmod(seconds, kDotsCycle);
        for (int i = 0; i < 3; ++i) {
            const double on = Clamp01((phase - 0.22 * i) / 0.25) - Clamp01((phase - (1.25 + 0.22 * i)) / 0.25);
            if (on > 0.01)
                text(L".", text_font, Gdiplus::RectF(line_x + word_size.Width + float(1 * scale_) + dot_w * i, line_y, dot_w * 2, float(30 * scale_)), near_edge,
                     0xA9, 0xA4, 0x98, on);
        }

        Gdiplus::BitmapData data;
        const Gdiplus::Rect whole(0, 0, width_, height_);
        if (canvas_->LockBits(&whole, Gdiplus::ImageLockModeRead, PixelFormat32bppPARGB, &data) == Gdiplus::Ok) {
            for (int row = 0; row < height_; ++row)
                std::memcpy(static_cast<uint8_t*>(bits_) + size_t(row) * width_ * 4, static_cast<const uint8_t*>(data.Scan0) + size_t(row) * data.Stride,
                            size_t(width_) * 4);
            canvas_->UnlockBits(&data);
        }
        POINT position = {x_, y_}, origin = {0, 0};
        SIZE size = {width_, height_};
        BLENDFUNCTION blend = {AC_SRC_OVER, 0, BYTE(255 * Clamp01(opacity) + 0.5), AC_SRC_ALPHA};
        UpdateLayeredWindow(window_, nullptr, &position, &size, memory_, &origin, 0, &blend, ULW_ALPHA);
    }

    double Elapsed() const { return Now() - start_; }

    void Close() {
        if (window_) DestroyWindow(window_);
        window_ = nullptr;
    }

private:
    // The circle is drawn in over one phase and drawn out over the next, then again: the same mask the interface uses for its progress,
    // moving along the stroke, so the end of a phase is the start of the other.
    void RenderRing(double seconds) {
        const double cycle = std::fmod(seconds, 2 * kPhase);
        const bool drawing_in = cycle < kPhase;
        const double progress = Ease(Clamp01((drawing_in ? cycle : cycle - kPhase) / kPhase));
        const double limit = progress * 1.04;
        const size_t pixels = size_t(ring_w_) * ring_h_;
        for (size_t i = 0; i < pixels; ++i) {
            const double t = along_[i] / 255.0;
            const double reach = Smooth(limit - 0.035, limit, t);
            const double visible = drawing_in ? 1.0 - reach : reach;
            const uint8_t* p = rgba_ + i * 4;
            const double alpha = p[3] / 255.0 * visible;
            uint8_t* out = premultiplied_.data() + i * 4;
            out[0] = uint8_t(p[2] * alpha + 0.5);  // BGRA, premultiplied
            out[1] = uint8_t(p[1] * alpha + 0.5);
            out[2] = uint8_t(p[0] * alpha + 0.5);
            out[3] = uint8_t(255 * alpha + 0.5);
        }
    }

    uint32_t ring_w_ = 0, ring_h_ = 0;
    const uint8_t* rgba_ = nullptr;
    const uint8_t* along_ = nullptr;
    std::vector<uint8_t> premultiplied_;
    double scale_ = 1.0, start_ = 0.0;
    int width_ = 0, height_ = 0, x_ = 0, y_ = 0;
    HWND window_ = nullptr;
    HDC memory_ = nullptr;
    HBITMAP dib_ = nullptr;
    void* bits_ = nullptr;
    Gdiplus::Bitmap* canvas_ = nullptr;
    Gdiplus::PrivateFontCollection regular_fonts_, semibold_fonts_;
};

std::wstring Directory() {
    wchar_t path[MAX_PATH * 4];
    DWORD n = GetModuleFileNameW(nullptr, path, DWORD(sizeof(path) / sizeof(path[0])));
    std::wstring full(path, n);
    return full.substr(0, full.find_last_of(L"\\/") + 1);
}

// The arguments given to this program, to pass on after "gui"
std::wstring Arguments() {
    const wchar_t* line = GetCommandLineW();
    bool quoted = false;
    if (*line == L'"') { quoted = true; ++line; }
    while (*line && (quoted ? *line != L'"' : *line != L' ')) ++line;
    if (quoted && *line) ++line;
    while (*line == L' ') ++line;
    return line;
}

}  // namespace

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    SetProcessDPIAware();
    const std::wstring program = Directory() + L"modkit.exe";
    if (GetFileAttributesW(program.c_str()) == INVALID_FILE_ATTRIBUTES) {
        MessageBoxW(nullptr, L"modkit.exe was not found beside OpenShao-ModKit.exe. Keep the two files in the same folder.", L"OpenShao ModKit",
                    MB_OK | MB_ICONERROR);
        return 1;
    }
    const std::wstring name = L"OpenShaoModKitReady-" + std::to_wstring(GetCurrentProcessId());
    HANDLE ready = CreateEventW(nullptr, TRUE, FALSE, name.c_str());
    SetEnvironmentVariableW(L"MODKIT_READY", name.c_str());

    std::wstring command = L"\"" + program + L"\" gui " + Arguments();
    STARTUPINFOW startup = {sizeof(startup)};
    PROCESS_INFORMATION child = {};
    if (!CreateProcessW(program.c_str(), &command[0], nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr, Directory().c_str(), &startup, &child)) {
        MessageBoxW(nullptr, L"modkit.exe could not be started.", L"OpenShao ModKit", MB_OK | MB_ICONERROR);
        return 1;
    }

    AllowSetForegroundWindow(ASFW_ANY);  // this program was started by the user, so it may let the ModKit window come to the front

    ULONG_PTR token = 0;
    Gdiplus::GdiplusStartupInput input;
    Gdiplus::GdiplusStartup(&token, &input, nullptr);
    int result = 0;
    {
        Splash splash;
        const bool shown = splash.Create();
        double fade_started = -1;
        for (;;) {
            MSG message;
            while (PeekMessageW(&message, nullptr, 0, 0, PM_REMOVE)) DispatchMessageW(&message);
            const double seconds = splash.Elapsed();
            if (fade_started < 0) {
                if (WaitForSingleObject(ready, 0) == WAIT_OBJECT_0 || seconds > kGiveUp) {
                    fade_started = seconds;
                } else if (WaitForSingleObject(child.hProcess, 0) == WAIT_OBJECT_0) {
                    DWORD code = 0;
                    GetExitCodeProcess(child.hProcess, &code);
                    splash.Close();
                    const std::wstring text = L"OpenShao ModKit closed before it opened (code " + std::to_wstring(code) +
                                              L"). Run \"modkit.exe gui\" in a terminal to see why.";
                    MessageBoxW(nullptr, text.c_str(), L"OpenShao ModKit", MB_OK | MB_ICONERROR);
                    result = 1;
                    break;
                }
            }
            double opacity = 1.0;
            if (fade_started >= 0) {
                opacity = 1.0 - (seconds - fade_started) / kFadeOut;
                if (opacity <= 0) break;
            }
            if (shown) splash.Draw(seconds, opacity);
            Sleep(12);
        }
        splash.Close();
    }
    Gdiplus::GdiplusShutdown(token);
    CloseHandle(child.hThread);
    CloseHandle(child.hProcess);
    return result;
}
