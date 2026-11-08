// OpenShao-ModKit (Linux): opens the ModKit window and shows a splash screen until the window is ready.
//
// It carries the ModKit inside itself (see Prepare), starts it with the "gui" command, and draws a splash on a transparent window: the interface's
// brush circle drawn in and then out again, the name, and "Starting" with three dots that appear and disappear in turn. The ModKit tells it the window
// is up by writing a byte to the pipe whose descriptor is in MODKIT_READY_FD; the splash then fades out and this program ends, leaving the ModKit
// running. A command of the ModKit (extract, compile, ...) given as the first argument runs that command in the terminal instead, with no splash.
//
// Xlib and Xfixes are loaded when the program starts, so a system without them (no display) still runs the commands. The splash needs a compositing
// window manager for its transparency; without one it is not shown.
#include <X11/Xatom.h>
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/extensions/Xfixes.h>
#include <X11/extensions/Xrandr.h>
#include <X11/extensions/shape.h>
#include <dirent.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <ftw.h>
#include <poll.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include <algorithm>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <string>
#include <thread>
#include <vector>

// The splash's pictures (packaging/linux/make_splash_assets.py), included in the program by the assembler.
__asm__(".section .rodata\n.balign 16\n.global kAssets\nkAssets:\n.incbin \"" MODKIT_ASSETS "\"\n.global kAssetsEnd\nkAssetsEnd:\n.byte 0\n.previous\n");
extern "C" const unsigned char kAssets[];
extern "C" const unsigned char kAssetsEnd[];

namespace {

constexpr int kWidth = 360, kHeight = 330;  // of the splash, in logical pixels
constexpr int kCompose = 2;                 // the pictures are drawn at this many times the logical size, then resampled to the screen's
constexpr double kPhase = 1.0;              // seconds to draw the circle in, and the same to draw it out
constexpr double kDotsCycle = 2.0;
constexpr double kFadeOut = 0.25;
constexpr double kGiveUp = 180.0;           // seconds without a signal after which the splash goes away anyway

double Smooth(double a, double b, double x) {
    double t = (x - a) / (b - a);
    t = t < 0 ? 0 : (t > 1 ? 1 : t);
    return t * t * (3 - 2 * t);
}
double Clamp01(double x) { return x < 0 ? 0 : (x > 1 ? 1 : x); }
// Slightly eased, so the stroke never stops: it only slows a little where it starts and ends.
double Ease(double p) { return 0.6 * p + 0.4 * (0.5 - 0.5 * std::cos(3.14159265358979 * p)); }

double Now() {
    using namespace std::chrono;
    return duration<double>(steady_clock::now().time_since_epoch()).count();
}

// ---- SHA-256 ----
struct Sha256 {
    uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    uint8_t block[64];
    size_t used = 0;
    uint64_t total = 0;

    static uint32_t Rotate(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }
    void Compress(const uint8_t* p) {
        static const uint32_t k[64] = {
            0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be,
            0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa,
            0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85,
            0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
            0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f,
            0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
        uint32_t w[64];
        for (int i = 0; i < 16; ++i) w[i] = uint32_t(p[i * 4]) << 24 | uint32_t(p[i * 4 + 1]) << 16 | uint32_t(p[i * 4 + 2]) << 8 | p[i * 4 + 3];
        for (int i = 16; i < 64; ++i) {
            const uint32_t s0 = Rotate(w[i - 15], 7) ^ Rotate(w[i - 15], 18) ^ (w[i - 15] >> 3);
            const uint32_t s1 = Rotate(w[i - 2], 17) ^ Rotate(w[i - 2], 19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16] + s0 + w[i - 7] + s1;
        }
        uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
        for (int i = 0; i < 64; ++i) {
            const uint32_t s1 = Rotate(e, 6) ^ Rotate(e, 11) ^ Rotate(e, 25), ch = (e & f) ^ (~e & g);
            const uint32_t t1 = hh + s1 + ch + k[i] + w[i];
            const uint32_t s0 = Rotate(a, 2) ^ Rotate(a, 13) ^ Rotate(a, 22), maj = (a & b) ^ (a & c) ^ (b & c);
            const uint32_t t2 = s0 + maj;
            hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
        }
        h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
    }
    void Update(const uint8_t* data, size_t n) {
        total += n;
        while (n) {
            const size_t take = std::min(n, sizeof(block) - used);
            std::memcpy(block + used, data, take);
            used += take; data += take; n -= take;
            if (used == sizeof(block)) { Compress(block); used = 0; }
        }
    }
    void Finish(uint8_t out[32]) {
        const uint64_t bits = total * 8;
        const uint8_t one = 0x80, zero = 0;
        Update(&one, 1);
        while (used != 56) Update(&zero, 1);
        uint8_t length[8];
        for (int i = 0; i < 8; ++i) length[i] = uint8_t(bits >> (56 - 8 * i));
        Update(length, 8);
        for (int i = 0; i < 8; ++i) for (int j = 0; j < 4; ++j) out[i * 4 + j] = uint8_t(h[i] >> (24 - 8 * j));
    }
};

// ---- the ModKit inside this file ----
// The ModKit is in this file, after the program, as a tar.gz of its folder: [tar.gz][SHA-256, 32 bytes][its size, 8 bytes][MKPAYLD1]. On the first run
// it is unpacked to $XDG_DATA_HOME/OpenShao/ModKit/<start of the hash>/ (the archive is checked against the hash first); later runs use that folder, which
// starts at once. A build with no payload (a development build) uses a folder modkit/ beside this file.
constexpr size_t kTrailer = 48;

struct Prepared {
    std::string program, error;
    std::atomic<bool> done{false};
};

std::string Hex(const uint8_t* bytes, size_t n) {
    static const char digits[] = "0123456789abcdef";
    std::string s;
    for (size_t i = 0; i < n; ++i) { s += digits[bytes[i] >> 4]; s += digits[bytes[i] & 15]; }
    return s;
}

bool ReadAt(int fd, uint64_t offset, void* buffer, size_t size) {
    uint8_t* out = static_cast<uint8_t*>(buffer);
    while (size) {
        const ssize_t n = pread(fd, out, size, off_t(offset));
        if (n <= 0) return false;
        out += n; offset += uint64_t(n); size -= size_t(n);
    }
    return true;
}

bool MakeFolder(const std::string& path) { return mkdir(path.c_str(), 0755) == 0 || errno == EEXIST; }

// mkdir -p
bool MakeFolders(const std::string& path) {
    for (size_t at = path.find('/', 1); at != std::string::npos; at = path.find('/', at + 1))
        if (!MakeFolder(path.substr(0, at))) return false;
    return MakeFolder(path);
}

bool Exists(const std::string& path) { return access(path.c_str(), X_OK) == 0; }

int Remove(const char* path, const struct stat*, int, struct FTW*) { return remove(path); }
void RemoveTree(const std::string& folder) { nftw(folder.c_str(), Remove, 16, FTW_DEPTH | FTW_PHYS); }

std::string SelfPath() {
    char path[4096];
    const ssize_t n = readlink("/proc/self/exe", path, sizeof(path) - 1);
    return n > 0 ? std::string(path, size_t(n)) : std::string();
}

std::string DataHome(const std::string& fallback) {
    const char* data = std::getenv("XDG_DATA_HOME");
    if (data && data[0] == '/') return data;
    const char* home = std::getenv("HOME");
    if (home && home[0] == '/') return std::string(home) + "/.local/share";
    return fallback;
}

// Copies the payload to `target` while hashing it; true when the hash is the one in the trailer.
bool Extract(int self, uint64_t offset, uint64_t size, const uint8_t* expected, const std::string& target) {
    const int out = open(target.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
    if (out < 0) return false;
    Sha256 hash;
    std::vector<uint8_t> block(4 << 20);
    bool ok = true;
    for (uint64_t done = 0; ok && done < size;) {
        const size_t n = size_t(std::min<uint64_t>(size - done, block.size()));
        ok = ReadAt(self, offset + done, block.data(), n);
        if (ok) {
            hash.Update(block.data(), n);
            for (size_t wrote = 0; ok && wrote < n;) {
                const ssize_t w = write(out, block.data() + wrote, n - wrote);
                ok = w > 0;
                if (ok) wrote += size_t(w);
            }
        }
        done += n;
    }
    uint8_t digest[32];
    hash.Finish(digest);
    ok = ok && std::memcmp(digest, expected, 32) == 0;
    close(out);
    if (!ok) unlink(target.c_str());
    return ok;
}

// Unpacks the archive into a folder with the system's tar; true when it succeeds.
bool Untar(const std::string& archive, const std::string& folder) {
    const pid_t child = fork();
    if (child < 0) return false;
    if (child == 0) {
        execlp("tar", "tar", "-xzf", archive.c_str(), "-C", folder.c_str(), static_cast<char*>(nullptr));
        _exit(127);
    }
    int status = 0;
    while (waitpid(child, &status, 0) < 0 && errno == EINTR) {}
    return WIFEXITED(status) && WEXITSTATUS(status) == 0;
}

// Older versions are removed (best effort: one that is running keeps working, as its files are only unlinked).
void RemoveOlderVersions(const std::string& versions, const std::string& current) {
    DIR* directory = opendir(versions.c_str());
    if (!directory) return;
    std::vector<std::string> old;
    while (const dirent* entry = readdir(directory)) {
        const std::string name = entry->d_name;
        const std::string path = versions + "/" + name;
        if (name == "." || name == ".." || path == current || name.compare(0, 7, "unpack-") == 0) continue;
        old.push_back(path);
    }
    closedir(directory);
    for (const std::string& path : old) RemoveTree(path);
}

void Prepare(Prepared& result, bool verbose) {
    const std::string self_path = SelfPath();
    const std::string folder = self_path.substr(0, self_path.find_last_of('/') + 1);
    const int self = open(self_path.c_str(), O_RDONLY | O_CLOEXEC);
    uint8_t trailer[kTrailer] = {};
    uint64_t total = 0;
    bool embedded = false;
    if (self >= 0) {
        const off_t end = lseek(self, 0, SEEK_END);
        total = end > 0 ? uint64_t(end) : 0;
        embedded = total > kTrailer && ReadAt(self, total - kTrailer, trailer, kTrailer) && std::memcmp(trailer + 40, "MKPAYLD1", 8) == 0;
    }
    if (!embedded) {
        if (self >= 0) close(self);
        result.program = folder + "modkit/modkit";
        if (!Exists(result.program)) result.error = "OpenShao-ModKit is incomplete: it has no ModKit inside it and there is no folder modkit beside it. Download it again.";
        result.done = true;
        return;
    }
    uint64_t size = 0;
    std::memcpy(&size, trailer + 32, 8);
    if (size == 0 || size > total - kTrailer) {
        result.error = "OpenShao-ModKit is damaged. Download it again.";
    } else {
        const std::string versions = DataHome(folder) + "/OpenShao/ModKit";
        const std::string current = versions + "/" + Hex(trailer + 0, 8), program = current + "/modkit";
        // a folder is unpacked beside its final place and renamed, so a folder with modkit in it is always a complete one
        if (!Exists(program)) {
            if (verbose) std::fprintf(stderr, "Unpacking the ModKit to %s (first run only)...\n", current.c_str());
            const std::string stem = versions + "/unpack-" + std::to_string(getpid());
            const std::string archive = stem + ".tar.gz", part = stem;
            RemoveTree(part);
            if (!MakeFolders(versions) || !MakeFolder(part))
                result.error = "The ModKit could not be unpacked: the folder " + versions + " could not be created.";
            else if (!Extract(self, total - kTrailer - size, size, trailer, archive))
                result.error = "The ModKit could not be unpacked to " + versions + ". There may be no space left, or OpenShao-ModKit is damaged.";
            else if (!Untar(archive, part))
                result.error = "The ModKit could not be unpacked: tar failed or is missing.";
            else if (rename(part.c_str(), current.c_str()) != 0 && !Exists(program))
                result.error = "The ModKit could not be unpacked to " + current + ".";  // if another run won the rename, its folder is used
            unlink(archive.c_str());
            RemoveTree(part);
        }
        if (result.error.empty()) {
            result.program = program;
            RemoveOlderVersions(versions, current);
        }
    }
    close(self);
    result.done = true;
}


// ---- the splash ----
struct Picture {
    uint32_t width = 0, height = 0;
    int32_t pad = 0;
    float advance = 0;
    const uint8_t* rgba = nullptr;
};

class Splash {
public:
    ~Splash() { Close(); }

    bool Create() {
        if (!LoadAssets()) return false;
        if (!std::getenv("DISPLAY") || !LoadXlib()) return false;
        display_ = x_.XOpenDisplay(nullptr);
        if (!display_) return false;
        const int screen = DefaultScreen(display_);
        // The splash has a transparent background, which only a compositing window manager can show.
        const Atom compositor = x_.XInternAtom(display_, ("_NET_WM_CM_S" + std::to_string(screen)).c_str(), False);
        if (x_.XGetSelectionOwner(display_, compositor) == None) return false;
        XVisualInfo visual;
        if (!x_.XMatchVisualInfo(display_, screen, 32, TrueColor, &visual)) return false;

        scale_ = Scale();
        width_ = int(kWidth * scale_ + 0.5);
        height_ = int(kHeight * scale_ + 0.5);
        const Window root = RootWindow(display_, screen);
        colormap_ = x_.XCreateColormap(display_, root, visual.visual, AllocNone);
        XSetWindowAttributes attributes = {};
        attributes.colormap = colormap_;
        attributes.border_pixel = 0;
        attributes.background_pixel = 0;
        attributes.override_redirect = True;  // no frame, no taskbar entry, and the window manager leaves it where it is put
        attributes.event_mask = 0;
        // the middle of the primary monitor, not of the whole screen, which is the space between the monitors when there are several
        int area_x = 0, area_y = 0, area_w = DisplayWidth(display_, screen), area_h = DisplayHeight(display_, screen);
        PrimaryMonitor(root, &area_x, &area_y, &area_w, &area_h);
        const int x = area_x + (area_w - width_) / 2, y = area_y + (area_h - height_) / 2;
        window_ = x_.XCreateWindow(display_, root, x, y, unsigned(width_), unsigned(height_), 0, 32, InputOutput, visual.visual,
                                   CWColormap | CWBorderPixel | CWBackPixel | CWOverrideRedirect | CWEventMask, &attributes);
        if (!window_) return false;
        XClassHint hint = {const_cast<char*>("openshao-modkit-splash"), const_cast<char*>("OpenShaoModKitSplash")};
        x_.XSetClassHint(display_, window_, &hint);
        PassClicksThrough();
        graphics_ = x_.XCreateGC(display_, window_, 0, nullptr);
        compose_.assign(size_t(kWidth * kCompose) * size_t(kHeight * kCompose) * 4, 0);
        frame_.assign(size_t(width_) * size_t(height_) * 4, 0);
        image_ = x_.XCreateImage(display_, visual.visual, 32, ZPixmap, 0, reinterpret_cast<char*>(frame_.data()), unsigned(width_), unsigned(height_), 32, 0);
        if (!image_) return false;
        Draw(0.0, 1.0);
        x_.XMapRaised(display_, window_);
        x_.XFlush(display_);
        return true;
    }

    // `seconds` since the start, `opacity` of the whole splash (below 1 while it fades out)
    void Draw(double seconds, double opacity) {
        if (!image_) return;
        std::fill(compose_.begin(), compose_.end(), uint8_t(0));
        const int cw = kWidth * kCompose;
        // the circle
        const int ring_x = (cw - int(ring_w_)) / 2, ring_y = 8 * kCompose;
        RenderRing(seconds, ring_x, ring_y, cw);
        // the name, then "Starting" with its dots at fixed places, so the word does not move while they come and go
        const int title_y = ring_y + int(ring_h_) + 6 * kCompose;
        Blit(title_, int((cw - title_.advance) / 2) - title_.pad, title_y - title_.pad, 1.0, cw);
        const double total = word_.advance + 3.0 * dot_.advance;
        const int line_x = int((cw - total) / 2), line_y = title_y + 44 * kCompose;
        Blit(word_, line_x - word_.pad, line_y - word_.pad, 1.0, cw);
        const double phase = std::fmod(seconds, kDotsCycle);
        for (int i = 0; i < 3; ++i) {
            const double on = Clamp01((phase - 0.22 * i) / 0.25) - Clamp01((phase - (1.25 + 0.22 * i)) / 0.25);
            if (on > 0.01)
                Blit(dot_, int(line_x + word_.advance + 2 + dot_.advance * i) - dot_.pad, line_y - dot_.pad, on, cw);
        }
        Resample(opacity);
        x_.XPutImage(display_, window_, graphics_, image_, 0, 0, 0, 0, unsigned(width_), unsigned(height_));
        x_.XFlush(display_);
    }

    void Close() {
        if (image_) { image_->data = nullptr; XDestroyImage(image_); image_ = nullptr; }
        if (display_) {
            if (graphics_) x_.XFreeGC(display_, graphics_);
            if (window_) x_.XDestroyWindow(display_, window_);
            if (colormap_) x_.XFreeColormap(display_, colormap_);
            x_.XFlush(display_);
            x_.XCloseDisplay(display_);
        }
        display_ = nullptr;
        graphics_ = nullptr;
        window_ = 0;
        colormap_ = 0;
    }

private:
    struct Xlib {
        decltype(&::XOpenDisplay) XOpenDisplay = nullptr;
        decltype(&::XCloseDisplay) XCloseDisplay = nullptr;
        decltype(&::XInternAtom) XInternAtom = nullptr;
        decltype(&::XGetSelectionOwner) XGetSelectionOwner = nullptr;
        decltype(&::XMatchVisualInfo) XMatchVisualInfo = nullptr;
        decltype(&::XCreateColormap) XCreateColormap = nullptr;
        decltype(&::XFreeColormap) XFreeColormap = nullptr;
        decltype(&::XCreateWindow) XCreateWindow = nullptr;
        decltype(&::XDestroyWindow) XDestroyWindow = nullptr;
        decltype(&::XMapRaised) XMapRaised = nullptr;
        decltype(&::XCreateGC) XCreateGC = nullptr;
        decltype(&::XFreeGC) XFreeGC = nullptr;
        decltype(&::XCreateImage) XCreateImage = nullptr;
        decltype(&::XPutImage) XPutImage = nullptr;
        decltype(&::XFlush) XFlush = nullptr;
        decltype(&::XResourceManagerString) XResourceManagerString = nullptr;
        decltype(&::XSetClassHint) XSetClassHint = nullptr;
    } x_;
    decltype(&::XFixesCreateRegion) fixes_create_ = nullptr;
    decltype(&::XFixesSetWindowShapeRegion) fixes_shape_ = nullptr;
    decltype(&::XFixesDestroyRegion) fixes_destroy_ = nullptr;
    decltype(&::XRRGetMonitors) randr_monitors_ = nullptr;
    decltype(&::XRRFreeMonitors) randr_free_ = nullptr;

    bool LoadXlib() {
        void* lib = dlopen("libX11.so.6", RTLD_NOW | RTLD_GLOBAL);
        if (!lib) return false;
        bool ok = true;
#define LOAD(name) ok = ok && (x_.name = reinterpret_cast<decltype(x_.name)>(dlsym(lib, #name))) != nullptr
        LOAD(XOpenDisplay); LOAD(XCloseDisplay); LOAD(XInternAtom); LOAD(XGetSelectionOwner); LOAD(XMatchVisualInfo); LOAD(XCreateColormap);
        LOAD(XFreeColormap); LOAD(XCreateWindow); LOAD(XDestroyWindow); LOAD(XMapRaised); LOAD(XCreateGC); LOAD(XFreeGC); LOAD(XCreateImage);
        LOAD(XPutImage); LOAD(XFlush); LOAD(XResourceManagerString); LOAD(XSetClassHint);
#undef LOAD
        if (void* fixes = dlopen("libXfixes.so.3", RTLD_NOW)) {  // best effort: without it the splash takes the clicks it covers
            fixes_create_ = reinterpret_cast<decltype(fixes_create_)>(dlsym(fixes, "XFixesCreateRegion"));
            fixes_shape_ = reinterpret_cast<decltype(fixes_shape_)>(dlsym(fixes, "XFixesSetWindowShapeRegion"));
            fixes_destroy_ = reinterpret_cast<decltype(fixes_destroy_)>(dlsym(fixes, "XFixesDestroyRegion"));
        }
        if (void* randr = dlopen("libXrandr.so.2", RTLD_NOW)) {  // best effort: without it the splash is centred on the whole screen
            randr_monitors_ = reinterpret_cast<decltype(randr_monitors_)>(dlsym(randr, "XRRGetMonitors"));
            randr_free_ = reinterpret_cast<decltype(randr_free_)>(dlsym(randr, "XRRFreeMonitors"));
        }
        return ok;
    }

    // The primary monitor's rectangle (the first monitor when none is marked primary); the whole screen when RandR cannot tell.
    void PrimaryMonitor(Window root, int* x, int* y, int* width, int* height) {
        if (!randr_monitors_ || !randr_free_) return;
        int count = 0;
        XRRMonitorInfo* monitors = randr_monitors_(display_, root, True, &count);
        if (!monitors) return;
        int pick = -1;
        for (int i = 0; i < count && pick < 0; ++i)
            if (monitors[i].primary) pick = i;
        if (pick < 0 && count > 0) pick = 0;
        if (pick >= 0) {
            *x = monitors[pick].x; *y = monitors[pick].y; *width = monitors[pick].width; *height = monitors[pick].height;
        }
        randr_free_(monitors);
    }

    // An empty input region: clicks go to the window below, as they do through the splash of the Windows launcher.
    void PassClicksThrough() {
        if (!fixes_create_ || !fixes_shape_ || !fixes_destroy_) return;
        const XserverRegion region = fixes_create_(display_, nullptr, 0);
        fixes_shape_(display_, window_, ShapeInput, 0, 0, region);
        fixes_destroy_(display_, region);
    }

    // The display's scale from Xft.dpi (96 is 1), so the splash is the size on screen it has on any other system
    double Scale() {
        double dpi = 96.0;
        if (const char* resources = x_.XResourceManagerString(display_)) {
            if (const char* at = std::strstr(resources, "Xft.dpi:")) dpi = std::atof(at + 8);
        }
        const double scale = dpi / 96.0;
        return scale < 1.0 ? 1.0 : (scale > 4.0 ? 4.0 : scale);
    }

    bool LoadAssets() {
        const uint8_t* p = kAssets;
        const uint8_t* end = kAssetsEnd;
        if (end - p < 16 || std::memcmp(p, "MKSPLSH1", 8) != 0) return false;
        p += 8;
        std::memcpy(&ring_w_, p, 4); std::memcpy(&ring_h_, p + 4, 4);
        p += 8;
        const size_t pixels = size_t(ring_w_) * ring_h_;
        if (size_t(end - p) < pixels * 5) return false;
        ring_rgba_ = p;
        ring_along_ = p + pixels * 4;
        p += pixels * 5;
        for (Picture* text : {&title_, &word_, &dot_}) {
            if (end - p < 16) return false;
            std::memcpy(&text->width, p, 4); std::memcpy(&text->height, p + 4, 4);
            std::memcpy(&text->pad, p + 8, 4); std::memcpy(&text->advance, p + 12, 4);
            p += 16;
            const size_t bytes = size_t(text->width) * text->height * 4;
            if (size_t(end - p) < bytes) return false;
            text->rgba = p;
            p += bytes;
        }
        return true;
    }

    // The circle is drawn in over one phase and drawn out over the next, then again: the same mask the interface uses for its progress, moving
    // along the stroke, so the end of a phase is the start of the other.
    void RenderRing(double seconds, int x0, int y0, int stride_pixels) {
        const double cycle = std::fmod(seconds, 2 * kPhase);
        const bool drawing_in = cycle < kPhase;
        const double progress = Ease(Clamp01((drawing_in ? cycle : cycle - kPhase) / kPhase));
        const double limit = progress * 1.04;
        // The mask only changes with the position along the stroke: a table of 256 steps makes it one lookup a pixel.
        uint8_t visible[256];
        for (int i = 0; i < 256; ++i) {
            const double reach = Smooth(limit - 0.035, limit, i / 255.0);
            visible[i] = uint8_t(255.0 * (drawing_in ? 1.0 - reach : reach) + 0.5);
        }
        for (uint32_t row = 0; row < ring_h_; ++row) {
            uint8_t* out = compose_.data() + (size_t(y0 + int(row)) * size_t(stride_pixels) + size_t(x0)) * 4;
            const uint8_t* in = ring_rgba_ + size_t(row) * ring_w_ * 4;
            const uint8_t* along = ring_along_ + size_t(row) * ring_w_;
            for (uint32_t col = 0; col < ring_w_; ++col, out += 4, in += 4) {
                const unsigned alpha = (unsigned(in[3]) * visible[along[col]] + 127) / 255;
                out[0] = uint8_t((in[2] * alpha + 127) / 255);  // BGRA, premultiplied
                out[1] = uint8_t((in[1] * alpha + 127) / 255);
                out[2] = uint8_t((in[0] * alpha + 127) / 255);
                out[3] = uint8_t(alpha);
            }
        }
    }

    // `text` over the composed picture at (x, y), with `strength` as extra opacity
    void Blit(const Picture& text, int x, int y, double strength, int stride_pixels) {
        const int rows = int(compose_.size() / 4 / size_t(stride_pixels));
        const unsigned s = unsigned(255.0 * Clamp01(strength) + 0.5);
        for (int row = 0; row < int(text.height); ++row) {
            const int ty = y + row;
            if (ty < 0 || ty >= rows) continue;
            for (int col = 0; col < int(text.width); ++col) {
                const int tx = x + col;
                if (tx < 0 || tx >= stride_pixels) continue;
                const uint8_t* in = text.rgba + (size_t(row) * text.width + size_t(col)) * 4;
                const unsigned a = (unsigned(in[3]) * s + 127) / 255;
                if (!a) continue;
                uint8_t* out = compose_.data() + (size_t(ty) * size_t(stride_pixels) + size_t(tx)) * 4;
                const unsigned keep = 255 - a;
                out[0] = uint8_t((in[2] * a + out[0] * keep + 127) / 255);
                out[1] = uint8_t((in[1] * a + out[1] * keep + 127) / 255);
                out[2] = uint8_t((in[0] * a + out[2] * keep + 127) / 255);
                out[3] = uint8_t(a + (out[3] * keep + 127) / 255);
            }
        }
    }

    // The composed picture (at kCompose times the logical size) to the size of the screen, averaging what each pixel covers, with `opacity` on all of it
    void Resample(double opacity) {
        const int cw = kWidth * kCompose, ch = kHeight * kCompose;
        const double sx = double(cw) / width_, sy = double(ch) / height_;
        const unsigned o = unsigned(256.0 * Clamp01(opacity) + 0.5);
        for (int y = 0; y < height_; ++y) {
            const int y0 = int(y * sy), y1 = std::min(ch, std::max(y0 + 1, int(std::ceil((y + 1) * sy))));
            for (int x = 0; x < width_; ++x) {
                const int x0 = int(x * sx), x1 = std::min(cw, std::max(x0 + 1, int(std::ceil((x + 1) * sx))));
                unsigned sum[4] = {0, 0, 0, 0}, count = 0;
                for (int yy = y0; yy < y1; ++yy) {
                    const uint8_t* in = compose_.data() + (size_t(yy) * size_t(cw) + size_t(x0)) * 4;
                    for (int xx = x0; xx < x1; ++xx, in += 4, ++count) { sum[0] += in[0]; sum[1] += in[1]; sum[2] += in[2]; sum[3] += in[3]; }
                }
                uint8_t* out = frame_.data() + (size_t(y) * size_t(width_) + size_t(x)) * 4;
                for (int c = 0; c < 4; ++c) out[c] = uint8_t(std::min(255u, (sum[c] / count) * o / 256));
            }
        }
    }

    Display* display_ = nullptr;
    Window window_ = 0;
    Colormap colormap_ = 0;
    GC graphics_ = nullptr;
    XImage* image_ = nullptr;
    std::vector<uint8_t> compose_, frame_;
    uint32_t ring_w_ = 0, ring_h_ = 0;
    const uint8_t* ring_rgba_ = nullptr;
    const uint8_t* ring_along_ = nullptr;
    Picture title_, word_, dot_;
    double scale_ = 1.0;
    int width_ = 0, height_ = 0;
};

// An error to the user: on the terminal, and in a dialog when the system has one of the usual tools (the launcher may have been opened from a file manager)
void ShowError(const std::string& text) {
    std::fprintf(stderr, "OpenShao ModKit: %s\n", text.c_str());
    if (!std::getenv("DISPLAY") && !std::getenv("WAYLAND_DISPLAY")) return;
    const pid_t child = fork();
    if (child != 0) {
        if (child > 0) { int status = 0; while (waitpid(child, &status, 0) < 0 && errno == EINTR) {} }
        return;
    }
    execlp("zenity", "zenity", "--error", "--title=OpenShao ModKit", ("--text=" + text).c_str(), static_cast<char*>(nullptr));
    execlp("kdialog", "kdialog", "--title", "OpenShao ModKit", "--error", text.c_str(), static_cast<char*>(nullptr));
    _exit(0);
}

bool IsCommand(const char* word) {
    for (const char* name : {"extract", "check", "init", "compile", "verify", "gui", "-h", "--help"})
        if (std::strcmp(word, name) == 0) return true;
    return false;
}

}  // namespace

int main(int argc, char** argv) {
    signal(SIGPIPE, SIG_IGN);

    // A command of the ModKit runs in the terminal, with no splash: the program is replaced by the ModKit.
    if (argc > 1 && IsCommand(argv[1])) {
        Prepared prepared;
        Prepare(prepared, true);
        if (!prepared.error.empty()) { std::fprintf(stderr, "OpenShao ModKit: %s\n", prepared.error.c_str()); return 1; }
        std::vector<char*> args{const_cast<char*>(prepared.program.c_str())};
        for (int i = 1; i < argc; ++i) args.push_back(argv[i]);
        args.push_back(nullptr);
        execv(prepared.program.c_str(), args.data());
        std::perror("OpenShao ModKit: the ModKit could not be started");
        return 1;
    }

    int ready[2] = {-1, -1};
    if (pipe(ready) != 0) { ShowError("The ModKit could not be started (pipe)."); return 1; }
    fcntl(ready[0], F_SETFD, FD_CLOEXEC);
    setenv("MODKIT_READY_FD", std::to_string(ready[1]).c_str(), 1);

    Prepared prepared;
    std::thread worker(Prepare, std::ref(prepared), false);
    int result = 0;
    pid_t child = 0;
    {
        Splash splash;
        const bool shown = splash.Create();
        double fade_started = -1;
        bool started = false;
        const double began = Now();
        for (;;) {
            const double elapsed = Now() - began;
            if (!started && prepared.done) {
                if (!prepared.error.empty()) {
                    splash.Close();
                    ShowError(prepared.error);
                    result = 1;
                    break;
                }
                child = fork();
                if (child == 0) {
                    setsid();  // the ModKit goes on when this program ends
                    close(ready[0]);
                    std::vector<char*> args{const_cast<char*>(prepared.program.c_str()), const_cast<char*>("gui")};
                    for (int i = 1; i < argc; ++i) args.push_back(argv[i]);
                    args.push_back(nullptr);
                    execv(prepared.program.c_str(), args.data());
                    _exit(127);
                }
                close(ready[1]);
                ready[1] = -1;
                if (child < 0) {
                    splash.Close();
                    ShowError("The ModKit could not be started.");
                    result = 1;
                    break;
                }
                started = true;
            }
            if (started && fade_started < 0) {
                pollfd watch = {ready[0], POLLIN, 0};
                if (poll(&watch, 1, 0) > 0) {
                    fade_started = elapsed;  // a byte: the window is up (end of file: the ModKit ended, which the check below reports)
                    char byte;
                    if (read(ready[0], &byte, 1) <= 0) {
                        int status = 0;
                        if (waitpid(child, &status, WNOHANG) == child) {
                            splash.Close();
                            ShowError("OpenShao ModKit closed before it opened (code " + std::to_string(WIFEXITED(status) ? WEXITSTATUS(status) : -1) +
                                      "). Run \"OpenShao-ModKit gui\" in a terminal to see why.");
                            result = 1;
                            break;
                        }
                    }
                } else if (elapsed > kGiveUp) {
                    fade_started = elapsed;
                }
            }
            double opacity = 1.0;
            if (fade_started >= 0) {
                opacity = 1.0 - (elapsed - fade_started) / kFadeOut;
                if (opacity <= 0) break;
            }
            if (shown) splash.Draw(elapsed, opacity);
            usleep(12000);
        }
        splash.Close();
    }
    worker.join();
    if (ready[0] >= 0) close(ready[0]);
    if (ready[1] >= 0) close(ready[1]);
    return result;
}
