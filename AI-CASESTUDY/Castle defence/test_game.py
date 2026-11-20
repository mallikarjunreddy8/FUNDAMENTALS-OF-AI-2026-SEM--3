"""Headless checks for the search algorithms and the game model.

Run with:   py test_game.py      (or: py -m pytest test_game.py)
"""

import heapq
import math
import random

from board import render_board
from model import ROCK, TOWER_TYPES, CastleDefence
from pathfinding import DIRECTIONS, astar, bfs, dfs

# ------------------------------------------------------------ helpers


def random_grid(rng, w=15, h=10, wall_p=0.25):
    walls = {(x, y) for x in range(w) for y in range(h) if rng.random() < wall_p}
    costs = {(x, y): rng.choice([1, 1, 1, 2, 5]) for x in range(w) for y in range(h)}

    def neighbours(pos):
        x, y = pos
        for dx, dy in DIRECTIONS:
            n = (x + dx, y + dy)
            if 0 <= n[0] < w and 0 <= n[1] < h and n not in walls:
                yield n

    open_cells = [(x, y) for x in range(w) for y in range(h) if (x, y) not in walls]
    return neighbours, costs.__getitem__, open_cells


def dijkstra(start, goals, neighbours, cost):
    best = {start: 0}
    heap = [(0, start)]
    while heap:
        d, cur = heapq.heappop(heap)
        if cur in goals:
            return d
        if d > best[cur]:
            continue
        for n in neighbours(cur):
            nd = d + cost(n)
            if nd < best.get(n, math.inf):
                best[n] = nd
                heapq.heappush(heap, (nd, n))
    return None


def assert_valid_path(start, goals, path, neighbours):
    cur = start
    for cell in path:
        assert cell in set(neighbours(cur)), f"{cell} is not next to {cur}"
        cur = cell
    assert cur in goals


def open_map(**kw):
    return CastleDefence(rock_density=0, mud_density=0, seed=1, **kw)


# ------------------------------------------------------- search algorithms


def test_algorithms_against_reference():
    rng = random.Random(42)
    checked = 0
    for _ in range(300):
        neighbours, cost, cells = random_grid(rng)
        start, goal = rng.sample(cells, 2)
        goals = {goal}
        steps = dijkstra(start, goals, neighbours, lambda p: 1)
        best_cost = dijkstra(start, goals, neighbours, cost)
        results = [
            bfs(start, goals, neighbours),
            astar(start, goals, neighbours, cost=cost),
            dfs(start, goals, neighbours, rng=rng),
            dfs(start, goals, neighbours, rng=rng, greedy=False),
        ]
        if steps is None:
            assert not any(r.found or r.path for r in results)
            continue
        checked += 1
        for r in results:
            assert r.found
            assert_valid_path(start, goals, r.path, neighbours)
        bfs_r, astar_r, dfs_r, dfs_rand = results
        assert len(bfs_r.path) == steps, "BFS must find the fewest steps"
        assert sum(cost(p) for p in astar_r.path) == best_cost, "A* must find the cheapest route"
        assert len(dfs_r.path) >= steps and len(dfs_rand.path) >= steps
    assert checked > 150


def test_astar_expands_fewer_cells_than_bfs_on_open_ground():
    def neighbours(pos):
        x, y = pos
        for dx, dy in DIRECTIONS:
            if 0 <= x + dx < 30 and 0 <= y + dy < 30:
                yield (x + dx, y + dy)

    goals = {(29, 15)}
    b = bfs((0, 15), goals, neighbours)
    a = astar((0, 15), goals, neighbours)
    assert len(a.path) == len(b.path) == 29
    assert len(a.explored) * 5 < len(b.explored)


def test_start_on_goal():
    for search in (bfs, dfs, astar):
        r = search((1, 1), {(1, 1)}, lambda p: [])
        assert r.found and r.path == []


# ------------------------------------------------------------------- model


def test_build_rules_and_gold():
    m = open_map()
    gold = m.gold
    assert m.build("Archer", (10, 3))
    assert m.gold == gold - TOWER_TYPES["Archer"].cost
    assert not m.build("Wall", (10, 3)), "cell already taken"
    assert not m.build("Wall", m.gates[0])
    assert not m.build("Wall", next(iter(m.castle_cells)))
    assert m.sell((10, 3))
    assert m.gold == gold - TOWER_TYPES["Archer"].cost + TOWER_TYPES["Archer"].cost // 2
    assert not m.sell((10, 3))


def test_cannot_seal_the_castle_off():
    m = open_map(difficulty="Easy")
    m.gold = 10_000
    x = 12
    for y in range(m.height - 1):
        assert m.build("Wall", (x, y)), m.message
    assert not m.build("Wall", (x, m.height - 1))
    assert "wall the castle off" in m.message
    for gate in m.gates:
        assert m.search("BFS", gate).found


def test_rocks_block_building():
    m = CastleDefence(seed=3)
    rock = next(p for p, t in m.terrain.items() if t == ROCK)
    assert not m.build("Wall", rock)


def test_knights_route_around_tower_fire():
    m = open_map()
    m.gold = 10_000
    gate = m.gates[1]
    for x in (8, 12, 16):
        assert m.build("Archer", (x, gate[1] - 1))
    exposure = {
        algo: sum(m.danger.get(p, 0) for p in m.search(algo, gate).path) for algo in ("BFS", "A*")
    }
    assert exposure["A*"] < exposure["BFS"]
    a_cost = sum(m.route_cost(p) for p in m.search("A*", gate).path)
    b_cost = sum(m.route_cost(p) for p in m.search("BFS", gate).path)
    assert a_cost <= b_cost


def test_enemies_replan_after_a_build():
    m = open_map()
    m.start_wave()
    m.step()
    enemy = m.live_enemies()[0]
    version = enemy.plan_version
    target = enemy.path[1]
    assert m.build("Wall", target), m.message
    m.step()
    assert enemy.plan_version != version
    assert target not in enemy.path


def test_undefended_castle_falls():
    m = CastleDefence(seed=5)
    for _ in range(2000):
        if m.phase in ("won", "lost"):
            break
        if m.phase == "build":
            m.start_wave()
        m.step()
    assert m.phase == "lost" and m.castle_hp == 0
    assert not m.running


def test_same_seed_same_game():
    def play(seed):
        m = CastleDefence(seed=seed)
        m.build("Archer", (20, 5))
        while m.phase not in ("won", "lost") and m.turn < 300:
            if m.phase == "build":
                m.start_wave()
            m.step()
        return m.terrain, m.turn, m.castle_hp, m.stats

    assert play(11) == play(11)


def test_full_game_with_towers_and_render():
    m = CastleDefence(seed=2, difficulty="Easy", n_waves=4)
    while m.phase not in ("won", "lost"):
        if m.phase == "build":
            for pos in [(19, 4), (19, 9), (17, 6), (21, 4), (21, 10), (15, 8)]:
                kind = "Cannon" if m.gold >= 60 else "Archer"
                m.build(kind, pos)
            m.start_wave()
        m.step()
        svg = render_board(m, search="A*", routes=True, ranges=True, danger=True)
        assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert m.phase == "won", m.message
    df = m.datacollector.get_model_vars_dataframe()
    assert len(df) == m.turn and df["Castle HP"].iloc[-1] == m.castle_hp


if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print(f"ok  {name}")
    print(f"\nAll {len(tests)} tests passed.")
