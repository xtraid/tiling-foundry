/* Private browser engine. Domains are cell-major arrays of ceil(tiles/32) words.
 * Callback snapshots have the same layout. Native solver APIs are untouched. */
#ifndef FOUNDRY_WEB_DYNAMIC_H
#define FOUNDRY_WEB_DYNAMIC_H
#include "wang/solver.h"
int foundry_dynamic_graph(const WangGraph *g, size_t tiles, const uint32_t *initial,
                          WangSolutionVisitor visit, void *userdata);
#endif
