#include "wang/solver.h"
#include <assert.h>
#include <stdio.h>

typedef struct { size_t count, limit; uint32_t last; } Capture;
static bool visit(const uint32_t *domains, size_t n,
                  const WangSolverMetrics *metrics, void *userdata)
{
    Capture *capture = userdata;
    assert(domains != NULL && n > 0 && metrics != NULL);
    ++capture->count;
    capture->last = domains[0];
    return capture->limit == 0 || capture->count < capture->limit;
}

int main(void)
{
    Region region = {0};
    assert(region_init(&region, 1, 1));
    assert(region_set_active(&region, 0, 0, true));
    WangTile tiles[3] = {{.edge={0,0,0,0}}, {.edge={1,1,1,1}}, {.edge={0,0,0,0}}};
    Capture c = {0};
    assert(wang_enumerate_optimized_tileset(&region,tiles,3,NULL,visit,&c,NULL)==0);
    assert(c.count==2); /* Isolated choices cannot be collapsed to one. */
    uint32_t domain=4; /* An allowed duplicate must remain usable. */
    WangSolverOptions options={.initial_domains=&domain,.initial_domain_count=1};
    c=(Capture){0};
    assert(wang_enumerate_optimized_tileset(&region,tiles,3,&options,visit,&c,NULL)==0);
    assert(c.count==1 && c.last==4);
    c=(Capture){.limit=1};
    assert(wang_enumerate_optimized_tileset(&region,tiles,3,NULL,visit,&c,NULL)==1);
    assert(c.count==1);
    domain=0;c=(Capture){0};
    assert(wang_enumerate_optimized_tileset(&region,tiles,3,&options,visit,&c,NULL)==0);
    assert(c.count==0);
    region_destroy(&region);

    assert(region_init(&region,2,2));
    WangTile binary[16]={0};
    for (unsigned t=0;t<16;t++) for (unsigned d=0;d<4;d++) binary[t].edge[d]=(t>>d)&1u;
    for(int y=0;y<2;y++) for(int x=0;x<2;x++) assert(region_set_active(&region,x,y,true));
    for(int y=0;y<2;y++) for(int x=0;x<2;x++) {
        if(y==0) assert(region_set_boundary(&region,x,y,N,0));
        if(y==1) assert(region_set_boundary(&region,x,y,S,0));
        if(x==0) assert(region_set_boundary(&region,x,y,W,0));
        if(x==1) assert(region_set_boundary(&region,x,y,E,0));
    }
    c=(Capture){0};
    WangSolverMetrics metrics={0};
    options=(WangSolverOptions){.flags=WANG_SOLVE_COLLECT_METRICS};
    assert(wang_enumerate_optimized_tileset(&region,binary,16,&options,visit,&c,&metrics)==0);
    assert(c.count==16 && metrics.backtracks>0);
    c=(Capture){0};
    metrics=(WangSolverMetrics){0};
    assert(wang_enumerate_serial_tileset(&region,binary,16,&options,visit,&c,&metrics)==0);
    assert(c.count==16 && metrics.backtracks>0);
    c=(Capture){.limit=1};
    assert(wang_enumerate_serial_tileset(&region,binary,16,&options,visit,&c,NULL)==1);
    assert(c.count==1);
    region_destroy(&region);
    puts("test_solver_enumeration: OK");
    return 0;
}
