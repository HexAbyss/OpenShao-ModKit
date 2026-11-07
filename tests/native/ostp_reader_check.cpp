#include "texture_pack_file.h"
#include <cstdio>
using namespace openshao::texpack;
int main(int argc, char** argv) {
    std::string error;
    auto pack = PackFile::Open(argv[1], error);
    if (!pack) { std::printf("REFUSED: %s\n", error.c_str()); return 1; }
    std::printf("info %s | %s | %s | authors %zu | logo %s %ux%u\n", pack->info().id.c_str(), pack->info().name.c_str(), pack->info().version.c_str(),
                pack->info().authors.size(), pack->logo() ? "yes" : "no", pack->logo() ? pack->logo()->width : 0, pack->logo() ? pack->logo()->height : 0);
    for (const auto& e : pack->entries()) {
        std::vector<uint8_t> b;
        if (!pack->ReadLevels(e, 0, b)) { std::printf("READ FAILED %016llx\n", (unsigned long long)e.hash); return 1; }
        uint64_t h = 0xcbf29ce484222325ull;
        for (uint8_t c : b) h = (h ^ c) * 0x100000001b3ull;
        std::printf("%016llx %u %u %d %d %zu %016llx\n", (unsigned long long)e.hash, e.width, e.height, int(e.format), int(e.alpha), b.size(), (unsigned long long)h);
    }
}
