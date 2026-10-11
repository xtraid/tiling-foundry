/* Browser ABI only. Propagation, enumeration and verification stay in Foundry. */
#include "wang/solver.h"
#include <emscripten.h>
#include <string.h>

EM_JS(int, publish_solution, (const uint32_t *domains, const uint64_t *metrics), {
    return Module['onSolution'](domains, metrics);
});

EM_ASYNC_JS(int, wait_for_browser, (int action), {
    return await Module['onWait'](action);
});

static bool visit(const uint32_t *domains, size_t count,
                  const WangSolverMetrics *metrics, void *unused)
{
    (void)count;
    (void)unused;
    const uint64_t counters[3] = {
        metrics->dfs_nodes, metrics->backtracks, metrics->domain_reductions
    };
    const int action = publish_solution(domains, counters);
    return action == 0 || wait_for_browser(action) != 0;
}

EMSCRIPTEN_KEEPALIVE
int foundry_enumerate(int32_t width, int32_t height, const uint8_t *active,
                      const uint8_t *boundary, const uint8_t *edges,
                      size_t tile_count, const uint32_t *initial, int reference)
{
    if (width <= 0 || height <= 0 || (uint64_t)width * (uint64_t)height > 16384 ||
        !active || !boundary || !edges || !initial ||
        tile_count == 0 || tile_count > WANG_RUNTIME_MAX_TILES) return -1;
    Region region = {0};
    if (!region_init(&region, width, height)) return -1;
    WangTile tiles[WANG_RUNTIME_MAX_TILES] = {0};
    for (size_t t = 0; t < tile_count; ++t) {
        tiles[t].id = (TileId)t;
        memcpy(tiles[t].edge, edges + t * DIR_COUNT, DIR_COUNT);
    }
    for (size_t i = 0; i < region.cell_count; ++i) {
        region.cells[i].active = active[i] != 0;
        memcpy(region.cells[i].boundary, boundary + i * DIR_COUNT, DIR_COUNT);
    }
    const WangSolverOptions options = {
        .flags = WANG_SOLVE_COLLECT_METRICS,
        .initial_domains = initial,
        .initial_domain_count = region.cell_count
    };
    const int result = reference
        ? wang_enumerate_serial_tileset(&region, tiles, tile_count, &options, visit, NULL, NULL)
        : wang_enumerate_optimized_tileset(&region, tiles, tile_count, &options, visit, NULL, NULL);
    region_destroy(&region);
    return result;
}

EMSCRIPTEN_KEEPALIVE
int foundry_enumerate_graph(int32_t count, int32_t sides, const int32_t *neighbors,
    const uint8_t *neighbor_sides, const uint8_t *boundary, const uint8_t *edges,
    size_t tile_count, const uint32_t *initial, int reference)
{
    if (count <= 0 || sides <= 0 || !initial) return -1;
    const WangGraph graph = {(size_t)count, (size_t)sides, neighbors, neighbor_sides, boundary, edges};
    const WangSolverOptions options = {
        .flags = WANG_SOLVE_COLLECT_METRICS,
        .initial_domains = initial, .initial_domain_count = (size_t)count
    };
    return wang_enumerate_graph(&graph, tile_count, &options, reference != 0, visit, NULL, NULL);
}
