/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef OE_ASSETS_H
#define OE_ASSETS_H
#include <stdbool.h>
#include <stddef.h>
#define OE_ASSET_COUNT 4
extern const char *const OEAssetNames[OE_ASSET_COUNT];
/* The original engine concatenates filenames, so the directory must end in /.
   Input and output buffers must not overlap. */
bool OEAssets_EnginePath(const char *input, char *output, size_t capacity);
/* Structural preflight, not a proof that arbitrary untrusted assets are safe. */
bool OEAssets_CheckDirectory(const char *path, char *error, size_t error_size);
bool OEAssets_CheckDRS(const char *path, unsigned slp_table, char *error, size_t error_size);
#endif
