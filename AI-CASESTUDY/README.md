# 🐀 Rat Escape
Get the rat out of the maze through the gap in the outer wall 🚪 without being caught by the cats 🐱😼.
Drive the rat yourself, or let an AI search method find the way: **BFS, DFS or A\***.
Built with Mesa (agents, grid, model step) and Solara (web page).

## Run (Windows)
- **Double-click** `run.bat`, then open http://localhost:8765.
- **In VS Code:** open this folder, press **F5** (or Run → Start Debugging → "Run Rat Escape"),
  then open http://localhost:8765.
- **In a terminal:** `venv\Scripts\python -m solara run app.py`

## Documents
- `docs/RatEscape_Case_Study.docx`: the case study (same format as the EcoMind case study)
- `docs/RatEscape_Presentation.pptx`: the 17-slide presentation (same design as the EcoMind deck)

## How to play
- **🎮 Drive yourself:** arrow buttons, or click the maze and use the **arrow keys / W A S D**.
- **🤖 Let the AI drive:** choose **BFS, DFS or A\*** in the dropdown, then
  **▶ Run to end** (watch it all) or **⏭ Step** (one step per click).
- Mix them: walk part of the way yourself, then let the AI finish from where the rat stands.
- **↩ Back to start** replays the same maze, so you can compare the methods in the table.
  The table marks the **🏆 best method**: it must escape, then fewest moves wins, and if moves are
  equal, fewer squares explored wins.
- Every time the rat moves, the cats move too. You lose if a cat catches the rat, or if the chase
  lasts more than size × size moves (the rat gets tired).

Settings: search method, level, number of cats (1 to 4), grid size (7 to 41), extra openings
(more routes), AI speed, and overlays for the searches and the cats' sight.

| Level | Cats | Cats see | Cats rest | Rat sees | AI rat caught* |
|---|---|---|---|---|---|
| Easy | 1 hunter | 4 squares | every 2nd turn | 8 squares | about 16% |
| Normal | hunter + guard | 5 squares | every 3rd turn | 7 squares | about 54% |
| Hard | 2 hunters + guard | 6 squares | every 4th turn | 5 squares | about 80% |

\* Tested on 270 runs per level (3 grid sizes × 30 mazes × BFS, DFS and A\*).

## The AI
**Rat (when the AI drives).** It only knows about the cats **within its own sight**, so it can walk into an ambush.
1. **Search:** the chosen method finds a route to the exit, treating each visible cat and the squares
   next to it as walls, so the route goes around them. You watch it explore one square per step.
2. **Walk:** it follows the route one square per step.
3. **Replan:** if a cat moves into the route, it searches again (instantly) with the same method.
4. **Flee:** if every route passes a cat, it moves (or waits) to the square the cats need the most
   moves to reach, measured with a breadth-first search from all visible cats.

**Cats.** There are two roles: 🐱 hunter and 😼 guard (the 2nd cat is the guard).

| Cat state | When | What it does |
|---|---|---|
| CHASE (A\*) | It sees the rat | A\* straight to the rat |
| INVESTIGATE | It just lost sight of the rat | A\* to the last place it saw the rat (memory) |
| WANDER | A hunter with nothing to do | Roams the maze |
| GUARD | The guard with nothing to do | Patrols within 3 squares of the exit (ambush) |

| | BFS | DFS | A\* |
|---|---|---|---|
| Frontier | Queue (first in, first out) | Stack (last in, first out) | Priority queue on `f(n) = g(n) + h(n)` |
| Shortest path? | ✅ Always | ❌ Not guaranteed | ✅ Always |
| Squares explored | Most | Depends on luck | Fewest (usually) |

All three use the same search loop in `Search.step()`; only the frontier is different.
`h(n)` is the Manhattan distance. The maze is generated with a **randomised DFS** (recursive backtracker).

The levels table above shows how often the AI rat gets caught.

## Files
- `model.py` maze generator (DFS), `Search` (BFS / DFS / A\*), Rat and Cat (hunter / guard) agents, the Mesa model
- `app.py`   the web page: board, keyboard and arrows, method dropdown, AI run/step, settings, compare table
- `run.bat`  sets up the Python environment (first run) and starts the game
- `.vscode/` VS Code settings: uses `venv`, and F5 runs the game
