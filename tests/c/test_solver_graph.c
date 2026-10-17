#include "wang/solver.h"
#include <assert.h>
#include <stdio.h>

static bool visit(const uint32_t *domains, size_t n,
                  const WangSolverMetrics *metrics, void *userdata)
{
    (void)metrics;
    assert(n == 2 && domains[0] && domains[1]);
    ++*(int *)userdata;
    return true;
}

int main(void)
{
    /* Different side numbers exercise explicit arcs, independent of geometry. */
    int32_t neighbors[12] = {-1,-1,-1,-1,-1,1, 0,-1,-1,-1,-1,-1};
    uint8_t sides[12] = {0,0,0,0,0,0, 5,0,0,0,0,0};
    uint8_t boundary[12];
    for (size_t i = 0; i < 12; ++i) boundary[i] = COLOR_NONE;
    const uint8_t edges[18] = {0,0,0,0,0,0, 1,1,1,1,1,1, 0,0,0,0,0,0};
    WangGraph graph = {2,6,neighbors,sides,boundary,edges};
    for (int reference = 0; reference < 2; ++reference) {
        int count = 0;
        assert(wang_enumerate_graph(&graph,3,NULL,reference,visit,&count,NULL) == 0);
        assert(count == 2); /* Duplicate tuples collapse. */
        uint32_t domains[2] = {4,1};
        WangSolverOptions options = {.initial_domains=domains,.initial_domain_count=2};
        count = 0;
        assert(wang_enumerate_graph(&graph,3,&options,reference,visit,&count,NULL) == 0);
        assert(count == 1); /* A duplicate pinned by ID remains available. */
        boundary[5] = 1;
        count = 0;
        assert(wang_enumerate_graph(&graph,3,&options,reference,visit,&count,NULL) == 0);
        assert(count == 0);
        boundary[5] = COLOR_NONE;
    }
    int count = 0;
    sides[6] = 4;
    assert(wang_enumerate_graph(&graph,3,NULL,false,visit,&count,NULL) == -1);
    sides[6] = 5;
    neighbors[5] = 2;
    assert(wang_enumerate_graph(&graph,3,NULL,false,visit,&count,NULL) == -1);
    neighbors[5] = 1;
    graph.side_count = 7;
    assert(wang_enumerate_graph(&graph,3,NULL,false,visit,&count,NULL) == -1);
    puts("test_solver_graph: OK");
}
