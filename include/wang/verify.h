#ifndef WANG_VERIFY_H
#define WANG_VERIFY_H

#include <stddef.h>

#include "wang/region.h"
#include "wang/tile.h"

typedef enum {
    WANG_VERIFY_VALID = 0,
    WANG_VERIFY_INVALID_ARGUMENT,
    WANG_VERIFY_INVALID_REGION,
    WANG_VERIFY_INVALID_LENGTH,
    WANG_VERIFY_INCOMPLETE,
    WANG_VERIFY_INVALID_TILE_ID,
    WANG_VERIFY_INACTIVE_ASSIGNED,
    WANG_VERIFY_BOUNDARY_MISMATCH,
    WANG_VERIFY_ADJACENCY_MISMATCH
} WangVerifyStatus;

/*
 * Verify a complete dense row-major tiling independently from solver state.
 * Active cells require a valid TileId; inactive cells require TILE_NONE.
 */
WangVerifyStatus wang_verify_tiling(
    const Region *region,
    const TileId *tiles,
    size_t tile_count
);

/* Independent verification against an explicitly supplied square tileset. */
WangVerifyStatus wang_verify_tiling_with_tileset(
    const Region *region, const TileId *tiles, size_t tile_count,
    const WangTile *tileset, size_t tileset_count
);

#endif /* WANG_VERIFY_H */
