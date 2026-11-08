// OpenShao-ModKit.exe: opens the ModKit window without a console and shows a splash screen until the window is ready.
//
// It carries modkit.exe inside itself (see Prepare), starts it with the "gui" command and no console, and draws a splash on a transparent layered window: the interface's
// brush circle drawn in and then out again, the name, and "Starting" with three dots that appear and disappear in turn. modkit.exe tells it the
// window is up by setting the named event whose name is in MODKIT_READY; the splash then fades out and this program ends, leaving the ModKit running.
#define UNICODE
#define _UNICODE
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
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



// The ModKit is in this file, after the program, as a zip of its folder: [zip][SHA-256, 32 bytes][its size, 8 bytes][MKPAYLD1]. On the first run it is unpacked to
// %LOCALAPPDATA%\OpenShao\ModKit\<start of the hash>\ (the zip is checked against the hash first); later runs use that folder, which starts at once. A build with no payload
// (a development build) uses a modkit.exe beside this file.
constexpr size_t kTrailer = 48;

std::wstring Hex(const uint8_t* bytes, size_t n) {
    static const wchar_t digits[] = L"0123456789abcdef";
    std::wstring s;
    for (size_t i = 0; i < n; ++i) { s += digits[bytes[i] >> 4]; s += digits[bytes[i] & 15]; }
    return s;
}

bool ReadAt(HANDLE file, uint64_t offset, void* buffer, DWORD size) {
    LARGE_INTEGER at;
    at.QuadPart = LONGLONG(offset);
    DWORD got = 0;
    return SetFilePointerEx(file, at, nullptr, FILE_BEGIN) && ReadFile(file, buffer, size, &got, nullptr) && got == size;
}

bool FileSize(const std::wstring& path, uint64_t* size) {
    WIN32_FILE_ATTRIBUTE_DATA data;
    if (!GetFileAttributesExW(path.c_str(), GetFileExInfoStandard, &data)) return false;
    *size = (uint64_t(data.nFileSizeHigh) << 32) | data.nFileSizeLow;
    return true;
}

bool MakeFolder(const std::wstring& path) { return CreateDirectoryW(path.c_str(), nullptr) || GetLastError() == ERROR_ALREADY_EXISTS; }

struct Prepared {
    std::wstring program, error;
    volatile bool done = false;
};

// Copies the payload to `target` while hashing it; true when the hash is the one in the trailer.
bool Extract(HANDLE self, uint64_t offset, uint64_t size, const uint8_t* expected, const std::wstring& target) {
    HANDLE out = CreateFileW(target.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (out == INVALID_HANDLE_VALUE) return false;
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    bool ok = BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) == 0 && BCryptCreateHash(algorithm, &hash, nullptr, 0, nullptr, 0, 0) == 0;
    std::vector<uint8_t> block(4 << 20);
    for (uint64_t done = 0; ok && done < size;) {
        const DWORD n = DWORD(size - done < block.size() ? size - done : block.size());
        DWORD wrote = 0;
        ok = ReadAt(self, offset + done, block.data(), n) && BCryptHashData(hash, block.data(), n, 0) == 0 && WriteFile(out, block.data(), n, &wrote, nullptr) && wrote == n;
        done += n;
    }
    uint8_t digest[32] = {};
    if (ok) ok = BCryptFinishHash(hash, digest, 32, 0) == 0 && std::memcmp(digest, expected, 32) == 0;
    if (hash) BCryptDestroyHash(hash);
    if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0);
    CloseHandle(out);
    if (!ok) DeleteFileW(target.c_str());
    return ok;
}

// Deletes a folder and what is in it, as far as Windows allows (a file of a running program stays).
void RemoveTree(const std::wstring& folder) {
    WIN32_FIND_DATAW entry;
    HANDLE find = FindFirstFileW((folder + L"\\*").c_str(), &entry);
    if (find != INVALID_HANDLE_VALUE) {
        do {
            const std::wstring name = entry.cFileName;
            if (name == L"." || name == L"..") continue;
            const std::wstring path = folder + L"\\" + name;
            if (entry.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) RemoveTree(path);
            else { SetFileAttributesW(path.c_str(), FILE_ATTRIBUTE_NORMAL); DeleteFileW(path.c_str()); }
        } while (FindNextFileW(find, &entry));
        FindClose(find);
    }
    RemoveDirectoryW(folder.c_str());
}

// Unpacks a zip into a folder with the tar.exe that comes with Windows 10 and later; true when it succeeds.
bool Untar(const std::wstring& zip, const std::wstring& folder) {
    wchar_t system[MAX_PATH];
    if (!GetSystemDirectoryW(system, MAX_PATH)) return false;
    const std::wstring tar = std::wstring(system) + L"\\tar.exe";
    std::wstring command = L"\"" + tar + L"\" -xf \"" + zip + L"\" -C \"" + folder + L"\"";
    STARTUPINFOW startup = {sizeof(startup)};
    PROCESS_INFORMATION process = {};
    if (!CreateProcessW(tar.c_str(), &command[0], nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr, nullptr, &startup, &process)) return false;
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD code = 1;
    GetExitCodeProcess(process.hProcess, &code);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return code == 0;
}
DWORD WINAPI Prepare(LPVOID parameter) {
    Prepared& result = *static_cast<Prepared*>(parameter);
    wchar_t path[MAX_PATH * 4];
    const DWORD length = GetModuleFileNameW(nullptr, path, DWORD(sizeof(path) / sizeof(path[0])));
    const std::wstring self_path(path, length);
    const std::wstring folder = self_path.substr(0, self_path.find_last_of(L"\\/") + 1);
    HANDLE self = CreateFileW(self_path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    uint8_t trailer[kTrailer] = {};
    LARGE_INTEGER total = {};
    bool embedded = false;
    if (self != INVALID_HANDLE_VALUE && GetFileSizeEx(self, &total) && uint64_t(total.QuadPart) > kTrailer &&
        ReadAt(self, uint64_t(total.QuadPart) - kTrailer, trailer, kTrailer))
        embedded = std::memcmp(trailer + 40, "MKPAYLD1", 8) == 0;
    if (!embedded) {
        if (self != INVALID_HANDLE_VALUE) CloseHandle(self);
        result.program = folder + L"modkit\\modkit.exe";
        if (GetFileAttributesW(result.program.c_str()) == INVALID_FILE_ATTRIBUTES)
            result.error = L"This copy of OpenShao-ModKit.exe has no ModKit inside and the folder modkit was not found beside it.";
        result.done = true;
        return 0;
    }
    uint64_t size = 0;
    std::memcpy(&size, trailer + 32, 8);
    if (size == 0 || size > uint64_t(total.QuadPart) - kTrailer) {
        result.error = L"OpenShao-ModKit.exe is damaged. Download it again.";
    } else {
        wchar_t local[MAX_PATH];
        const DWORD n = GetEnvironmentVariableW(L"LOCALAPPDATA", local, MAX_PATH);
        const std::wstring root = n && n < MAX_PATH ? std::wstring(local) : folder;
        const std::wstring base = root + L"\\OpenShao", versions = base + L"\\ModKit";
        const std::wstring current = versions + L"\\" + Hex(trailer, 8), program = current + L"\\modkit.exe";
        // a folder is unpacked beside its final place and renamed, so a folder with modkit.exe in it is always a complete one
        if (GetFileAttributesW(program.c_str()) == INVALID_FILE_ATTRIBUTES) {
            const std::wstring stem = versions + L"\\unpack-" + std::to_wstring(GetCurrentProcessId());
            const std::wstring zip = stem + L".zip", part = stem;
            RemoveTree(part);
            if (!MakeFolder(base) || !MakeFolder(versions) || !MakeFolder(part))
                result.error = L"The ModKit could not be unpacked: the folder " + versions + L" could not be created.";
            else if (!Extract(self, uint64_t(total.QuadPart) - kTrailer - size, size, trailer, zip))
                result.error = L"The ModKit could not be unpacked to " + versions + L". There may be no space left, or OpenShao-ModKit.exe is damaged.";
            else if (!Untar(zip, part))
                result.error = L"The ModKit could not be unpacked: tar.exe, which comes with Windows 10 and later, failed or is missing.";
            else if (!MoveFileExW(part.c_str(), current.c_str(), 0) && GetFileAttributesW(program.c_str()) == INVALID_FILE_ATTRIBUTES)
                result.error = L"The ModKit could not be unpacked to " + current + L".";  // if another run won the rename, its folder is used
            DeleteFileW(zip.c_str());
            RemoveTree(part);
        }
        if (result.error.empty()) {
            result.program = program;
            WIN32_FIND_DATAW entry;  // older versions are removed (best effort: one that is running stays)
            HANDLE find = FindFirstFileW((versions + L"\\*").c_str(), &entry);
            if (find != INVALID_HANDLE_VALUE) {
                do {
                    const std::wstring name = entry.cFileName;
                    if (name == L"." || name == L".." || !(entry.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) || versions + L"\\" + name == current ||
                        name.compare(0, 7, L"unpack-") == 0)
                        continue;
                    RemoveTree(versions + L"\\" + name);
                } while (FindNextFileW(find, &entry));
                FindClose(find);
            }
        }
    }    CloseHandle(self);
    result.done = true;
    return 0;
}
}  // namespace

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    SetProcessDPIAware();
    const std::wstring name = L"OpenShaoModKitReady-" + std::to_wstring(GetCurrentProcessId());
    HANDLE ready = CreateEventW(nullptr, TRUE, FALSE, name.c_str());
    SetEnvironmentVariableW(L"MODKIT_READY", name.c_str());
    AllowSetForegroundWindow(ASFW_ANY);  // this program was started by the user, so it may let the ModKit window come to the front

    Prepared prepared;
    HANDLE worker = CreateThread(nullptr, 0, Prepare, &prepared, 0, nullptr);

    ULONG_PTR token = 0;
    Gdiplus::GdiplusStartupInput input;
    Gdiplus::GdiplusStartup(&token, &input, nullptr);
    int result = 0;
    PROCESS_INFORMATION child = {};
    {
        Splash splash;
        const bool shown = splash.Create();
        double fade_started = -1;
        bool started = false;
        for (;;) {
            MSG message;
            while (PeekMessageW(&message, nullptr, 0, 0, PM_REMOVE)) DispatchMessageW(&message);
            const double seconds = splash.Elapsed();
            if (!started && prepared.done) {
                if (!prepared.error.empty()) {
                    splash.Close();
                    MessageBoxW(nullptr, prepared.error.c_str(), L"OpenShao ModKit", MB_OK | MB_ICONERROR);
                    result = 1;
                    break;
                }
                std::wstring command = L"\"" + prepared.program + L"\" gui " + Arguments();
                STARTUPINFOW startup = {sizeof(startup)};
                const std::wstring folder = prepared.program.substr(0, prepared.program.find_last_of(L"\\/") + 1);
                if (!CreateProcessW(prepared.program.c_str(), &command[0], nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr, folder.c_str(), &startup, &child)) {
                    splash.Close();
                    MessageBoxW(nullptr, L"The ModKit could not be started.", L"OpenShao ModKit", MB_OK | MB_ICONERROR);
                    result = 1;
                    break;
                }
                started = true;
            }
            if (started && fade_started < 0) {
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
    WaitForSingleObject(worker, 5000);
    CloseHandle(worker);
    if (child.hProcess) {
        CloseHandle(child.hThread);
        CloseHandle(child.hProcess);
    }
    return result;
}