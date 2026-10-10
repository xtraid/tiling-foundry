#include "wang/verify.h"

WangVerifyStatus wang_verify_tiling_with_tileset(
    const Region *region,
    const TileId *tiles,
    size_t tile_count,
    const WangTile *tileset,
    size_t tileset_count
)
{
    if (region == NULL || tiles == NULL || tileset == NULL ||
        tileset_count == 0 || tileset_count > 32u) {
        return WANG_VERIFY_INVALID_ARGUMENT;
    }

    for (size_t t = 0; t < tileset_count; ++t) {
        for (Dir d = N; d < DIR_COUNT; ++d) {
            if (tileset[t].edge[d] >= COLOR_COUNT) return WANG_VERIFY_INVALID_ARGUMENT;
        }
    }

    if (!region_validate(region)) {
        return WANG_VERIFY_INVALID_REGION;
    }

    const size_t expected_count = region->cell_count;

    if (tile_count != expected_count) {
        return WANG_VERIFY_INVALID_LENGTH;
    }

    for (size_t index = 0; index < expected_count; ++index) {
        const RegionCell *cell = &region->cells[index];
        const TileId tile_id = tiles[index];

        if (!cell->active) {
            if (tile_id != TILE_NONE) {
                return WANG_VERIFY_INACTIVE_ASSIGNED;
            }
            continue;
        }

        if (tile_id == TILE_NONE) {
            return WANG_VERIFY_INCOMPLETE;
        }
        if (tile_id >= tileset_count) {
            return WANG_VERIFY_INVALID_TILE_ID;
        }

        const WangTile *tile = &tileset[tile_id];
        for (Dir dir = N; dir < DIR_COUNT; ++dir) {
            const ColorId required = cell->boundary[dir];
            if (required != COLOR_NONE && tile->edge[dir] != required) {
                return WANG_VERIFY_BOUNDARY_MISMATCH;
            }
        }
    }

    for (int32_t y = 0; y < region->height; ++y) {
        for (int32_t x = 0; x < region->width; ++x) {
            const size_t index = region_index(region, x, y);
            const RegionCell *cell = &region->cells[index];
            if (!cell->active) {
                continue;
            }

            static const Dir checked_dirs[] = { E, S };
            static const int32_t dx[] = { 1, 0 };
            static const int32_t dy[] = { 0, 1 };
            for (size_t d = 0; d < 2; ++d) {
                const Dir dir = checked_dirs[d];
                const int32_t neighbor_x = x + dx[d];
                const int32_t neighbor_y = y + dy[d];
                const RegionCell *neighbor =
                    region_cell_const(region, neighbor_x, neighbor_y);
                if (neighbor == NULL || !neighbor->active) {
                    continue;
                }

                const size_t neighbor_index = region_index(
                    region,
                    neighbor_x,
                    neighbor_y
                );
                const WangTile *tile = &tileset[tiles[index]];
                const WangTile *neighbor_tile = &tileset[tiles[neighbor_index]];

                if (tile->edge[dir] != neighbor_tile->edge[opposite(dir)]) {
                    return WANG_VERIFY_ADJACENCY_MISMATCH;
                }
            }
        }
    }

    return WANG_VERIFY_VALID;
}

WangVerifyStatus wang_verify_tiling(
    const Region *region, const TileId *tiles, size_t tile_count
)
{
    return wang_verify_tiling_with_tileset(
        region, tiles, tile_count, TILESET, TILE_COUNT);
}
