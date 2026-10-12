/* Standalone test of the browser-only implementation, with allocation faults.
 * cc -Iinclude -std=c17 -Wall -Wextra -Werror -fsanitize=address,undefined
 * tests/test_web_dynamic.c -o build/test_web_dynamic */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
static size_t calls, fail_at = SIZE_MAX;
static void *test_calloc(size_t n, size_t z) { return calls++ == fail_at ? NULL : calloc(n, z); }
static void *test_realloc(void *p, size_t z) { return calls++ == fail_at ? NULL : realloc(p, z); }
#define calloc test_calloc
#define realloc test_realloc
#include "../packages/solver-web/dynamic.c"
#undef calloc
#undef realloc
static size_t solutions;
static bool visit(const uint32_t *d, size_t n, const WangSolverMetrics *m, void *u)
{
    (void)d;
    (void)n;
    (void)u;
    (void)m;
    ++solutions;
    return true;
}
static void ring(size_t tiles, size_t cells)
{
    size_t words = (tiles + 31) / 32;
    uint8_t *edges = calloc(tiles * 2, 1);
    uint32_t *initial = calloc(cells * words, sizeof(uint32_t));
    int32_t *neighbors = calloc(cells * 2, sizeof(int32_t));
    uint8_t *sides = calloc(cells * 2, 1), *boundary = calloc(cells * 2, 1);
    assert(edges && initial && neighbors && sides && boundary);
    edges[(tiles - 2) * 2] = 0;
    edges[(tiles - 2) * 2 + 1] = 1;
    edges[(tiles - 1) * 2] = 1;
    edges[(tiles - 1) * 2 + 1] = 0;
    for (size_t c = 0; c < cells; c++) {
        neighbors[c * 2] = (int32_t)((c + cells - 1) % cells);
        neighbors[c * 2 + 1] = (int32_t)((c + 1) % cells);
        sides[c * 2] = 1;
        sides[c * 2 + 1] = 0;
        boundary[c * 2] = boundary[c * 2 + 1] = 255;
        for (size_t t = tiles - 2; t < tiles; t++)
            initial[c * words + t / 32] |= UINT32_C(1) << (t % 32);
    }
    WangGraph g = {cells, 2, neighbors, sides, boundary, edges};
    calls = solutions = 0;
    fail_at = SIZE_MAX;
    assert(foundry_dynamic_graph(&g, tiles, initial, visit, NULL) == 0);
    assert(solutions == (cells % 2 ? 0 : 2));
    size_t allocations = calls;
    for (size_t fail = 0; fail < allocations; fail++) {
        calls = solutions = 0;
        fail_at = fail;
        assert(foundry_dynamic_graph(&g, tiles, initial, visit, NULL) == -1);
    }
    fail_at = SIZE_MAX;
    if (tiles % 32) {
        initial[words - 1] |= UINT32_C(1) << (tiles % 32);
        assert(foundry_dynamic_graph(&g, tiles, initial, visit, NULL) == -1);
    }
    free(edges);
    free(initial);
    free(neighbors);
    free(sides);
    free(boundary);
}
int main(void)
{
    const size_t counts[] = {23, 31, 32, 33, 64, 65, 96, 97, 257, 1025};
    for (size_t i = 0; i < sizeof(counts) / sizeof(*counts); i++) {
        ring(counts[i], 3);
        ring(counts[i], 4);
    }
    ring(65, 1024); /* Grow the undo trail repeatedly; fail each realloc. */
    puts("PASS dynamic: arc-consistent odd-cycle UNSAT, even-cycle SAT, rollback, high IDs, "
         "invalid tail bits, every allocation fault.");
}
