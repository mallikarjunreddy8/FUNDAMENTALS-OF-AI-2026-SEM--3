"""
Rat Escape - the game logic (built with Mesa 3.x).

A rat must get out of a maze through a gap in the outer wall without being caught by cats.

The rat can be driven by you (arrow keys) or by an AI search method:
    BFS  - queue (first in, first out): explores ring by ring, always finds a shortest path
    DFS  - stack (last in, first out): dives down one corridor, the path may be longer
    A*   - priority queue on f(n) = g(n) + h(n): heads for the exit, always finds a shortest path

The cats are AI agents too:
    - they chase the rat with A* when they can see it
    - they remember where they last saw it (INVESTIGATE)
    - a hunter cat wanders the maze, the guard cat patrols near the exit

The maze itself is generated with a randomised DFS ("recursive backtracker").

This file has no web page code; app.py draws everything.
"""

import heapq
import itertools
from collections import deque

import mesa


# =============================================================================
# SETTINGS YOU CAN CHANGE
# (stop the game, change a value, save, start the game again)
# =============================================================================

RAT_ICON = "🐀"            # picture of the rat
HUNTER_ICON = "🐱"         # picture of a hunter cat
GUARD_ICON = "😼"          # picture of the guard cat

START = (1, 1)             # where the rat starts (x, y): must be an ODD x and ODD y inside the maze

GUARD_INDEX = 1            # which cat is the guard: 0 = 1st cat, 1 = 2nd cat, ... (the others are hunters)
GUARD_ZONE = 3             # the guard patrols within this many squares of the exit

DANGER_DISTANCE = 1        # the AI rat avoids squares this close to a cat it can see
                           # (1 = the cat's square and the 4 squares next to it)

TIRED_FACTOR = 1           # the rat gets tired after TIRED_FACTOR x size x size moves
                           # (e.g. 2 = twice as long before the game ends as TIRED)


# =============================================================================
# FIXED VALUES
# =============================================================================

# The four moves on the grid: (change in x, change in y)
MOVES = {"up": (0, -1), "right": (1, 0), "down": (0, 1), "left": (-1, 0)}

# The search methods shown in the dropdown
METHODS = ["BFS", "DFS", "A*"]


# =============================================================================
# SMALL HELPERS
# =============================================================================

def manhattan(a, b):
    """Manhattan distance |x1 - x2| + |y1 - y2|.
    This is the A* heuristic h(n): it never over-estimates the real distance on a grid."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def make_maze(size, loops, rng):
    """Build a random maze and return the set of wall squares.

    1. Randomised DFS ("recursive backtracker"): start with every square a wall, then carve
       a tunnel from START, always going deeper into an unvisited cell (2 squares away)
       and backtracking at dead ends. This gives a perfect maze (exactly one route).
    2. Knock down some extra inner walls (loops = fraction removed) so there are several
       routes, and choosing the shortest one actually matters.
    """
    walls = {(x, y) for x in range(size) for y in range(size)}
    walls.discard(START)
    stack = [START]                      # the DFS stack

    while stack:
        x, y = stack[-1]

        # Unvisited cells 2 squares away, still inside the outer wall
        options = [
            (dx, dy) for dx, dy in MOVES.values()
            if 0 < x + 2 * dx < size - 1
            and 0 < y + 2 * dy < size - 1
            and (x + 2 * dx, y + 2 * dy) in walls
        ]

        if options:
            dx, dy = rng.choice(options)
            walls -= {(x + dx, y + dy), (x + 2 * dx, y + 2 * dy)}   # remove the wall between and the cell
            stack.append((x + 2 * dx, y + 2 * dy))                  # go deeper
        else:
            stack.pop()                                             # dead end: backtrack

    # Extra openings: remove a fraction of the inner walls
    inner = sorted(w for w in walls if 0 < w[0] < size - 1 and 0 < w[1] < size - 1)
    walls -= set(rng.sample(inner, int(loops * len(inner))))

    return walls


def steps_from(starts, walls, size):
    """Breadth-first search from one or more squares.
    Returns {square: number of moves needed to reach it}.
    The fleeing rat uses this to find the square the cats need the most moves to reach."""

    steps = {s: 0 for s in starts}
    queue = deque(starts)

    while queue:
        cur = queue.popleft()
        for dx, dy in MOVES.values():
            nxt = (cur[0] + dx, cur[1] + dy)
            inside = 0 <= nxt[0] < size and 0 <= nxt[1] < size
            if inside and nxt not in walls and nxt not in steps:
                steps[nxt] = steps[cur] + 1
                queue.append(nxt)

    return steps


# =============================================================================
# THE SEARCH (BFS, DFS and A* share this one class)
# =============================================================================

class Search:
    """A search that runs ONE square at a time, so you can watch it on the board.

    BFS, DFS and A* use exactly the same loop (see step()).
    The ONLY difference is the frontier, the list of squares waiting to be explored:
        BFS -> queue           (take the OLDEST square first)
        DFS -> stack           (take the NEWEST square first)
        A*  -> priority queue  (take the square with the LOWEST f = g + h first)
    """

    def __init__(self, method, start, goal, blocked, size):
        self.method = method          # "BFS", "DFS" or "A*"
        self.start = start
        self.goal = goal
        self.blocked = blocked        # squares the search may not enter (walls, and squares near cats)
        self.size = size

        self.order = itertools.count()                          # A* tie-breaker for equal f values
        self.frontier = deque() if method == "BFS" else []      # queue for BFS, list for DFS and A*

        self.parent = {}              # explored square -> the square we reached it from
        self.explored = []            # explored squares, in order (drawn on the board)
        self.path = None              # the route to the goal, once found

        self.push(start, None, 0)

    # --- the frontier: the only part that differs between the three methods --

    def push(self, node, came_from, g):
        """Add a square to the frontier. g = number of steps from the start."""
        if self.method == "A*":
            h = manhattan(node, self.goal)                      # estimated steps left
            heapq.heappush(self.frontier, (g + h, h, next(self.order), node, came_from, g))
        else:
            self.frontier.append((node, came_from, g))

    def pop(self):
        """Take the next square out of the frontier."""
        if self.method == "A*":
            return heapq.heappop(self.frontier)[3:]             # lowest f = g + h
        if self.method == "BFS":
            return self.frontier.popleft()                      # queue: oldest first
        return self.frontier.pop()                              # DFS stack: newest first

    # --- the shared search loop -----------------------------------------------

    @property
    def done(self):
        """Finished when the goal is found or there is nothing left to explore."""
        return self.path is not None or not self.frontier

    def step(self):
        """Explore ONE square: take it from the frontier, check for the goal, add its open neighbours."""
        while self.frontier:
            node, came_from, g = self.pop()

            if node in self.parent:
                continue                                        # already explored: skip it

            self.parent[node] = came_from
            self.explored.append(node)

            # Goal found: follow the parent links back to build the path
            if node == self.goal:
                self.path = []
                while node != self.start:
                    self.path.append(node)
                    node = self.parent[node]
                self.path.reverse()
                return

            # Add every open neighbour to the frontier
            for dx, dy in MOVES.values():
                nxt = (node[0] + dx, node[1] + dy)
                inside = 0 <= nxt[0] < self.size and 0 <= nxt[1] < self.size
                if inside and nxt not in self.blocked and nxt not in self.parent:
                    self.push(nxt, node, g + 1)
            return

    def frontier_cells(self):
        """The squares waiting in the frontier (outlined on the board)."""
        return {entry[3] if self.method == "A*" else entry[0] for entry in self.frontier}

    def run(self):
        """Run the whole search at once (used for replanning and for the cats)."""
        while not self.done:
            self.step()
        return self


# =============================================================================
# THE RAT (Mesa agent)
# =============================================================================

class Rat(mesa.Agent):
    """You, or the AI.

    When the AI drives, the rat goes through these states:
        SEARCH  - the chosen method looks for a route to the exit, one square per step,
                  treating the cats it can SEE (and the squares next to them) as walls
        WALK    - follow the route, one square per step
        REPLAN  - a cat moved into the route: search again (instantly)
        FLEE    - every route passes a cat: move (or wait) where the cats need the most moves to reach
    The AI rat only knows about the cats within its own sight, so it can walk into an ambush.
    """

    icon = RAT_ICON

    def __init__(self, model):
        super().__init__(model)
        self.reset()

    def reset(self):
        """Forget any AI plan (new game, back to start, or you took over with the arrows)."""
        self.search = None            # the current Search (or None)
        self.route = []               # squares still to walk
        self.explored_total = 0       # squares explored by all searches this game
        self.replans = 0              # how many times the AI had to think again
        self.fleeing = False          # True while running away from a cat

    def drive(self, method):
        """Let the AI drive with the chosen method, starting from where the rat stands."""
        m = self.model
        self.search = Search(method, self.pos, m.exit, m.walls | m.danger(), m.size)
        self.route = []
        self.fleeing = False
        m.ai_from = m.ai_from or self.pos         # remember the AI is driving (for the compare table)

    def replan(self):
        """A cat is in the way: think again (instantly) with the same method."""
        m = self.model

        s = Search(self.search.method, self.pos, m.exit, m.walls | m.danger(), m.size).run()
        self.search = s
        self.replans += 1
        self.explored_total += len(s.explored)

        # A safe route exists: walk it
        if s.path:
            self.route = list(s.path)
            self.fleeing = False
            return

        # No safe route: FLEE to (or stay on) the square the visible cats need the most moves to reach
        cat_steps = steps_from([c.pos for c in m.visible_cats()], m.walls, m.size)   # BFS from the cats

        x, y = self.pos
        options = [self.pos] + [
            (x + dx, y + dy) for dx, dy in MOVES.values() if (x + dx, y + dy) not in m.walls
        ]
        self.route = [max(options, key=lambda p: (cat_steps.get(p, 999), self.random.random()))]
        self.fleeing = True

    def step(self):
        """One AI step: either explore one square of the search, or walk one square."""
        m = self.model

        # 1) SEARCH: explore one more square
        if self.search and not self.search.done:
            self.search.step()

            if self.search.done:
                self.explored_total += len(self.search.explored)
                if self.search.path is None:
                    self.replan()                     # the cats block every route for now
                else:
                    self.route = list(self.search.path)

        # 2) WALK: one square along the route (replanning first if a cat is in the way)
        elif self.route or self.fleeing:
            if self.fleeing or self.route[0] in m.danger():
                self.replan()
            m.rat_moves(self.route.pop(0))


# =============================================================================
# THE CATS (Mesa agents)
# =============================================================================

class Cat(mesa.Agent):
    """A cat moves once after every rat move (and rests now and then, depending on the level).

    States:
        CHASE (A*)   - it sees the rat: A* straight at it
        INVESTIGATE  - it lost sight of the rat: A* to where it last saw it (memory)
        WANDER       - a hunter with nothing to do roams the maze
        GUARD        - the guard with nothing to do patrols near the exit (ambush)
    """

    icons = {"hunter": HUNTER_ICON, "guard": GUARD_ICON}

    def __init__(self, model, role, home):
        super().__init__(model)
        self.role = role              # "hunter" or "guard"
        self.home = home              # starting square (the guard returns here)
        self.icon = self.icons[role]
        self.reset()

    def reset(self):
        self.path = []                # current A* route (drawn in red on the board)
        self.prev = None              # last square (so a wandering cat avoids turning back)
        self.last_seen = None         # memory: where the rat was last seen
        self.state = "GUARD" if self.role == "guard" else "WANDER"

    def sees_rat(self):
        """PERCEIVE: is the rat within this cat's sight?"""
        return manhattan(self.pos, self.model.rat.pos) <= self.model.cat_sight

    def walk_to(self, goal):
        """Plan an A* route to goal and return the first square of it (cats never step into the exit)."""
        m = self.model
        self.path = Search("A*", self.pos, goal, m.walls | {m.exit}, m.size).run().path or []
        return self.path.pop(0) if self.path else None

    def step(self):
        """DECIDE and ACT: choose a state and take one step."""
        m = self.model
        self.path = []

        # It can see the rat: CHASE with A*
        if self.sees_rat():
            self.state = "CHASE (A*)"
            self.last_seen = m.rat.pos
            nxt = self.walk_to(m.rat.pos) if m.rat.pos != m.exit else None

        # It lost the rat: go to where it last saw it
        elif self.last_seen:
            self.state = "INVESTIGATE"
            nxt = self.walk_to(self.last_seen)
            if nxt is None or nxt == self.last_seen:
                self.last_seen = None                 # nothing there: give up

        # The guard is too far from the exit: go back to its post
        elif self.role == "guard" and manhattan(self.pos, m.exit) > GUARD_ZONE:
            self.state = "GUARD"
            nxt = self.walk_to(self.home)

        # Nothing to do: a hunter WANDERS anywhere, the guard wanders within GUARD_ZONE of the exit
        else:
            self.state = "GUARD" if self.role == "guard" else "WANDER"
            x, y = self.pos
            options = [
                (x + dx, y + dy) for dx, dy in MOVES.values()
                if (x + dx, y + dy) not in m.walls
                and (x + dx, y + dy) != m.exit
                and (self.role == "hunter" or manhattan((x + dx, y + dy), m.exit) <= GUARD_ZONE)
            ]
            forward = [p for p in options if p != self.prev] or options     # avoid turning back
            nxt = self.random.choice(forward) if forward else None

        # ACT: take the step
        if nxt:
            self.prev = self.pos
            m.grid.move_agent(self, nxt)


# =============================================================================
# THE GAME (Mesa model)
# =============================================================================

class MazeEscapeModel(mesa.Model):
    """The whole game: the maze, the rat, the cats, and the rules.

    Settings (app.py passes these in from the level):
        size       - grid size (odd number)
        loops      - extra openings in the maze (0 to 0.3)
        cats       - number of cats (cat number GUARD_INDEX is the guard)
        cat_sight  - how far a cat sees the rat
        cat_rests  - the cats skip every Nth turn (0 = never rest)
        rat_sight  - how far the AI rat sees the cats
        seed       - fix the random numbers (same seed = same maze)
    """

    def __init__(self, size=15, loops=0.12, cats=2, cat_sight=5, cat_rests=3, rat_sight=6, seed=None):
        super().__init__(seed=seed)

        self.size = size
        self.cat_sight = cat_sight
        self.cat_rests = cat_rests
        self.rat_sight = rat_sight

        # --- The maze ---------------------------------------------------------
        self.walls = make_maze(size, loops, self.random)
        self.grid = mesa.space.MultiGrid(size, size, torus=False)
        self.start = START

        # --- The exit: a gap in the outer wall, far from the start ------------
        gaps = [(x, y) for x in range(1, size - 1) for y in range(1, size - 1) if (x, y) not in self.walls]
        border = (
            [(0, y) for x, y in gaps if x == 1]                 # left wall
            + [(size - 1, y) for x, y in gaps if x == size - 2]   # right wall
            + [(x, 0) for x, y in gaps if y == 1]                 # top wall
            + [(x, size - 1) for x, y in gaps if y == size - 2]   # bottom wall
        )
        far = [b for b in border if manhattan(b, self.start) >= size - 1]
        self.exit = self.random.choice(far or border)
        self.walls.discard(self.exit)

        # --- Where the cats start ---------------------------------------------
        away = [c for c in gaps if manhattan(c, self.start) >= size // 2]           # not near the rat
        middle = [c for c in away if manhattan(c, self.exit) >= size // 3] or away  # hunters
        near_exit = sorted(away, key=lambda c: manhattan(c, self.exit))[:4]         # the guard

        # --- The agents ------------------------------------------------------
        self.rat = Rat(self)
        self.grid.place_agent(self.rat, self.start)

        self.cats = []
        for i in range(cats):
            role = "guard" if i == GUARD_INDEX else "hunter"
            home = self.random.choice(near_exit if role == "guard" else middle)
            cat = Cat(self, role, home)
            self.grid.place_agent(cat, home)
            self.cats.append(cat)

        self.runs = []                # one row per finished AI run (the compare table)
        self.restart()

    def restart(self):
        """Back to the start of the SAME maze (used by ↩ Back to start)."""
        self.grid.move_agent(self.rat, self.start)
        self.rat.reset()

        for cat in self.cats:
            self.grid.move_agent(cat, cat.home)
            cat.reset()

        self.moves = 0
        self.status = "READY"         # READY -> PLAYING -> ESCAPED / CAUGHT / TIRED
        self.ai_from = None           # where the AI took over (None = you are driving)

    # --- What the rat can perceive ---------------------------------------------

    def visible_cats(self):
        """The cats the rat can see (the AI rat only avoids these)."""
        return [c for c in self.cats if manhattan(c.pos, self.rat.pos) <= self.rat_sight]

    def danger(self):
        """Squares the AI rat avoids: every square within DANGER_DISTANCE of a visible cat."""
        r = DANGER_DISTANCE
        cells = set()
        for c in self.visible_cats():
            x, y = c.pos
            cells |= {(x + dx, y + dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1)
                      if abs(dx) + abs(dy) <= r}
        return cells

    def shortest_from(self, pos):
        """Length of the shortest way out from pos, ignoring the cats (BFS always finds a shortest path)."""
        return len(Search("BFS", pos, self.exit, self.walls, self.size).run().path)

    # --- The rules ---------------------------------------------------------------

    def caught(self):
        return any(c.pos == self.rat.pos for c in self.cats)

    def rat_moves(self, pos):
        """The rat steps to pos, then each cat takes its turn."""
        self.grid.move_agent(self.rat, pos)
        self.moves += 1
        self.status = "PLAYING"

        # Win: reached the exit
        if pos == self.exit:
            return self.finish("ESCAPED")

        # Lose: walked onto a cat
        if self.caught():
            return self.finish("CAUGHT")

        # The cats' turn (unless this is a rest turn)
        cats_rest = self.cat_rests and self.moves % self.cat_rests == 0
        if not cats_rest:
            for cat in self.cats:
                cat.step()
                if self.caught():
                    return self.finish("CAUGHT")

        # Lose: an endless chase, the rat gets too tired
        if self.moves >= TIRED_FACTOR * self.size * self.size:
            self.finish("TIRED")

    def finish(self, status):
        """End the game. If the AI was driving, add a row to the compare table."""
        self.status = status
        s = self.rat.search

        if s and self.ai_from is not None:
            self.runs.append({
                "method": s.method,
                "result": status,
                "explored": self.rat.explored_total,
                "moves": self.moves,
                "best": self.shortest_from(self.start),
                "replans": self.rat.replans,
            })

    # --- Controls --------------------------------------------------------------

    def move_rat(self, direction):
        """Arrow navigator: you move the rat yourself (any AI plan is cancelled)."""
        if self.status not in ("READY", "PLAYING"):
            return

        dx, dy = MOVES[direction]
        new = (self.rat.pos[0] + dx, self.rat.pos[1] + dy)

        inside = 0 <= new[0] < self.size and 0 <= new[1] < self.size
        if new in self.walls or not inside:
            return                                      # bumped into a wall: doesn't count

        self.rat.reset()
        self.ai_from = None
        self.rat_moves(new)

    def ai_busy(self):
        """Is the AI still working (searching, walking or fleeing)?"""
        r = self.rat
        searching = r.search is not None and not r.search.done
        return self.status in ("READY", "PLAYING") and (bool(r.route) or r.fleeing or searching)

    def step(self):
        """One Mesa step: the rat's AI explores or walks one square (the cats answer each rat move)."""
        self.agents.select(agent_type=Rat).do("step")
