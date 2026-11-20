"""Mesa model for "Castle Defence: Search Algorithm Siege".

Enemies pour out of three gates on the left and march on the castle on the
right. Each enemy type plans its route with a different search algorithm:

  * Grunt  -- BFS: fewest steps; walks straight through mud and tower fire
  * Raider -- DFS: fast, but takes the first route it finds, often a long one
  * Knight -- A*:  cheapest route, where mud and the towers' fire zones cost extra

The player spends gold on walls and towers. Both block movement, so every
build makes the enemies search again. A build that would cut every route to
the castle is refused (checked with a BFS from the castle).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import mesa
from mesa.space import MultiGrid

from pathfinding import ALGORITHMS, DIRECTIONS, distance_field

GRASS, MUD, ROCK = "grass", "mud", "rock"
MOVE_COST = {GRASS: 1, MUD: 3}
MAX_ENERGY = max(MOVE_COST.values())
DANGER_WEIGHT = 1  # extra A* cost per point of tower damage aimed at a cell

ALGO_COLORS = {"BFS": "#2563eb", "DFS": "#ea580c", "A*": "#9333ea"}


@dataclass(frozen=True)
class EnemySpec:
    name: str
    algorithm: str
    hp: int
    speed: int  # move points per turn; grass costs 1, mud costs 3
    bounty: int
    damage: int  # castle HP lost if it gets through
    blurb: str


@dataclass(frozen=True)
class TowerSpec:
    name: str
    cost: int
    range: float
    damage: int
    reload: int  # turns between shots
    splash: int  # damage to other enemies within 1 cell of the target
    icon: str

    @property
    def dps(self):
        return self.damage / self.reload


ENEMY_TYPES = {
    "Grunt": EnemySpec("Grunt", "BFS", hp=4, speed=1, bounty=2, damage=1,
                       blurb="Marches the fewest steps, straight through mud and arrows."),
    "Raider": EnemySpec("Raider", "DFS", hp=3, speed=2, bounty=3, damage=1,
                        blurb="Fast, but follows the first route its DFS finds."),
    "Knight": EnemySpec("Knight", "A*", hp=6, speed=1, bounty=6, damage=2,
                        blurb="Plans the cheapest route, steering around mud and tower fire."),
}
ALGO_ENEMY = {spec.algorithm: name for name, spec in ENEMY_TYPES.items()}

TOWER_TYPES = {
    "Archer": TowerSpec("Archer", cost=20, range=3.0, damage=1, reload=1, splash=0, icon="🏹"),
    "Cannon": TowerSpec("Cannon", cost=45, range=2.5, damage=3, reload=2, splash=2, icon="💣"),
}
WALL_COST = 4
SELL_REFUND = 0.5
HP_GROWTH = 0.15  # enemy HP grows by this fraction of base HP each wave

DIFFICULTY = {
    "Easy": dict(gold=110, castle_hp=25, hp_scale=0.8),
    "Normal": dict(gold=80, castle_hp=20, hp_scale=1.0),
    "Hard": dict(gold=65, castle_hp=15, hp_scale=1.25),
}


def wave_roster(n):
    """Enemies in wave n (1-based). Raiders join in wave 2, Knights in wave 3."""
    return ["Grunt"] * (3 + n) + ["Raider"] * (n - 1) + ["Knight"] * max(0, (n - 1) // 2)


def generate_terrain(width, height, rng, rock_density, mud_density, keep_clear):
    """Scatter rock and mud in small random-walk blobs. Cells in keep_clear stay grass."""
    terrain = {(x, y): GRASS for x in range(width) for y in range(height)}
    for kind, density in ((ROCK, rock_density), (MUD, mud_density)):
        target = int(width * height * density)
        placed = 0
        while placed < target:
            x, y = rng.randrange(width), rng.randrange(height)
            for _ in range(rng.randint(3, 7)):
                if (x, y) not in keep_clear and terrain[(x, y)] == GRASS:
                    terrain[(x, y)] = kind
                    placed += 1
                dx, dy = rng.choice(DIRECTIONS)
                x = min(max(x + dx, 0), width - 1)
                y = min(max(y + dy, 0), height - 1)
    return terrain


# --------------------------------------------------------------------- agents
class Wall(mesa.Agent):
    """A cheap block. Enemies can't pass, so walls reshape their routes."""

    kind = "Wall"

    def __init__(self, model):
        super().__init__(model)
        self.cost = WALL_COST


class Tower(mesa.Agent):
    """Shoots the enemy in range that is closest to the castle."""

    def __init__(self, model, spec):
        super().__init__(model)
        self.spec = spec
        self.kind = spec.name
        self.cost = spec.cost
        self.cooldown = 0
        self.shots = 0
        self.kills = 0
        self.damage_dealt = 0

    def covers(self, pos):
        return math.dist(self.pos, pos) <= self.spec.range

    def step(self):
        if self.cooldown:
            self.cooldown -= 1
            return
        m = self.model
        targets = [e for e in m.live_enemies() if self.covers(e.pos)]
        if not targets:
            return
        # "First" targeting: fewest steps left to the castle, from the BFS distance field.
        target = min(targets, key=lambda e: (m.distance_to_castle(e.pos), e.hp))
        self._hit(target, self.spec.damage)
        if self.spec.splash:
            tx, ty = target.pos
            for e in m.live_enemies():
                if e is not target and max(abs(e.pos[0] - tx), abs(e.pos[1] - ty)) <= 1:
                    self._hit(e, self.spec.splash)
        m.shots.append((self.pos, target.pos, self.kind))
        self.shots += 1
        self.cooldown = self.spec.reload - 1

    def _hit(self, enemy, damage):
        dealt = min(damage, enemy.hp)
        enemy.hp -= dealt
        self.damage_dealt += dealt
        self.model.stats[enemy.algorithm]["damage_taken"] += dealt
        if enemy.hp <= 0:
            enemy.alive = False
            self.kills += 1


class Enemy(mesa.Agent):
    """Walks to the castle along the route its search algorithm found."""

    def __init__(self, model, spec, hp):
        super().__init__(model)
        self.spec = spec
        self.kind = spec.name
        self.algorithm = spec.algorithm
        self.hp = self.max_hp = hp
        self.energy = 0
        self.path = []
        self.explored = []
        self.plan_version = -1
        self.alive = True
        self.reached_castle = False
        self.steps = 0
        self.searches = 0

    def plan(self):
        m = self.model
        result = m.search(self.algorithm, self.pos, rng=self.random)
        self.path = result.path
        self.explored = result.explored
        self.plan_version = m.map_version
        self.searches += 1
        st = m.stats[self.algorithm]
        st["searches"] += 1
        st["nodes"] += len(result.explored)
        st["path_steps"] += len(result.path)

    def step(self):
        if not self.alive:
            return
        m = self.model
        # Re-plan after any build or sale: the old route may be blocked, or no longer the best.
        if not self.path or self.plan_version != m.map_version:
            self.plan()
        self.energy = min(self.energy + self.spec.speed, MAX_ENERGY)
        while self.path and self.energy >= m.move_cost(self.path[0]):
            nxt = self.path.pop(0)
            self.energy -= m.move_cost(nxt)
            m.grid.move_agent(self, nxt)
            self.steps += 1
            if nxt in m.castle_cells:
                m.enemy_reached_castle(self)
                return


# ---------------------------------------------------------------------- model
class CastleDefence(mesa.Model):
    def __init__(
        self,
        n_waves=10,
        difficulty="Normal",
        rock_density=0.08,
        mud_density=0.08,
        dfs_greedy=True,
        width=24,
        height=14,
        seed=None,
    ):
        super().__init__(rng=seed)
        cfg = DIFFICULTY[difficulty]
        self.width, self.height = width, height
        self.n_waves = n_waves
        self.dfs_greedy = dfs_greedy
        self.difficulty = difficulty
        self.hp_scale = cfg["hp_scale"]
        self.gold = cfg["gold"]
        self.castle_hp = self.castle_max_hp = cfg["castle_hp"]

        mid = height // 2
        self.gates = [(0, 2), (0, mid), (0, height - 3)]
        self.castle_cells = frozenset(
            (x, y) for x in (width - 2, width - 1) for y in (mid - 1, mid, mid + 1)
        )
        keep_clear = {
            (x + dx, y + dy)
            for x, y in [*self.gates, *self.castle_cells]
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
        }
        self.structures = {}  # pos -> Wall | Tower, for fast "is this cell blocked?"
        while True:  # re-roll the rare map where rocks cut a gate off
            self.terrain = generate_terrain(
                width, height, self.random, rock_density, mud_density, keep_clear
            )
            self.dist = distance_field(self.castle_cells, self.neighbours)
            if all(g in self.dist for g in self.gates):
                break

        self.grid = MultiGrid(width, height, torus=False)
        self.phase = "build"  # build | wave | won | lost
        self.wave = 0
        self.turn = 0
        self.spawn_queue = []
        self.spawn_every = 1
        self.spawn_timer = 0
        self.shots = []
        self.log = []
        self.message = ""
        self.map_version = 0
        self.danger = {}
        self._gate_cache = {}
        self.stats = {
            algo: dict(spawned=0, killed=0, leaked=0, searches=0, nodes=0,
                       path_steps=0, damage_taken=0)
            for algo in ALGORITHMS
        }
        self.datacollector = mesa.DataCollector(
            model_reporters={
                "Turn": lambda m: m.turn,
                "Castle HP": lambda m: m.castle_hp,
                "Gold": lambda m: m.gold,
                **{
                    f"{algo} alive": (lambda m, a=algo: sum(e.algorithm == a for e in m.live_enemies()))
                    for algo in ALGORITHMS
                },
            }
        )
        self._map_changed()
        self.say(f"Build your defences, then start wave 1 of {n_waves}.")

    # ------------------------------------------------------------- map queries
    def in_bounds(self, pos):
        return 0 <= pos[0] < self.width and 0 <= pos[1] < self.height

    def is_open(self, pos, extra_block=None):
        return (
            self.in_bounds(pos)
            and self.terrain[pos] != ROCK
            and pos not in self.structures
            and pos != extra_block
        )

    def neighbours(self, pos, extra_block=None):
        x, y = pos
        for dx, dy in DIRECTIONS:
            nxt = (x + dx, y + dy)
            if self.is_open(nxt, extra_block):
                yield nxt

    def move_cost(self, pos):
        return MOVE_COST[self.terrain[pos]]

    def route_cost(self, pos):
        """What a step onto pos costs an A* Knight: walking time plus tower fire."""
        return self.move_cost(pos) + DANGER_WEIGHT * self.danger.get(pos, 0)

    def distance_to_castle(self, pos):
        return self.dist.get(pos, math.inf)

    def search(self, algorithm, start, rng=None):
        extra = {"greedy": self.dfs_greedy} if algorithm == "DFS" else {}
        return ALGORITHMS[algorithm](
            start, self.castle_cells, self.neighbours, cost=self.route_cost, rng=rng, **extra
        )

    def gate_searches(self, algorithm):
        """The route each gate's next spawn would take. Cached until the map changes."""
        key = (algorithm, self.map_version)
        if key not in self._gate_cache:
            rng = random.Random(0)  # fixed, so the DFS preview doesn't flicker
            self._gate_cache[key] = [(g, self.search(algorithm, g, rng)) for g in self.gates]
        return self._gate_cache[key]

    def compare_algorithms(self):
        """Totals over all three gates, for the algorithm comparison table."""
        rows = {}
        for algo in ALGORITHMS:
            row = dict(steps=0, walk=0, exposure=0.0, astar_cost=0.0, nodes=0, frontier=0, ms=0.0)
            for _, res in self.gate_searches(algo):
                row["steps"] += len(res.path)
                row["walk"] += sum(self.move_cost(p) for p in res.path)
                row["exposure"] += sum(self.danger.get(p, 0) for p in res.path)
                row["astar_cost"] += sum(self.route_cost(p) for p in res.path)
                row["nodes"] += len(res.explored)
                row["frontier"] = max(row["frontier"], res.max_frontier)
                row["ms"] += res.seconds * 1000
            rows[algo] = row
        return rows

    def live_enemies(self):
        return [e for e in self.agents if isinstance(e, Enemy) and e.alive]

    def towers(self):
        return [s for s in self.structures.values() if isinstance(s, Tower)]

    # ---------------------------------------------------------------- building
    def build_problem(self, pos):
        """Why pos can't be built on, or None if it can."""
        if not self.in_bounds(pos):
            return "That's off the map."
        if pos in self.castle_cells:
            return "That's your castle."
        if pos in self.gates:
            return "You can't build on an enemy gate."
        if self.terrain[pos] == ROCK:
            return "There's a rock in the way."
        if pos in self.structures:
            return "Something is already built there."
        enemies = self.live_enemies()
        if any(e.pos == pos for e in enemies):
            return "An enemy is standing there."
        # The new block must leave every gate and every enemy a route to the castle.
        dist = distance_field(self.castle_cells, lambda p: self.neighbours(p, extra_block=pos))
        if any(g not in dist for g in self.gates) or any(e.pos not in dist for e in enemies):
            return "That would wall the castle off completely. Leave the enemies a route."
        return None

    def build(self, kind, pos):
        cost = WALL_COST if kind == "Wall" else TOWER_TYPES[kind].cost
        if self.phase in ("won", "lost"):
            return False
        if self.gold < cost:
            self.message = f"Not enough gold: a {kind} costs {cost}g and you have {self.gold}g."
            return False
        problem = self.build_problem(pos)
        if problem:
            self.message = problem
            return False
        agent = Wall(self) if kind == "Wall" else Tower(self, TOWER_TYPES[kind])
        self.grid.place_agent(agent, pos)
        self.structures[pos] = agent
        self.gold -= cost
        self._map_changed()
        self.message = f"Built {'an' if kind[0] in 'AEIOU' else 'a'} {kind} at {pos} for {cost}g."
        return True

    def sell(self, pos):
        agent = self.structures.get(pos)
        if agent is None or self.phase in ("won", "lost"):
            self.message = "Nothing to sell there."
            return False
        refund = int(agent.cost * SELL_REFUND)
        del self.structures[pos]
        self.grid.remove_agent(agent)
        agent.remove()
        self.gold += refund
        self._map_changed()
        self.message = f"Sold the {agent.kind} for {refund}g."
        return True

    def _map_changed(self):
        self.map_version += 1
        self.danger = {}
        for tower in self.towers():
            r = int(tower.spec.range)
            tx, ty = tower.pos
            for x in range(tx - r, tx + r + 1):
                for y in range(ty - r, ty + r + 1):
                    if self.in_bounds((x, y)) and tower.covers((x, y)):
                        self.danger[(x, y)] = self.danger.get((x, y), 0) + tower.spec.dps
        self.dist = distance_field(self.castle_cells, self.neighbours)
        self._gate_cache.clear()

    # ------------------------------------------------------------------ turns
    def start_wave(self):
        if self.phase != "build":
            return False
        self.wave += 1
        self.phase = "wave"
        roster = wave_roster(self.wave)
        parts = ", ".join(f"{roster.count(k)} {k}s" for k in ENEMY_TYPES if k in roster)
        self.say(f"Wave {self.wave} incoming: {parts}.")
        self.random.shuffle(roster)
        self.spawn_queue = roster
        self.spawn_every = 2 if self.wave <= 2 else 1
        self.spawn_timer = 0
        self._spawn()
        return True

    def step(self):
        if self.phase != "wave":
            return
        self.turn += 1
        self.shots = []
        self.agents.select(agent_type=Enemy).shuffle_do("step")  # move
        self.agents.select(agent_type=Tower).do("step")  # fire
        self._remove_fallen()
        self._spawn()
        self._check_end()
        self.datacollector.collect(self)

    def enemy_reached_castle(self, enemy):
        enemy.alive = False
        enemy.reached_castle = True
        self.castle_hp = max(0, self.castle_hp - enemy.spec.damage)
        self.stats[enemy.algorithm]["leaked"] += 1
        self.say(f"A {enemy.kind} ({enemy.algorithm}) hit the castle for {enemy.spec.damage}!")

    def _remove_fallen(self):
        for enemy in [a for a in self.agents if isinstance(a, Enemy) and not a.alive]:
            if not enemy.reached_castle:
                self.gold += enemy.spec.bounty
                self.stats[enemy.algorithm]["killed"] += 1
            self.grid.remove_agent(enemy)
            enemy.remove()

    def _spawn(self):
        self.spawn_timer -= 1
        if not self.spawn_queue or self.spawn_timer > 0:
            return
        self.spawn_timer = self.spawn_every
        spec = ENEMY_TYPES[self.spawn_queue.pop(0)]
        hp = max(1, round(spec.hp * self.hp_scale * (1 + HP_GROWTH * (self.wave - 1))))
        enemy = Enemy(self, spec, hp)
        self.grid.place_agent(enemy, self.random.choice(self.gates))
        self.stats[spec.algorithm]["spawned"] += 1

    def _check_end(self):
        if self.castle_hp <= 0:
            self.phase = "lost"
            self.running = False
            self.say(f"The castle has fallen in wave {self.wave}. Game over.")
        elif not self.spawn_queue and not self.live_enemies():
            if self.wave >= self.n_waves:
                self.phase = "won"
                self.running = False
                self.say(f"Victory! The castle held all {self.n_waves} waves "
                         f"with {self.castle_hp}/{self.castle_max_hp} HP left.")
            else:
                bonus = 10 + 2 * self.wave
                self.gold += bonus
                self.phase = "build"
                self.shots = []
                self.say(f"Wave {self.wave} cleared! +{bonus}g bonus. Build, then start wave {self.wave + 1}.")

    def say(self, text):
        self.message = text
        self.log.insert(0, f"T{self.turn}: {text}")
        del self.log[30:]
