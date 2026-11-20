"""Search algorithms the enemies use to reach the castle: BFS, DFS and A*.

All three share one signature so an enemy can swap algorithms freely:

    search(start, goals, neighbours, cost=None, rng=None) -> SearchResult

* start      -- (x, y) cell to search from
* goals      -- set of (x, y) cells; the search stops at the first one reached
* neighbours -- callable(pos) -> iterable of open cells next to pos
* cost       -- callable(pos) -> cost of stepping onto pos, always >= 1.
                Only A* uses it; BFS and DFS count every step as 1.
* rng        -- optional random.Random, used by DFS to break ties
"""

from __future__ import annotations

import heapq
import time
from collections import deque
from dataclasses import dataclass, field

DIRECTIONS = ((0, -1), (1, 0), (0, 1), (-1, 0))  # up, right, down, left


@dataclass
class SearchResult:
    algorithm: str
    found: bool = False
    path: list = field(default_factory=list)      # cells to walk, start excluded
    explored: list = field(default_factory=list)  # cells expanded, in order
    max_frontier: int = 0                         # peak size of the queue / stack / heap
    seconds: float = 0.0


def manhattan(pos, goals):
    """Grid distance to the nearest goal. Never overestimates when each step costs >= 1."""
    x, y = pos
    return min(abs(x - gx) + abs(y - gy) for gx, gy in goals)


def _finish(algorithm, parent, end, explored, max_frontier, started):
    path = []
    if end is not None:
        while parent[end] is not None:
            path.append(end)
            end = parent[end]
        path.reverse()
    return SearchResult(
        algorithm,
        found=end is not None,
        path=path,
        explored=explored,
        max_frontier=max_frontier,
        seconds=time.perf_counter() - started,
    )


def bfs(start, goals, neighbours, cost=None, rng=None) -> SearchResult:
    """Breadth-first search: expands cells ring by ring (a FIFO queue), so the
    first goal it reaches is the one with the fewest steps. Ignores step costs."""
    started = time.perf_counter()
    parent = {start: None}
    queue = deque([start])
    explored = []
    peak = 1
    end = start if start in goals else None
    while queue and end is None:
        cur = queue.popleft()
        explored.append(cur)
        for nxt in neighbours(cur):
            if nxt in parent:
                continue
            parent[nxt] = cur
            if nxt in goals:
                end = nxt
                break
            queue.append(nxt)
        peak = max(peak, len(queue))
    return _finish("BFS", parent, end, explored, peak, started)


def dfs(start, goals, neighbours, cost=None, rng=None, greedy=True) -> SearchResult:
    """Depth-first search: always extends the newest branch (a LIFO stack) and
    backs up only at dead ends. It keeps the first route it completes, which is
    often far from the shortest.

    greedy=True tries the neighbour closest to the goal first (ties broken at
    random), so it heads for the castle; greedy=False is textbook DFS with a
    random neighbour order, which wanders much more."""
    started = time.perf_counter()
    parent = {start: None}
    stack = [start]
    seen = set()
    explored = []
    peak = 1
    end = None
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        explored.append(cur)
        if cur in goals:
            end = cur
            break
        nbrs = [n for n in neighbours(cur) if n not in seen]
        if rng is not None:
            rng.shuffle(nbrs)
        if greedy:
            # Push the farthest first so the closest ends up on top of the stack.
            nbrs.sort(key=lambda n: manhattan(n, goals), reverse=True)
        for nxt in nbrs:
            parent[nxt] = cur
            stack.append(nxt)
        peak = max(peak, len(stack))
    return _finish("DFS", parent, end, explored, peak, started)


def astar(start, goals, neighbours, cost=None, rng=None) -> SearchResult:
    """A*: expands the cell with the lowest f = g + h, where g is the cost paid
    so far and h is the Manhattan distance to the castle. Finds the cheapest
    route by `cost`, and the heuristic keeps it from expanding cells that lead away."""
    started = time.perf_counter()
    cost = cost or (lambda pos: 1)
    parent = {start: None}
    g_cost = {start: 0}
    h0 = manhattan(start, goals)
    heap = [(h0, h0, 0, start)]  # (f, h, tie-breaker, cell): on equal f prefer lower h
    closed = set()
    explored = []
    peak = 1
    counter = 0
    end = None
    while heap:
        _, _, _, cur = heapq.heappop(heap)
        if cur in closed:
            continue
        closed.add(cur)
        explored.append(cur)
        if cur in goals:
            end = cur
            break
        for nxt in neighbours(cur):
            if nxt in closed:
                continue
            new_g = g_cost[cur] + cost(nxt)
            if new_g < g_cost.get(nxt, float("inf")):
                g_cost[nxt] = new_g
                parent[nxt] = cur
                counter += 1
                h = manhattan(nxt, goals)
                heapq.heappush(heap, (new_g + h, h, counter, nxt))
        peak = max(peak, len(heap))
    return _finish("A*", parent, end, explored, peak, started)


def distance_field(sources, neighbours):
    """Multi-source BFS: steps from every reachable cell to the nearest source.

    Run from the castle, this tells towers which enemy is closest to breaking
    through, and tells the builder whether a wall would cut a gate off.
    """
    dist = {s: 0 for s in sources}
    queue = deque(sources)
    while queue:
        cur = queue.popleft()
        for nxt in neighbours(cur):
            if nxt not in dist:
                dist[nxt] = dist[cur] + 1
                queue.append(nxt)
    return dist


ALGORITHMS = {"BFS": bfs, "DFS": dfs, "A*": astar}
