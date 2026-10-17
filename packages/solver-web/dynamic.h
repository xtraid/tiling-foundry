/* Private browser engine. Domains are cell-major arrays of ceil(tiles/32) words.
 * Callback snapshots have the same layout. Native solver APIs are untouched. */
#ifndef FOUNDRY_WEB_DYNAMIC_H
#define FOUNDRY_WEB_DYNAMIC_H
#include "wang/solver.h"
#define FOUNDRY_WEB_MAX_CELLS 65536u
#define FOUNDRY_WEB_MAX_COLORS 65536u
/* Byte colors retain ABI 2 compatibility; wide colors use uint32_t with
 * UINT32_MAX for unconstrained boundaries. Native WangGraph is unchanged. */
typedef struct {
    size_t cell_count, side_count;
    const int32_t *neighbors;
    const uint8_t *neighbor_sides;
    const void *boundary, *edges;
    bool wide_colors;
} FoundryWebGraph;
int foundry_dynamic_graph(const FoundryWebGraph *g, size_t tiles, const uint32_t *initial,
                          WangSolutionVisitor visit, void *userdata);
#endif
