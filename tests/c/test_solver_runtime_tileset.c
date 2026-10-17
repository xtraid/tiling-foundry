#include "wang/solver.h"
#include "wang/verify.h"
#include <assert.h>
#include <stdio.h>

static Region rectangle(int width, int height)
{
    Region r = {0};
    assert(region_init(&r, width, height));
    for (int y = 0; y < height; ++y)
        for (int x = 0; x < width; ++x)
            assert(region_set_active(&r, x, y, true));
    return r;
}

int main(void)
{
    WangTile alternating[2] = {
        {.edge = {0, 1, 0, 0}}, {.edge = {0, 0, 0, 1}}
    };
    Region r = rectangle(2, 1);
    assert(region_set_boundary(&r, 0, 0, W, 0));
    assert(region_set_boundary(&r, 1, 0, E, 0));
    WangSolveResult out = {0};
    assert(wang_solve_optimized_tileset(&r, alternating, 2, NULL, &out) == WANG_SOLVE_SAT);
    assert(out.domains[0] == 1 && out.domains[1] == 2);
    const TileId solution[2] = {0, 1};
    assert(wang_verify_tiling_with_tileset(&r, solution, 2, alternating, 2) == WANG_VERIFY_VALID);
    wang_solve_result_destroy(&out);
    assert(region_set_boundary(&r, 1, 0, E, 1));
    assert(wang_solve_optimized_tileset(&r, alternating, 2, NULL, &out) == WANG_SOLVE_UNSAT);
    wang_solve_result_destroy(&out);
    region_destroy(&r);

    /* Exercise bit 31, four-byte support and the largest MRV domain. */
    WangTile full[32] = {0};
    for (int d = 0; d < 4; ++d) full[31].edge[d] = 1;
    r = rectangle(3, 2);
    uint32_t domains[6] = {UINT32_MAX, UINT32_MAX, UINT32_MAX,
                          UINT32_MAX, UINT32_MAX, UINT32_C(1) << 31};
    WangSolverOptions options = {.flags = WANG_SOLVE_COLLECT_METRICS,
                                .initial_domains = domains, .initial_domain_count = 6};
    assert(wang_solve_optimized_tileset(&r, full, 32, &options, &out) == WANG_SOLVE_SAT);
    for (int i = 0; i < 6; ++i) assert(out.domains[i] == (UINT32_C(1) << 31));
    assert(out.metrics.support_table_bytes == 4u * 4u * 256u * sizeof(uint32_t));
    wang_solve_result_destroy(&out);
    assert(wang_solve_optimized_tileset(&r, full, 32, NULL, &out) == WANG_SOLVE_SAT);
    wang_solve_result_destroy(&out);
    assert(wang_solve_optimized_tileset(&r, full, 0, NULL, &out) == WANG_SOLVE_ERROR);
    assert(wang_solve_optimized_tileset(&r, full, 33, NULL, &out) == WANG_SOLVE_ERROR);
    assert(wang_solve_optimized_tileset(&r, full, 1, &options, &out) == WANG_SOLVE_ERROR);
    full[0].edge[0] = COLOR_COUNT;
    assert(wang_solve_optimized_tileset(&r, full, 32, NULL, &out) == WANG_SOLVE_ERROR);
    region_destroy(&r);
    puts("test_solver_runtime_tileset: OK");
    return 0;
}
