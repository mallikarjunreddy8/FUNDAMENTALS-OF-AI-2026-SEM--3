"""
Rat Escape - the web page.

This file builds everything you see in the browser:
    - the maze board
    - the arrow buttons and keyboard control
    - the AI controls (method dropdown, Run to end, Step)
    - the settings (level, number of cats, grid size, openings)
    - the compare table that names the best method

The game logic itself (maze, rat, cats, BFS / DFS / A*) lives in model.py.

Run with:
    venv\\Scripts\\python -m solara run app.py
Then open http://localhost:8765
"""

import threading
import time

import solara

from model import METHODS, MazeEscapeModel, manhattan


# =============================================================================
# SETTINGS YOU CAN CHANGE
# (stop the game, change a value, save, start the game again)
# =============================================================================

DEFAULT_SIZE = 15    # starting grid size (must be an ODD number: 7, 9, 11 ... 41)
MIN_SIZE = 7               # smallest grid allowed by the slider
MAX_SIZE = 41              # biggest grid allowed by the slider

DEFAULT_LEVEL = "Normal"   # starting level: "Easy", "Normal" or "Hard"
DEFAULT_METHOD = "A*"      # starting search method: "BFS", "DFS" or "A*"
MAX_CATS = 4               # most cats the slider allows

DEFAULT_OPENINGS = 0.12    # extra openings in the maze (0 = no extra routes, 0.3 = many routes)
DEFAULT_SPEED = 0.05       # seconds between AI steps (bigger = slower)

# Each level sets:
#   cats      - how many cats (the 2nd cat is the guard)
#   cat_sight - how far a cat can see the rat (in squares)
#   cat_rests - a cat skips every Nth turn (0 = never rests)
#   rat_sight - how far the AI rat can see the cats
LEVELS = {
    "Easy":   dict(cats=1, cat_sight=4, cat_rests=2, rat_sight=8),
    "Normal": dict(cats=2, cat_sight=5, cat_rests=3, rat_sight=7),
    "Hard":   dict(cats=3, cat_sight=6, cat_rests=4, rat_sight=5),
}

# The text shown for each level (keep it in step with LEVELS above)
LEVEL_INFO = {
    "Easy":   "cats see 4 squares and rest every 2nd turn; the rat sees 8",
    "Normal": "cats see 5 squares and rest every 3rd turn; the rat sees 7",
    "Hard":   "cats see 6 squares and rest every 4th turn; the rat sees only 5",
}

# Colour used to draw each search method on the board and in the table
COLORS = {
    "BFS": "#1c7ed6",   # blue
    "DFS": "#9c36b5",   # purple
    "A*":  "#e8590c",   # orange
}


# =============================================================================
# FIXED VALUES
# =============================================================================

# Only one thread may use the model at a time:
# the AI thread (moving the rat) and the drawing code never touch it together.
LOCK = threading.Lock()

# Keyboard keys -> rat moves (arrow keys and W A S D)
KEYS = {
    "ArrowUp": "up", "ArrowDown": "down", "ArrowLeft": "left", "ArrowRight": "right",
    "w": "up", "s": "down", "a": "left", "d": "right",
}

# Page styling (CSS) for the board, the stat boxes and the compare table
CSS = """
.escape { max-width: 1100px; margin: 0 auto; padding: 16px; font-family: system-ui, sans-serif; }
.escape h1 { margin: 0 0 4px; }

.board { display: grid; gap: 1px; background: #cfc8b8; border-radius: 8px; overflow: hidden; }
.cell { aspect-ratio: 1; display: flex; align-items: center; justify-content: center;
        font-size: var(--fs); line-height: 1; background: #fbf8f0; }
.cell.wall { background: #3b3f45; }

.stats { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0; }
.stats div { flex: 1; min-width: 80px; background: white; border-radius: 10px; padding: 6px 8px;
             box-shadow: 0 1px 4px rgba(0,0,0,.1); text-align: center; font-size: 12px; color: #666; }
.stats b { display: block; font-size: 18px; color: #222; }

.runs { width: 100%; border-collapse: collapse; font-size: 14px; }
.runs th, .runs td { padding: 5px 8px; border-bottom: 1px solid #eee; text-align: left; }
"""


# =============================================================================
# HELP TEXT (shown in the fold-out panels at the bottom of the page)
# =============================================================================

HOW_TO_PLAY = """
- Get the **rat 🐀** out of the maze through the **gap in the outer wall 🚪**, without being caught by the **cats**.
- Every time the rat moves, the cats move too. Each cat:
  - **sees** the rat (pink area) → **CHASE** it with **A\\***
  - lost sight of it → **INVESTIGATE** the last place it saw the rat (memory)
  - otherwise: a **hunter 🐱** wanders the maze, the **guard 😼** (2nd cat) patrols near the exit
- The AI rat only knows about the cats **it can see** (rat sight depends on the level), so it can walk into an ambush.
- **🎮 Drive yourself:** arrow buttons, or click the maze and use the **arrow keys / W A S D**.
- **🤖 Let the AI drive:** pick **BFS, DFS or A\\*** and press **▶ Run to end**, or **⏭ Step** for one step at a time.
  The AI searches for a route **around the cats it can see**, walks it, and **replans** if a cat gets in the way.
  If every route passes a cat, it flees to the square the cats need the most moves to reach.
- You can mix: walk part of the way yourself, then let the AI finish.
- **↩ Back to start** tries again on the **same maze**: compare the methods in the table.
- You lose if the cat catches you, or if the chase goes on too long and the rat gets tired (size × size moves).
"""

METHODS_HELP = """
| | **BFS** (breadth-first) | **DFS** (depth-first) | **A\\*** |
|---|---|---|---|
| **Frontier** | Queue: first in, first out | Stack: last in, first out | Priority queue: lowest `f(n) = g(n) + h(n)` |
| **How it searches** | Ring by ring, outward | Dives down one corridor, backtracks at dead ends | Towards the exit first |
| **Shortest path?** | ✅ Always | ❌ Not guaranteed | ✅ Always |
| **Squares explored** | Most | In between (luck) | Fewest |
| **Used by** | Rat (if chosen) · rat fleeing (distance from the cats) | Rat (if chosen) · builds the maze | Rat (if chosen) · **every cat move** |

`g(n)` = steps from where the search started, `h(n)` = Manhattan distance `|x1 - x2| + |y1 - y2|` to the goal.
All three share the same search loop; only the frontier is different.
The rat's searches treat each visible cat and the squares next to it as walls, so the route goes around them.
"""

CAT_STATES = """
| Cat state | When | What it does |
|---|---|---|
| **CHASE (A\\*)** | It sees the rat | A\\* straight to the rat |
| **INVESTIGATE** | It just lost sight of the rat | A\\* to the last place it saw the rat |
| **WANDER** | Hunter 🐱 with nothing to do | Roams the maze |
| **GUARD** | Guard 😼 with nothing to do | Patrols within 3 squares of the exit |
"""


# =============================================================================
# DRAWING THE MAZE BOARD
# =============================================================================

def board_html(model, show_search, show_sight):
    """Build the maze as an HTML grid: one coloured square (div) per cell."""

    rat = model.rat

    # --- What to highlight -------------------------------------------------
    search = rat.search if show_search else None            # the rat's current search (if shown)
    color = COLORS[search.method] if search else ""         # colour of that search method

    explored = set(search.explored) if search else set()    # squares the search has explored
    frontier = search.frontier_cells() if search and not search.done else set()  # waiting to be explored
    route = set(rat.route) if not rat.fleeing else set()    # the path the rat will walk

    chase = {p for c in model.cats for p in c.path} if show_search else set()  # cats' A* routes
    cat_at = {c.pos: c for c in model.cats}                 # which cat stands on which square

    # --- Draw every square, row by row -------------------------------------
    cells = []

    for y in range(model.size):
        for x in range(model.size):
            pos = (x, y)

            # Walls are simply dark squares
            if pos in model.walls:
                cells.append('<div class="cell wall"></div>')
                continue

            # Background: explored by the search, or inside a cat's sight (pink)
            cat_can_see = show_sight and any(manhattan(pos, c.pos) <= model.cat_sight for c in model.cats)
            if pos in explored:
                style = f"background:{color}38"   # "38" makes the colour see-through
            elif cat_can_see:
                style = "background:#ffe3e3"
            else:
                style = ""

            # Outline: the search frontier, or a cat's chase route (red)
            if pos in frontier:
                style += f";box-shadow: inset 0 0 0 2px {color}"
            elif pos in chase:
                style += ";box-shadow: inset 0 0 0 2px #e03131"

            # Picture on the square (rat, cat, exit, start, or a path dot)
            if pos == rat.pos:
                icon = {"ESCAPED": "🥳", "CAUGHT": "😵", "TIRED": "😩"}.get(model.status, "🐀")
            elif pos in cat_at:
                icon = cat_at[pos].icon
            elif pos == model.exit:
                icon = "🚪"
            elif pos == model.start:
                icon = "🏠"
            elif pos in route and rat.search:
                icon = f'<span style="color:{COLORS[rat.search.method]};font-size:70%">●</span>'
            else:
                icon = ""

            cells.append(f'<div class="cell" style="{style}">{icon}</div>')

    # Smaller emojis on bigger grids so they still fit in the squares
    font = max(8, min(24, 420 // model.size))

    return (
        f'<div class="board" style="grid-template-columns: repeat({model.size}, 1fr); --fs:{font}px">'
        f'{"".join(cells)}'
        f'</div>'
    )


# =============================================================================
# THE COMPARE TABLE (one row per AI run, best method marked with 🏆)
# =============================================================================

def best_run(runs):
    """The best escape: it must escape, then fewest moves, then fewest squares explored.
    Returns None if no run escaped."""

    escaped = [r for r in runs if r["result"] == "ESCAPED"]
    return min(escaped, key=lambda r: (r["moves"], r["explored"]), default=None)


def runs_html(model):
    """Build the compare table and the 'best method' sentence under it."""

    result_text = {"ESCAPED": "🥳 escaped", "CAUGHT": "😵 caught", "TIRED": "😩 tired"}
    best = best_run(model.runs)

    # --- One table row per run (the best row gets a yellow background) ----
    rows = ""
    for r in model.runs:
        highlight = " style=background:#fff9db" if r is best else ""
        trophy = "🏆 best" if r is best else ""
        rows += (
            f'<tr{highlight}>'
            f'<td style="color:{COLORS[r["method"]]};font-weight:700">{r["method"]}</td>'
            f'<td>{result_text[r["result"]]}</td>'
            f'<td>{r["moves"]}</td>'
            f'<td>{r["explored"]}</td>'
            f'<td>{r["replans"]}</td>'
            f'<td>{trophy}</td>'
            f'</tr>'
        )

    # --- The verdict sentence ---------------------------------------------
    if best:
        verdict = (
            f'🏆 <b style="color:{COLORS[best["method"]]}">{best["method"]}</b> is the best method on this maze: '
            f'it escaped in <b>{best["moves"]}</b> moves after exploring <b>{best["explored"]}</b> squares.'
        )
    else:
        verdict = "No method has escaped yet, so there is no winner. Try another method with ↩ Back to start."

    return (
        '<table class="runs">'
        '<tr><th>Method</th><th>Result</th><th>Moves</th><th>Squares explored</th><th>Replans</th><th></th></tr>'
        f'{rows}'
        '</table>'
        f'<div style="font-size:15px;margin-top:10px">{verdict}</div>'
        '<div style="font-size:12px;color:#777;margin-top:4px">'
        'Best = it must escape; then fewest moves wins; if moves are equal, fewer squares explored wins '
        f'(less thinking). Shortest way out from 🏠, ignoring the cats: {model.shortest_from(model.start)} moves.'
        '</div>'
    )


# =============================================================================
# THE BOARD COMPONENT (so the maze can listen to the keyboard)
# =============================================================================

@solara.component
def Board(html, on_key):
    """The maze board. It can be clicked (focused) and then listens for key presses."""

    element = solara.v.Html(
        tag="div",
        attributes={"tabindex": "0"},   # makes the div focusable, so it receives key presses
        style_="outline:none",
        children=[solara.HTML(unsafe_innerHTML=html)],
    )

    # Every key press on the board calls on_key with the key's name (e.g. "ArrowUp")
    solara.v.use_event(element, "keydown", lambda *args: on_key(args[-1].get("key", "")))


# =============================================================================
# THE PAGE
# =============================================================================

@solara.component
def Page():

    # -------------------------------------------------------------------------
    # 1. Page state (remembered between redraws)
    # -------------------------------------------------------------------------
    method, set_method = solara.use_state(DEFAULT_METHOD)          # BFS, DFS or A*
    level, set_level = solara.use_state(DEFAULT_LEVEL)             # Easy, Normal or Hard
    cats, set_cats = solara.use_state(LEVELS[DEFAULT_LEVEL]["cats"])
    size, set_size = solara.use_state(DEFAULT_SIZE)                # grid size
    loops, set_loops = solara.use_state(DEFAULT_OPENINGS)          # extra openings
    speed, set_speed = solara.use_state(DEFAULT_SPEED)             # seconds per AI step

    show_search, set_show_search = solara.use_state(True)          # draw the searches?
    show_sight, set_show_sight = solara.use_state(True)            # draw the cats' sight?

    # The game itself (created once; replaced when you press New maze)
    first_model = solara.use_memo(
        lambda: MazeEscapeModel(DEFAULT_SIZE, DEFAULT_OPENINGS, **LEVELS[DEFAULT_LEVEL]), []
    )
    model, set_model = solara.use_state(first_model)

    running, set_running = solara.use_state(False)                 # is "Run to end" playing?
    _, set_tick = solara.use_state(0)                              # bumped to force a redraw

    def redraw():
        set_tick(lambda t: t + 1)

    # -------------------------------------------------------------------------
    # 2. The AI loop: runs in the background while "Run to end" is playing
    # -------------------------------------------------------------------------
    def ai_loop(cancel):
        while running and model.ai_busy() and not cancel.is_set():
            with LOCK:
                model.step()          # the rat explores or walks one square (cats answer each move)
            redraw()
            time.sleep(speed)
        set_running(False)            # finished (escaped, caught, tired) or paused

    solara.use_thread(ai_loop, dependencies=[running, model, speed], intrusive_cancel=False)

    # -------------------------------------------------------------------------
    # 3. What the buttons do
    # -------------------------------------------------------------------------
    def ensure_ai():
        """Start the chosen method from where the rat stands (unless it is already on its way)."""
        rat = model.rat
        if not model.ai_busy() or rat.search is None or rat.search.method != method:
            rat.drive(method)

    def run_to_end():
        """▶ Run to end: let the AI play until the game is over."""
        with LOCK:
            ensure_ai()
        set_running(True)

    def ai_step():
        """⏭ Step: the AI does exactly one step."""
        with LOCK:
            ensure_ai()
            model.step()
        redraw()

    def move(direction):
        """Arrow button or key: you move the rat yourself (this stops the AI)."""
        set_running(False)
        with LOCK:
            model.move_rat(direction)
        redraw()

    def on_key(key):
        if key in KEYS:
            move(KEYS[key])

    def back_to_start():
        """↩ Back to start: same maze, rat and cats back where they began."""
        set_running(False)
        with LOCK:
            model.restart()
        redraw()

    def new_maze(new_size=None, new_loops=None, new_level=None, new_cats=None):
        """New maze, optionally with a new size, openings, level or number of cats."""
        new_size = new_size or size
        new_level = new_level or level
        new_loops = loops if new_loops is None else new_loops

        # A new level brings its own number of cats, unless you choose one yourself
        if new_cats is None:
            new_cats = LEVELS[new_level]["cats"] if new_level != level else cats

        set_running(False)
        set_size(new_size)
        set_loops(new_loops)
        set_level(new_level)
        set_cats(new_cats)

        settings = {**LEVELS[new_level], "cats": new_cats}
        set_model(MazeEscapeModel(new_size, new_loops, **settings))

    # -------------------------------------------------------------------------
    # 4. Read everything we need from the model (safely, under the lock)
    # -------------------------------------------------------------------------
    with LOCK:
        board = board_html(model, show_search, show_sight)
        runs = runs_html(model) if model.runs else ""

        rat, status, moves = model.rat, model.status, model.moves
        search = rat.search
        busy = model.ai_busy()

        if not busy:
            phase = ""
        elif search and not search.done:
            phase = "searching"
        elif rat.fleeing:
            phase = "fleeing from the cat"
        else:
            phase = "walking"

        cat_states = " · ".join(f"{c.icon} {c.state}" for c in model.cats)
        explored = rat.explored_total + (len(search.explored) if search and not search.done else 0)

    over = status in ("ESCAPED", "CAUGHT", "TIRED")
    driver = search.method if search and model.ai_from is not None else "You"

    # -------------------------------------------------------------------------
    # 5. The layout
    # -------------------------------------------------------------------------
    solara.Style(CSS)

    with solara.Div(classes=["escape"]):

        # --- Title -----------------------------------------------------------
        solara.HTML(unsafe_innerHTML="<h1>🐀 Rat Escape</h1>")
        solara.Text(
            "Get the rat out of the maze 🚪 without being caught by the cats 🐱😼. "
            "Drive it yourself, or let BFS, DFS or A* find the way."
        )

        # --- Status message --------------------------------------------------
        if status == "ESCAPED":
            solara.Success(f"🥳 The rat escaped in {moves} moves! Driver: {driver}.")
        elif status == "CAUGHT":
            solara.Error(f"😵 The cat caught the rat after {moves} moves. Press ↩ Back to start or New maze.")
        elif status == "TIRED":
            solara.Error(f"😩 The chase went on too long ({moves} moves) and the rat got tired.")
        elif busy:
            solara.Info(f"🤖 {search.method} is {phase}…")
        else:
            solara.Info(f"Level {level}: {LEVEL_INFO[level]}. Move with the arrows, or let the AI drive.")

        with solara.Row(style={"flex-wrap": "wrap", "gap": "16px", "align-items": "flex-start"}):

            # --- Left: the maze ----------------------------------------------
            with solara.Column(style={"flex": "1 1 440px", "max-width": "600px"}):
                Board(board, on_key)
                solara.Text(
                    "Tip: click the maze, then use the arrow keys or W A S D.",
                    style={"font-size": "12px", "color": "#777"},
                )

            # --- Right: the controls -----------------------------------------
            with solara.Column(style={"flex": "1 1 300px"}):

                # Arrow navigator
                with solara.Card("🎮 Drive yourself"):
                    big = {"font-size": "22px", "min-width": "56px"}
                    with solara.Column(align="center", gap="4px"):
                        solara.Button("⬆", on_click=lambda: move("up"), disabled=over, style=big)
                        with solara.Row(gap="4px"):
                            solara.Button("⬅", on_click=lambda: move("left"), disabled=over, style=big)
                            solara.Button("⬇", on_click=lambda: move("down"), disabled=over, style=big)
                            solara.Button("➡", on_click=lambda: move("right"), disabled=over, style=big)

                # AI controls
                with solara.Card("🤖 Let the AI drive"):
                    solara.Select(label="Search method", value=method, values=METHODS, on_value=set_method)

                    with solara.Row(style={"flex-wrap": "wrap"}):
                        solara.Button(
                            "⏸ Pause" if running else "▶ Run to end",
                            color="primary",
                            disabled=over,
                            on_click=lambda: set_running(False) if running else run_to_end(),
                        )
                        solara.Button("⏭ Step", outlined=True, disabled=over or running, on_click=ai_step)

                    solara.SliderFloat(
                        "Seconds per AI step", value=speed, min=0.01, max=0.5, step=0.01, on_value=set_speed
                    )
                    solara.Checkbox(
                        label="Show the searches (rat: explored / frontier, cat: red A* route)",
                        value=show_search,
                        on_value=set_show_search,
                    )
                    solara.Checkbox(label="Show what the cat can see", value=show_sight, on_value=set_show_sight)

                # Live numbers
                solara.HTML(unsafe_innerHTML=(
                    '<div class="stats">'
                    f'<div><b>{moves}</b>moves</div>'
                    f'<div><b>{driver}</b>driver</div>'
                    f'<div><b>{explored}</b>explored</div>'
                    '</div>'
                    f'<div style="font-size:13px;color:#444;margin-bottom:8px">Cats: {cat_states}</div>'
                ))

                # Maze settings
                with solara.Card("🗺 Maze"):
                    solara.Select(
                        label="Level", value=level, values=list(LEVELS),
                        on_value=lambda v: new_maze(new_level=v),
                    )
                    solara.SliderInt(
                        "Number of cats (2nd cat guards the exit)", value=cats, min=1, max=MAX_CATS,
                        on_value=lambda v: new_maze(new_cats=v),
                    )
                    solara.SliderInt(
                        "Grid size", value=size, min=MIN_SIZE, max=MAX_SIZE, step=2,
                        on_value=lambda v: new_maze(new_size=v),
                    )
                    solara.SliderFloat(
                        "Extra openings (more routes)", value=loops, min=0, max=0.3, step=0.02,
                        on_value=lambda v: new_maze(new_loops=v),
                    )
                    with solara.Row(style={"flex-wrap": "wrap"}):
                        solara.Button("↩ Back to start", outlined=True, on_click=back_to_start)
                        solara.Button("New maze", icon_name="mdi-restart", outlined=True, on_click=lambda: new_maze())

        # --- Bottom: compare table and help panels ---------------------------
        if runs:
            with solara.Card("📊 Compare the methods on this maze"):
                solara.HTML(unsafe_innerHTML=runs)

        with solara.Details("❓ How to play", expand=moves == 0 and not model.runs):
            solara.Markdown(HOW_TO_PLAY)

        with solara.Details("🧠 How BFS, DFS and A* work"):
            solara.Markdown(METHODS_HELP)

        with solara.Details("🐱 How the cats think"):
            solara.Markdown(CAT_STATES)
