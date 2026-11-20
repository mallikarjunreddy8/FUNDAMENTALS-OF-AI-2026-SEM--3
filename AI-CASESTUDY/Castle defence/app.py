"""Solara front-end for "Castle Defence: Search Algorithm Siege".

Run with:   solara run app.py
"""

import asyncio
import os
import random
import sys
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import solara  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from board import render_board  # noqa: E402
from model import (  # noqa: E402
    ALGO_COLORS,
    ALGO_ENEMY,
    DANGER_WEIGHT,
    DIFFICULTY,
    ENEMY_TYPES,
    MOVE_COST,
    TOWER_TYPES,
    WALL_COST,
    CastleDefence,
)

TOOLS = {
    "Wall": ("🧱", WALL_COST),
    "Archer": ("🏹", TOWER_TYPES["Archer"].cost),
    "Cannon": ("💣", TOWER_TYPES["Cannon"].cost),
    "Sell": ("💰", None),
}
DFS_ORDERS = ["Toward the castle", "Random (textbook)"]

# New-game settings
difficulty = solara.reactive("Normal")
n_waves = solara.reactive(10)
rock_density = solara.reactive(0.08)
mud_density = solara.reactive(0.08)
dfs_order = solara.reactive(DFS_ORDERS[0])
seed = solara.reactive(7)

# View and play state
tool = solara.reactive("Archer")
show_search = solara.reactive("Off")
show_routes = solara.reactive(True)
show_ranges = solara.reactive(False)
show_danger = solara.reactive(False)
auto_next = solara.reactive(False)
playing = solara.reactive(False)
speed = solara.reactive(4)  # turns per second
panel = solara.reactive("📊 Algorithms")

game = solara.reactive(None)  # created per browser session, in Page()
version = solara.reactive(0)  # bumped after every in-place change to the model


def build_game():
    return CastleDefence(
        n_waves=n_waves.value,
        difficulty=difficulty.value,
        rock_density=rock_density.value,
        mud_density=mud_density.value,
        dfs_greedy=dfs_order.value == DFS_ORDERS[0],
        seed=seed.value,
    )


def refresh():
    version.value += 1


def new_game():
    playing.value = False
    game.value = build_game()
    refresh()


def random_map():
    seed.value = random.randint(0, 9999)
    new_game()


def start_wave():
    if game.value.start_wave():
        playing.value = True
    refresh()


def step_once():
    game.value.step()
    refresh()


def click_cell(data):
    m = game.value
    pos = (int(data["x"]), int(data["y"]))
    if tool.value == "Sell":
        m.sell(pos)
    else:
        m.build(tool.value, pos)
    refresh()


# ---------------------------------------------------------------- the board
@solara.component_vue("board.vue")
def BoardView(
    svg: str,
    cols: int,
    rows: int,
    ghost: str = "",
    ghost_range: float = 0,
    event_cell_click: Callable[[dict], None] = None,
):
    pass


@solara.component
def Board():
    _ = version.value
    m = game.value
    over = m.phase in ("won", "lost")
    svg = render_board(
        m,
        search=None if show_search.value == "Off" else show_search.value,
        routes=show_routes.value,
        ranges=show_ranges.value,
        danger=show_danger.value,
    )
    spec = TOWER_TYPES.get(tool.value)
    BoardView(
        svg=svg,
        cols=m.width,
        rows=m.height,
        ghost="" if over else TOOLS[tool.value][0],
        ghost_range=spec.range if spec and not over else 0,
        event_cell_click=click_cell,
    )


@solara.component
def StatusBar():
    _ = version.value
    m = game.value
    pills = [
        ("🌊 Wave", f"{m.wave}/{m.n_waves}"),
        ("🏰 Castle", f"{m.castle_hp}/{m.castle_max_hp}"),
        ("💰 Gold", f"{m.gold}"),
        ("👣 Enemies", f"{len(m.live_enemies())} on field, {len(m.spawn_queue)} to come"),
        ("⏱️ Turn", f"{m.turn}"),
    ]
    solara.HTML(
        tag="div",
        unsafe_innerHTML="".join(
            f'<span style="display:inline-block;margin:0 8px 6px 0;padding:4px 12px;'
            f'border-radius:999px;background:#f1f5f9;border:1px solid #cbd5e1;font-size:15px">'
            f"{k} <b>{v}</b></span>"
            for k, v in pills
        ),
    )
    banner = {"won": solara.Success, "lost": solara.Error, "wave": solara.Warning}.get(
        m.phase, solara.Info
    )
    banner(m.message)


@solara.component
def Controls():
    _ = version.value
    m = game.value

    async def autoplay():
        while playing.value:
            await asyncio.sleep(1 / speed.value)
            model = game.value
            if model.phase == "build" and auto_next.value:
                model.start_wave()
            elif model.phase != "wave":
                playing.value = False
                break
            else:
                model.step()
            refresh()

    solara.lab.use_task(autoplay, dependencies=[playing.value])

    over = m.phase in ("won", "lost")
    with solara.Row(gap="6px", style="flex-wrap:wrap;align-items:center"):
        for name, (icon, cost) in TOOLS.items():
            solara.Button(
                f"{icon} {name}" + (f" · {cost}g" if cost else ""),
                on_click=lambda name=name: tool.set(name),
                color="primary" if tool.value == name else None,
                outlined=tool.value != name,
                disabled=over,
            )
    with solara.Row(gap="6px", style="flex-wrap:wrap;align-items:center"):
        if m.phase == "build":
            solara.Button(f"⚔️ Start wave {m.wave + 1}", on_click=start_wave, color="error")
        elif over:
            solara.Button("🔄 New game", on_click=new_game, color="primary")
        solara.Button(
            "⏸ Pause" if playing.value else "▶ Play",
            on_click=lambda: playing.set(not playing.value),
            disabled=m.phase != "wave",
        )
        solara.Button("⏭ Step", on_click=step_once, disabled=m.phase != "wave" or playing.value)
        with solara.Div(style="min-width:220px"):
            solara.SliderInt("Speed (turns / s)", value=speed, min=1, max=12)


@solara.component
def Legend():
    def chip(color, shape, text):
        style = {
            "circle": "border-radius:50%",
            "triangle": "clip-path:polygon(0 0,100% 50%,0 100%)",
            "square": "border-radius:3px",
        }[shape]
        return (
            f'<span style="display:inline-flex;align-items:center;margin-right:14px">'
            f'<span style="width:14px;height:14px;background:{color};{style};margin-right:5px"></span>'
            f"{text}</span>"
        )

    shapes = {"Grunt": "circle", "Raider": "triangle", "Knight": "square"}
    html = "".join(
        chip(ALGO_COLORS[s.algorithm], shapes[name], f"<b>{name}</b>&nbsp;({s.algorithm})")
        for name, s in ENEMY_TYPES.items()
    )
    html += (
        '<span style="margin-right:14px">🟫 mud (3× slower)</span>'
        '<span style="margin-right:14px">🪨 rock</span>'
        '<span style="margin-right:14px">🟪 gate</span>'
    )
    solara.HTML(tag="div", unsafe_innerHTML=html, style="font-size:14px;margin-top:6px")


# ------------------------------------------------------------- side panels
def dot(algo):
    return f'<span style="color:{ALGO_COLORS[algo]}">⬤</span>'


@solara.component
def AlgorithmStats():
    _ = version.value
    m = game.value
    rows = []
    for algo, st in m.stats.items():
        avg_nodes = st["nodes"] / st["searches"] if st["searches"] else 0
        avg_len = st["path_steps"] / st["searches"] if st["searches"] else 0
        rows.append(
            f"| {dot(algo)} {ALGO_ENEMY[algo]} | {algo} | {st['spawned']} | {st['killed']} "
            f"| {st['leaked']} | {st['searches']} | {avg_nodes:.0f} | {avg_len:.1f} |"
        )
    solara.Markdown(
        "#### ⚔️ Battle so far\n"
        "| Enemy | Search | Spawned | Killed | Got through | Searches | Nodes / search | Route length |\n"
        "|---|---|---|---|---|---|---|---|\n" + "\n".join(rows)
    )

    lab = m.compare_algorithms()
    rows = [
        f"| {dot(a)} {a} | {r['steps']} | {r['walk']} | {r['exposure']:.0f} | {r['astar_cost']:.0f} "
        f"| {r['nodes']} | {r['frontier']} | {r['ms']:.2f} |"
        for a, r in lab.items()
    ]
    solara.Markdown(
        "#### 🔬 Route check on the current map\n"
        "Each algorithm searched from all three gates to the castle (totals). "
        "Build something and watch the numbers change.\n\n"
        "| Search | Steps | Walk time | Fire exposure | A\\* cost | Nodes expanded | Peak frontier | ms |\n"
        "|---|---|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n\n"
        f"*Walk time* counts mud as {MOVE_COST['mud']}. *Fire exposure* adds up the tower damage "
        f"per turn aimed at each cell of the route. *A\\* cost* = walk time + {DANGER_WEIGHT} × "
        "fire exposure, which is what the Knights minimise: A\\* always has the lowest. "
        "BFS always has the fewest steps."
    )


@solara.component
def Charts():
    _ = version.value
    df = game.value.datacollector.get_model_vars_dataframe()
    if df.empty:
        solara.Info("Charts fill in once the first wave starts.")
        return
    fig = Figure(figsize=(6.4, 5.4), layout="constrained")
    ax1, ax2 = fig.subplots(2, 1, sharex=True)
    ax1.plot(df["Turn"], df["Castle HP"], color="#16a34a", lw=2, label="Castle HP")
    ax1.set_ylabel("Castle HP")
    ax1.set_ylim(bottom=0)
    gold_ax = ax1.twinx()
    gold_ax.plot(df["Turn"], df["Gold"], color="#ca8a04", lw=1.5, ls="--", label="Gold")
    gold_ax.set_ylabel("Gold")
    ax1.set_title("Castle HP (solid) and gold (dashed)")
    algos = list(ALGO_COLORS)
    ax2.stackplot(
        df["Turn"],
        [df[f"{a} alive"] for a in algos],
        colors=[ALGO_COLORS[a] for a in algos],
        labels=[f"{ALGO_ENEMY[a]} ({a})" for a in algos],
        alpha=0.85,
    )
    ax2.set_title("Enemies on the field")
    ax2.set_xlabel("Turn")
    ax2.legend(loc="upper left", fontsize=8)
    solara.FigureMatplotlib(fig)


@solara.component
def EventLog():
    _ = version.value
    solara.Markdown("\n".join(f"- {line}" for line in game.value.log) or "-")


@solara.component
def HowToPlay():
    tower_lines = "\n".join(
        f"- {t.icon} **{t.name}** ({t.cost}g): range {t.range:g}, {t.damage} damage every "
        f"{t.reload} turn(s){', hits nearby enemies too' if t.splash else ''}."
        for t in TOWER_TYPES.values()
    )
    enemy_lines = "\n".join(
        f"- {dot(s.algorithm)} **{name}**, {s.algorithm}: {s.blurb} "
        f"HP {s.hp}, speed {s.speed}, {s.bounty}g bounty, deals {s.damage} to the castle."
        for name, s in ENEMY_TYPES.items()
    )
    solara.Markdown(
        f"""
#### Goal
Survive every wave. Enemies leave the purple gates on the left and march on your castle.
Each one that gets in costs the castle HP.

#### Building
Pick a tool, then click the map. You can build between waves and during them.

- 🧱 **Wall** ({WALL_COST}g): blocks the way. Use walls to force long routes past your towers.
{tower_lines}
- 💰 **Sell**: click a wall or tower to get half its price back.

Walls and towers block movement, so every build makes the enemies search again.
You can't seal the castle off completely: the game runs a BFS from the castle and
refuses any build that leaves a gate or an enemy with no route.

#### The enemies and their search algorithms
{enemy_lines}

- **BFS** explores ring by ring with a queue, so it finds the route with the fewest
  steps. It treats every step as equal, so Grunts wade straight through mud and arrows.
- **DFS** dives down one branch with a stack and only backs up at dead ends. It keeps
  the first route it finds, which is usually not the shortest, but it expands very few
  cells. The "Raider DFS neighbour order" setting switches between trying the cell
  nearest the castle first and textbook random order.
- **A\\*** always expands the cell with the lowest *f = g + h*: *g* is the cost so far
  (mud costs {MOVE_COST['mud']}, cells under tower fire cost extra) and *h* is the Manhattan distance
  to the castle. It finds the cheapest route and expands far fewer cells than BFS.
  Knights steer around your towers, so funnel them with walls.

Towers also use a BFS: they shoot the enemy with the fewest steps left to the castle.

#### Tips
- Use **Show search** in the sidebar to see which cells each algorithm expanded (light)
  and the route it chose (thick line).
- Turn on the **Danger map** to see the tower fire the Knights' A\\* tries to avoid.
"""
    )


@solara.component
def ViewOptions():
    with solara.Row(gap="12px", style="flex-wrap:wrap;align-items:center"):
        with solara.Div(style="width:170px"):
            solara.Select("Show search", values=["Off", "BFS", "DFS", "A*"], value=show_search)
        solara.Checkbox(label="Enemy routes", value=show_routes)
        solara.Checkbox(label="Tower ranges", value=show_ranges)
        solara.Checkbox(label="Danger map (what A* avoids)", value=show_danger)
        solara.Checkbox(label="Auto-start next wave", value=auto_next)


@solara.component
def Settings():
    solara.Markdown("These apply when you start a new game.")
    solara.Select("Difficulty", values=list(DIFFICULTY), value=difficulty)
    solara.SliderInt("Waves", value=n_waves, min=3, max=20)
    solara.SliderFloat("Rocks", value=rock_density, min=0.0, max=0.2, step=0.02)
    solara.SliderFloat("Mud", value=mud_density, min=0.0, max=0.2, step=0.02)
    solara.Select("Raider DFS neighbour order", values=DFS_ORDERS, value=dfs_order)
    solara.InputInt("Map seed", value=seed)
    with solara.Row():
        solara.Button("🔄 New game", on_click=new_game, color="primary")
        solara.Button("🎲 Random map", on_click=random_map)


PANELS = {
    "📊 Algorithms": AlgorithmStats,
    "📈 Charts": Charts,
    "📜 Log": EventLog,
    "❓ How to play": HowToPlay,
    "⚙️ New game": Settings,
}


@solara.component
def Page():
    solara.Title("Castle Defence")

    def create_game():
        if game.value is None:
            game.value = build_game()

    solara.use_effect(create_game, [])
    if game.value is None:
        solara.Text("Raising the castle walls...")
        return

    solara.Markdown(
        "# 🏰 Castle Defence: Search Algorithm Siege\n"
        "Enemies built with **Mesa** find their way to your castle with "
        f"{dot('BFS')} **BFS**, {dot('DFS')} **DFS** and {dot('A*')} **A\\***. "
        "Build walls and towers to stop them."
    )
    StatusBar()
    with solara.Columns([3, 2], style="margin:0"):  # v-row's negative margin adds a sideways scrollbar
        with solara.Column():
            Controls()
            Board()
            Legend()
            ViewOptions()
        with solara.Column():
            with solara.Row(gap="4px", style="flex-wrap:wrap"):
                for name in PANELS:
                    solara.Button(
                        name,
                        on_click=lambda name=name: panel.set(name),
                        color="primary" if panel.value == name else None,
                        text=panel.value != name,
                    )
            PANELS[panel.value]()
