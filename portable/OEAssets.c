/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "OEAssets.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <sys/stat.h>

const char *const OEAssetNames[OE_ASSET_COUNT] = {
    "terrain.drs", "graphics.drs", "interfac.drs", "blendomatic.dat"
};
static bool fail(char *err, size_t size, const char *fmt, ...) {
    if (err && size) {
        va_list ap; va_start(ap, fmt); vsnprintf(err, size, fmt, ap); va_end(ap);
    }
    return false;
}
static uint32_t u32(const unsigned char *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
           (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static bool span(uint64_t offset, uint64_t bytes, uint64_t size) {
    return offset <= size && bytes <= size - offset;
}
bool OEAssets_CheckDRS(const char *path, unsigned slp_table, char *err, size_t errlen) {
    struct stat st;
    if (!path || stat(path, &st) || !S_ISREG(st.st_mode) || st.st_size < 76 ||
        st.st_size > 512LL * 1024 * 1024)
        return fail(err, errlen, "Missing, empty, or oversized DRS: %s", path ? path : "(null)");
    FILE *fp = fopen(path, "rb");
    if (!fp) return fail(err, errlen, "Cannot read %s", path);
    unsigned char header[64], tables[16][12];
    const uint64_t size = (uint64_t)st.st_size;
    bool ok = false;
    if (fread(header, 1, 64, fp) != 64) goto finish;
    uint32_t count = u32(header + 56);
    if (!count || count > 16 || slp_table >= count ||
        !span(64, (uint64_t)count * 12, size)) goto finish;
    if (fread(tables, 12, count, fp) != count) goto finish;
    if (memcmp(tables[slp_table], " pls", 4)) goto finish;
    if (slp_table == 1 && memcmp(tables[0], "anib", 4)) goto finish;
    uint64_t cursor = 64 + (uint64_t)count * 12;
    for (uint32_t i = 0; i < count; ++i) {
        uint32_t offset = u32(tables[i] + 4), files = u32(tables[i] + 8);
        /* This engine reads the file records sequentially, not by offset. */
        if (!files || files > 100000 || offset != cursor ||
            !span(cursor, (uint64_t)files * 12, size)) goto finish;
        for (uint32_t j = 0; j < files; ++j) {
            unsigned char record[12];
            if (fread(record, 1, 12, fp) != 12) goto finish;
            uint32_t data_offset = u32(record + 4), bytes = u32(record + 8);
            if (!bytes || !span(data_offset, bytes, size)) goto finish;
        }
        cursor += (uint64_t)files * 12;
    }
    ok = true;
finish:
    fclose(fp);
    return ok ? true : fail(err, errlen, "Unsupported or damaged Trial DRS: %s", path);
}
bool OEAssets_CheckDirectory(const char *path, char *err, size_t errlen) {
    if (!path || !*path) return fail(err, errlen, "Choose the installed Trial Data folder.");
    char file[4096];
    for (unsigned i = 0; i < OE_ASSET_COUNT; ++i) {
        int n = snprintf(file, sizeof(file), "%s/%s", path, OEAssetNames[i]);
        if (n < 0 || (size_t)n >= sizeof(file)) return fail(err, errlen, "Asset path is too long.");
        if (i < 3) {
            if (!OEAssets_CheckDRS(file, i == 2 ? 1 : 0, err, errlen)) return false;
        } else {
            struct stat st;
            if (stat(file, &st) || !S_ISREG(st.st_mode) || st.st_size < 8 ||
                st.st_size > 64LL * 1024 * 1024)
                return fail(err, errlen, "Missing or invalid blendomatic.dat");
            FILE *fp = fopen(file, "rb");
            unsigned char header[8];
            if (!fp) return fail(err, errlen, "Cannot read blendomatic.dat");
            size_t nread = fread(header, 1, 8, fp);
            if (nread != 8 || !u32(header) || u32(header) > 256 ||
                u32(header + 4) < 31 || u32(header + 4) > 256) {
                fclose(fp); return fail(err, errlen, "Unsupported blendomatic.dat header");
            }
            uint32_t modes = u32(header), tiles = u32(header + 4);
            uint64_t cursor = 8;
            bool complete = true;
            for (uint32_t mode = 0; mode < modes; ++mode) {
                unsigned char raw[4];
                if (!span(cursor, 4, (uint64_t)st.st_size) || fread(raw, 1, 4, fp) != 4) {
                    complete = false; break;
                }
                uint32_t tile_size = u32(raw);
                if (!tile_size || tile_size > 65536) { complete = false; break; }
                uint64_t bytes = tiles + ((uint64_t)tiles + 1) * tile_size / 8 + (uint64_t)tiles * tile_size;
                cursor += 4;
                if (!span(cursor, bytes, (uint64_t)st.st_size) || fseek(fp, (long)bytes, SEEK_CUR)) {
                    complete = false; break;
                }
                cursor += bytes;
            }
            fclose(fp);
            if (!complete) return fail(err, errlen, "Truncated or invalid blendomatic.dat mode data");
        }
    }
    if (err && errlen) *err = '\0';
    return true;
}

/* Preserve the separator required by upstream Util_StringJoin(path, filename). */
bool OEAssets_EnginePath(const char *input, char *output, size_t capacity) {
    if (!input || !output || capacity == 0) return false;
    output[0] = '\0';
    size_t n = strlen(input);
    if (n == 0 || n >= capacity) return false;
    bool append = input[n-1] != '/';
    if (append && n >= capacity-1) return false;
    memcpy(output, input, n);
    if (append) output[n++] = '/';
    output[n] = '\0';
    return true;
}
