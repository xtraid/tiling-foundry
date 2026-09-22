#equivalent of yang-zhang.c

from .formula import Formula
from .region import Region

def source_token(n):
    source = []
    for i in range(n):
        for j in range(3):
            source.append(("x",i,j))
        source.append(("z",i))
    return tuple(source[0:-1])

def target_token(formula):
    target = []
    occurrences = [0] * formula.variable_count
    for i,clause in enumerate(formula.clauses):
        for letter in clause:
            v= letter -1
            target.append(("x",v,occurrences[v]))
            occurrences[v] += 1
        target.append(("z",i))
    return tuple(target[:-1])

def adjacent_swap (src, r):
    app = src[r]
    src[r] = src[r+1]
    src[r+1]= app


def swap_plan(source, target) -> list:
    plan = []
    src = list(source)
    obj = list(target)
    for i in range(len(obj)):
        j = 0
        while src[j] != obj[i]:
            if j + 1 >= len(src):
                raise IndexError
            j += 1
        if j < i:
            for k in range(i - j):
                plan.append(i - k - 1) # per come è formulato adjacent_swap
                adjacent_swap(src, i - k - 1)
        elif j > i:
            for k in range(j - i):
                plan.append(j - k - 1)
                adjacent_swap(src, j - k - 1)
        else:
            continue
    return plan

def crossovers (boundary, plan, width):
    n = len(boundary)
    height = n // width
    k = 0
    if len(plan) == 0:
        return
    start_block = 3
    end_block  = start_block + plan[0]
    for i in range (3, width -4):
        if (i == start_block):
            boundary[width * (height - 1) + i][2] = "L"
        if i == end_block:
            boundary[i][0] = "R"
            start_block = end_block + 1
            k += 1
            if k < len(plan):
                end_block = start_block + plan[k]


def boundary_helper (active, height, width, plan):
    n = width * height
    boundary = [[None] * 4 for i in range(n)]

    for i in range(n):
        if not active[i]:
            continue
        x = i % width
        y = i // width
        if y == 0 or not active [i - width]:
            boundary[i][0] = "B"   # N
        if x == width - 1 or not active[i + 1]:
            boundary[i][1] = "B"   # E
        if y == height - 1 or not active[i +width]:
            boundary[i][2] = "B"   # S
        if x == 0 or not active[i - 1]:
            boundary[i][3] = "B"   # W


    z_count = 0
    for i in range (height):
        left = i * width
        right = (i +1) * width -1
        while not active[right]:
            right -= 1

        if i % 4 == 3: # inutile chiedere se sono ative sono tutte attive
            boundary[left][3] = "0"
            boundary[right][1] = "0"

            z_count += 1
        else:
            boundary[left][3] = "V"
            if i % 4 in (0, 1):
                boundary[right][1] = "0'"
            else:
                boundary[right][1] = "1"
    crossovers(boundary, plan, width)
    return boundary





def building_region(formula: Formula) -> Region:
    source = source_token(formula.variable_count)
    target = target_token(formula)
    plan = swap_plan(source, target)

    height = 4 * formula.variable_count - 1
    xpartition = []
    for i in range (len (plan)):
        xpartition.append(plan[i] + 1)
    width = 7 + sum(xpartition)
    n = width * height
    active = [True] * n
    for i in range (height):
        if (i % 4 == 0):
            active[(i + 1) *width-1] = False
        if (i %4 == 3):
            active[(i + 1) *width-1] = False
            active[(i + 1) *width-2] = False
    boundary = boundary_helper(active, height, width, plan)
    region = Region(width, height, active, boundary)
    return region 




