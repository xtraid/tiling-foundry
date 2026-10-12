#include "dynamic.h"
#include <stdlib.h>
#include <string.h>

typedef struct {
    size_t index;
    uint32_t old;
} Change;
typedef struct {
    size_t cell, next, mark;
} Frame;
typedef struct {
    const FoundryWebGraph *g;
    size_t tiles, words, used, capacity, color_count;
    uint32_t *color_stamps, epoch;
    uint32_t *domains;
    Change *trail;
    WangSolverMetrics metrics;
} Search;

static uint32_t edge(const FoundryWebGraph *g, size_t i)
{
    return g->wide_colors ? ((const uint32_t *)g->edges)[i] : ((const uint8_t *)g->edges)[i];
}
static uint32_t boundary(const FoundryWebGraph *g, size_t i)
{
    uint32_t value =
        g->wide_colors ? ((const uint32_t *)g->boundary)[i] : ((const uint8_t *)g->boundary)[i];
    return !g->wide_colors && value == COLOR_NONE ? UINT32_MAX : value;
}
static void *array(size_t n, size_t size)
{
    return n && n <= SIZE_MAX / size ? calloc(n, size) : NULL;
}
static bool has(const Search *s, size_t c, size_t t)
{
    return (s->domains[c * s->words + t / 32] & (UINT32_C(1) << (t % 32))) != 0;
}
static bool change(Search *s, size_t i, uint32_t value)
{
    if (s->domains[i] == value)
        return true;
    if (s->used == s->capacity) {
        size_t cap = s->capacity ? s->capacity * 2 : 256;
        if (cap < s->capacity || cap > SIZE_MAX / sizeof(Change))
            return false;
        Change *p = realloc(s->trail, cap * sizeof(Change));
        if (!p)
            return false;
        s->trail = p;
        s->capacity = cap;
    }
    s->trail[s->used++] = (Change){i, s->domains[i]};
    s->domains[i] = value;
    ++s->metrics.domain_reductions;
    return true;
}
static void undo(Search *s, size_t mark)
{
    while (s->used > mark) {
        Change c = s->trail[--s->used];
        s->domains[c.index] = c.old;
    }
}
/* Arc consistency: an edge value is supported iff it occurs on the incident
 * neighbor side. Revisit all arcs until no word changes. */
static int propagate(Search *s)
{
    const FoundryWebGraph *g = s->g;
    size_t before;
    do {
        before = s->used;
        for (size_t c = 0; c < g->cell_count; ++c) {
            for (size_t d = 0; d < g->side_count; ++d) {
                size_t a = c * g->side_count + d;
                int32_t n = g->neighbors[a];
                if (n < 0)
                    continue;
                if (++s->epoch == 0) {
                    memset(s->color_stamps, 0, s->color_count * sizeof(uint32_t));
                    s->epoch = 1;
                }
                for (size_t t = 0; t < s->tiles; ++t)
                    if (has(s, (size_t)n, t))
                        s->color_stamps[edge(g, t * g->side_count + g->neighbor_sides[a])] =
                            s->epoch;
                for (size_t w = 0; w < s->words; ++w) {
                    size_t i = c * s->words + w;
                    uint32_t bits = s->domains[i], kept = bits;
                    while (bits) {
                        unsigned b = (unsigned)__builtin_ctz(bits);
                        size_t t = w * 32 + b;
                        if (s->color_stamps[edge(g, t * g->side_count + d)] != s->epoch)
                            kept &= ~(UINT32_C(1) << b);
                        bits &= bits - 1;
                    }
                    if (!change(s, i, kept))
                        return -1;
                }
            }
            uint32_t any = 0;
            for (size_t w = 0; w < s->words; ++w)
                any |= s->domains[c * s->words + w];
            if (!any)
                return 0;
        }
    } while (before != s->used);
    return 1;
}
static size_t choose(Search *s)
{
    size_t best = SIZE_MAX, minimum = SIZE_MAX;
    for (size_t c = 0; c < s->g->cell_count; ++c) {
        size_t count = 0;
        for (size_t w = 0; w < s->words; ++w)
            count += (unsigned)__builtin_popcount(s->domains[c * s->words + w]);
        if (count > 1 && count < minimum) {
            best = c;
            minimum = count;
        }
    }
    return best;
}
static size_t singleton(const Search *s, size_t c)
{
    size_t tile = SIZE_MAX;
    for (size_t w = 0; w < s->words; ++w) {
        uint32_t bits = s->domains[c * s->words + w];
        if (!bits)
            continue;
        if (tile != SIZE_MAX || (bits & (bits - 1)))
            return SIZE_MAX;
        tile = w * 32 + (unsigned)__builtin_ctz(bits);
    }
    return tile;
}
static bool verify(const Search *s, const uint32_t *initial)
{
    const FoundryWebGraph *g = s->g;
    for (size_t c = 0; c < g->cell_count; ++c) {
        size_t t = singleton(s, c);
        if (t >= s->tiles || !(initial[c * s->words + t / 32] & (UINT32_C(1) << (t % 32))))
            return false;
        for (size_t d = 0; d < g->side_count; ++d) {
            size_t a = c * g->side_count + d;
            uint32_t color = edge(g, t * g->side_count + d);
            if (boundary(g, a) != UINT32_MAX && boundary(g, a) != color)
                return false;
            if (g->neighbors[a] >= 0) {
                size_t u = singleton(s, (size_t)g->neighbors[a]);
                if (u >= s->tiles || color != edge(g, u * g->side_count + g->neighbor_sides[a]))
                    return false;
            }
        }
    }
    return true;
}
int foundry_dynamic_graph(const FoundryWebGraph *g, size_t tiles, const uint32_t *initial,
                          WangSolutionVisitor visit, void *userdata)
{
    if (!g || !initial || !visit || !tiles || tiles > SIZE_MAX - 31 || !g->cell_count ||
        g->cell_count > FOUNDRY_WEB_MAX_CELLS || !g->side_count || g->side_count > 6 ||
        !g->neighbors || !g->neighbor_sides || !g->boundary || !g->edges ||
        tiles > SIZE_MAX / g->side_count)
        return -1;
    if (tiles * g->side_count > SIZE_MAX / (g->wide_colors ? sizeof(uint32_t) : 1))
        return -1;
    size_t color_count = 1;
    for (size_t i = 0; i < tiles * g->side_count; ++i) {
        uint32_t color = edge(g, i);
        if (color >= FOUNDRY_WEB_MAX_COLORS)
            return -1;
        if ((size_t)color + 1 > color_count)
            color_count = (size_t)color + 1;
    }
    for (size_t c = 0; c < g->cell_count; ++c)
        for (size_t d = 0; d < g->side_count; ++d) {
            size_t a = c * g->side_count + d;
            int32_t n = g->neighbors[a];
            if (boundary(g, a) != UINT32_MAX && boundary(g, a) >= FOUNDRY_WEB_MAX_COLORS)
                return -1;
            if (n == -1)
                continue;
            if (n < 0 || (size_t)n >= g->cell_count || (size_t)n == c ||
                g->neighbor_sides[a] >= g->side_count)
                return -1;
            size_t back = (size_t)n * g->side_count + g->neighbor_sides[a];
            if (g->neighbors[back] != (int32_t)c || g->neighbor_sides[back] != d)
                return -1;
        }
    Search s = {.g = g, .tiles = tiles, .words = (tiles + 31) / 32, .color_count = color_count};
    if (s.words > SIZE_MAX / g->cell_count)
        return -1;
    size_t length = s.words * g->cell_count;
    s.domains = array(length, sizeof(uint32_t));
    s.color_stamps = array(color_count, sizeof(uint32_t));
    Frame *stack = array(g->cell_count, sizeof(Frame));
    int result = -1;
    if (!s.domains || !stack || !s.color_stamps)
        goto done;
    memcpy(s.domains, initial, length * sizeof(uint32_t));
    for (size_t c = 0; c < g->cell_count; ++c) {
        if (tiles % 32 && (s.domains[(c + 1) * s.words - 1] >> (tiles % 32)))
            goto done;
        for (size_t t = 0; t < tiles; ++t)
            if (has(&s, c, t)) {
                bool keep = true;
                for (size_t d = 0; d < g->side_count; ++d) {
                    uint32_t color = boundary(g, c * g->side_count + d);
                    if (color != UINT32_MAX && color != edge(g, t * g->side_count + d))
                        keep = false;
                }
                /* Collapse only allowed duplicate tuples, retaining the first ID. */
                for (size_t u = 0; keep && u < t; ++u)
                    if (has(&s, c, u) && !memcmp((const uint8_t *)g->edges +
                                                     u * g->side_count * (g->wide_colors ? 4 : 1),
                                                 (const uint8_t *)g->edges +
                                                     t * g->side_count * (g->wide_colors ? 4 : 1),
                                                 g->side_count * (g->wide_colors ? 4 : 1)))
                        keep = false;
                if (!keep)
                    s.domains[c * s.words + t / 32] &= ~(UINT32_C(1) << (t % 32));
            }
    }
    size_t depth = 0;
    int consistent = propagate(&s);
    if (consistent < 0)
        goto done;
    s.used = 0; /* Root pruning is permanent. */
    for (;;) {
        if (consistent) {
            ++s.metrics.dfs_nodes;
            size_t cell = choose(&s);
            if (cell == SIZE_MAX) {
                if (!verify(&s, initial))
                    goto done;
                if (!visit(s.domains, g->cell_count, &s.metrics, userdata)) {
                    result = 1;
                    goto done;
                }
            } else {
                stack[depth++] = (Frame){cell, 0, s.used};
            }
        }
        bool branched = false;
        while (depth) {
            Frame *f = &stack[depth - 1];
            undo(&s, f->mark);
            size_t t = f->next;
            while (t < tiles && !has(&s, f->cell, t))
                ++t;
            if (t == tiles) {
                --depth;
                ++s.metrics.backtracks;
                continue;
            }
            f->next = t + 1;
            for (size_t w = 0; w < s.words; ++w)
                if (!change(&s, f->cell * s.words + w, w == t / 32 ? UINT32_C(1) << (t % 32) : 0))
                    goto done;
            consistent = propagate(&s);
            if (consistent < 0)
                goto done;
            branched = true;
            break;
        }
        if (!branched) {
            result = 0;
            break;
        }
    }
done:
    free(stack);
    free(s.domains);
    free(s.trail);
    free(s.color_stamps);
    return result;
}
