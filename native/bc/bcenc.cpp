// A small C interface over rgbcx (BC1 and BC3, levels 0 to 18) and stb_dxt (BC1 and BC3), for the pack tools' Python code.
// rgbcx and stb_dxt are in this folder with their own licenses (MIT or public domain). Build with build.sh.
#include <cstring>
#include <cstdlib>
#include <cmath>
#define STB_DXT_IMPLEMENTATION
#include "stb_dxt.h"
#include "rgbcx.h"
#include <cstdint>

#if defined(_WIN32)
#define BC_API extern "C" __declspec(dllexport)
#else
#define BC_API extern "C" __attribute__((visibility("default")))
#endif

namespace {
void Gather(const uint8_t* rgba, int w, int bx, int by, uint8_t block[64]) {
    for (int y = 0; y < 4; ++y) std::memcpy(block + y * 16, rgba + (size_t(by * 4 + y) * w + bx * 4) * 4, 16);
}
}

BC_API void bc_init() { rgbcx::init(); }

// `format` is 1 for BC1 and 2 for BC3; the image is RGBA, a multiple of 4 on both sides, and `out` is blocks of 8 or 16 bytes
BC_API void bc_encode_rgbcx(const uint8_t* rgba, int w, int h, int format, int level, uint8_t* out) {
    const size_t size = format == 1 ? 8 : 16;
    uint8_t block[64];
    for (int by = 0; by < h / 4; ++by)
        for (int bx = 0; bx < w / 4; ++bx) {
            Gather(rgba, w, bx, by, block);
            uint8_t* dst = out + (size_t(by) * (w / 4) + bx) * size;
            if (format == 1) rgbcx::encode_bc1(uint32_t(level), dst, block, false, false);
            else rgbcx::encode_bc3(uint32_t(level), dst, block);
        }
}

BC_API void bc_encode_stb(const uint8_t* rgba, int w, int h, int format, int high_quality, uint8_t* out) {
    const size_t size = format == 1 ? 8 : 16;
    uint8_t block[64];
    for (int by = 0; by < h / 4; ++by)
        for (int bx = 0; bx < w / 4; ++bx) {
            Gather(rgba, w, bx, by, block);
            stb_compress_dxt_block(out + (size_t(by) * (w / 4) + bx) * size, block, format == 2 ? 1 : 0, high_quality ? STB_DXT_HIGHQUAL : 0);
        }
}
