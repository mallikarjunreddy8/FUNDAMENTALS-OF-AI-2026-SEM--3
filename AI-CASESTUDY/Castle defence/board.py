"""Draws the battlefield as one SVG string, which board.vue shows and makes clickable."""

from model import ALGO_COLORS, MUD, ROCK

CELL = 32
LABELS = {"BFS": "B", "DFS": "D", "A*": "A"}
STACK_OFFSETS = [(0, 0), (-6, -5), (6, 5), (-6, 5), (6, -5)]


def _mid(v):
    return v * CELL + CELL / 2


def _points(cells):
    return " ".join(f"{_mid(x)},{_mid(y)}" for x, y in cells)


def _hp_color(frac):
    return "#16a34a" if frac > 0.6 else "#eab308" if frac > 0.3 else "#dc2626"


def render_board(m, search=None, routes=True, ranges=False, danger=False):
    """search: None or an algorithm name whose gate searches to overlay."""
    width, height = m.width * CELL, m.height * CELL
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" '
        'style="display:block;border-radius:10px;font-family:system-ui,sans-serif">',
        '<defs><pattern id="cd-grass" width="64" height="64" patternUnits="userSpaceOnUse">'
        '<rect width="64" height="64" fill="#a3cf6e"/><rect width="32" height="32" fill="#99c765"/>'
        '<rect x="32" y="32" width="32" height="32" fill="#99c765"/></pattern></defs>',
        f'<rect width="{width}" height="{height}" fill="url(#cd-grass)"/>',
    ]
    add = out.append

    for (x, y), kind in m.terrain.items():
        px, py = x * CELL, y * CELL
        if kind == MUD:
            add(f'<rect x="{px}" y="{py}" width="{CELL}" height="{CELL}" fill="#8d6e4a"/>'
                f'<circle cx="{px + 9}" cy="{py + 11}" r="3" fill="#6f5437"/>'
                f'<circle cx="{px + 22}" cy="{py + 22}" r="4" fill="#6f5437"/>')
        elif kind == ROCK:
            add(f'<rect x="{px + 2}" y="{py + 3}" width="{CELL - 4}" height="{CELL - 5}" rx="9" fill="#78716c"/>'
                f'<rect x="{px + 7}" y="{py + 7}" width="{CELL - 16}" height="7" rx="3.5" fill="#a8a29e"/>')

    if danger:
        for (x, y), d in m.danger.items():
            if m.terrain[(x, y)] != ROCK:
                add(f'<rect x="{x * CELL}" y="{y * CELL}" width="{CELL}" height="{CELL}" '
                    f'fill="#dc2626" opacity="{min(0.6, 0.18 * d):.2f}"/>')

    if search:
        color = ALGO_COLORS[search]
        explored = set()
        for _, res in m.gate_searches(search):
            explored.update(res.explored)
        for x, y in explored:
            add(f'<rect x="{x * CELL}" y="{y * CELL}" width="{CELL}" height="{CELL}" '
                f'fill="{color}" opacity="0.22"/>')

    if ranges:
        for t in m.towers():
            add(f'<circle cx="{_mid(t.pos[0])}" cy="{_mid(t.pos[1])}" r="{t.spec.range * CELL}" '
                'fill="#fde047" fill-opacity="0.12" stroke="#a16207" stroke-opacity="0.5" '
                'stroke-dasharray="5 4"/>')

    if search:
        for gate, res in m.gate_searches(search):
            add(f'<polyline points="{_points([gate, *res.path])}" fill="none" stroke="{color}" '
                'stroke-width="5" stroke-opacity="0.85" stroke-linecap="round" stroke-linejoin="round"/>')

    for x, y in m.gates:
        px, py = x * CELL, y * CELL
        add(f'<g><title>Enemy gate</title>'
            f'<rect x="{px + 3}" y="{py + 2}" width="{CELL - 6}" height="{CELL - 2}" rx="11" fill="#3b0764"/>'
            f'<rect x="{px + 8}" y="{py + 8}" width="{CELL - 16}" height="{CELL - 8}" rx="7" fill="#a21caf"/></g>')

    xs = [x for x, _ in m.castle_cells]
    ys = [y for _, y in m.castle_cells]
    cx0, cy0 = min(xs) * CELL, min(ys) * CELL
    cw, ch = (max(xs) - min(xs) + 1) * CELL, (max(ys) - min(ys) + 1) * CELL
    frac = m.castle_hp / m.castle_max_hp
    add(f'<g><title>Your castle: {m.castle_hp}/{m.castle_max_hp} HP</title>'
        f'<rect x="{cx0 + 2}" y="{cy0 + 2}" width="{cw - 4}" height="{ch - 4}" rx="6" '
        'fill="#e2e8f0" stroke="#475569" stroke-width="2"/>'
        f'<text x="{cx0 + cw / 2}" y="{cy0 + ch / 2 - 6}" font-size="38" text-anchor="middle" '
        'dominant-baseline="central">🏰</text>'
        f'<rect x="{cx0 + 6}" y="{cy0 + ch - 16}" width="{cw - 12}" height="8" rx="4" fill="#334155"/>'
        f'<rect x="{cx0 + 6}" y="{cy0 + ch - 16}" width="{(cw - 12) * frac:.1f}" height="8" rx="4" '
        f'fill="{_hp_color(frac)}"/></g>')

    for (x, y), s in m.structures.items():
        px, py = x * CELL, y * CELL
        if s.kind == "Wall":
            add(f'<g><title>Wall (sells for {s.cost // 2}g)</title>'
                f'<rect x="{px + 1}" y="{py + 1}" width="{CELL - 2}" height="{CELL - 2}" rx="3" '
                'fill="#b45309" stroke="#78350f" stroke-width="2"/>'
                f'<path d="M{px + 1} {py + 11}h{CELL - 2}M{px + 1} {py + 21}h{CELL - 2}'
                f'M{px + 16} {py + 1}v10M{px + 9} {py + 11}v10M{px + 23} {py + 11}v10M{px + 16} {py + 21}v10" '
                'stroke="#78350f" stroke-width="1.5"/></g>')
        else:
            sp = s.spec
            add(f'<g><title>{sp.name} tower: range {sp.range:g}, {sp.damage} dmg every '
                f'{sp.reload} turn(s){", splash" if sp.splash else ""}. Kills: {s.kills}. '
                f'Sells for {s.cost // 2}g</title>'
                f'<circle cx="{_mid(x)}" cy="{_mid(y)}" r="14" fill="#f8fafc" stroke="#334155" stroke-width="2.5"/>'
                f'<text x="{_mid(x)}" y="{_mid(y) + 1}" font-size="17" text-anchor="middle" '
                f'dominant-baseline="central">{sp.icon}</text></g>')

    enemies = m.live_enemies()
    if routes:
        for e in enemies:
            if e.path:
                add(f'<polyline points="{_points([e.pos, *e.path])}" fill="none" '
                    f'stroke="{ALGO_COLORS[e.algorithm]}" stroke-width="2" stroke-opacity="0.6" '
                    'stroke-dasharray="4 4"/>')

    by_cell = {}
    for e in enemies:
        by_cell.setdefault(e.pos, []).append(e)
    for (x, y), group in by_cell.items():
        for e, (ox, oy) in zip(group, STACK_OFFSETS):
            cx, cy = _mid(x) + ox, _mid(y) + oy
            color = ALGO_COLORS[e.algorithm]
            if e.kind == "Raider":
                shape = f'<polygon points="{cx - 10},{cy - 10} {cx + 12},{cy} {cx - 10},{cy + 10}" fill="{color}"/>'
            elif e.kind == "Knight":
                shape = f'<rect x="{cx - 10}" y="{cy - 10}" width="20" height="20" rx="4" fill="{color}"/>'
            else:
                shape = f'<circle cx="{cx}" cy="{cy}" r="10" fill="{color}"/>'
            frac = e.hp / e.max_hp
            add(f'<g stroke="white" stroke-width="2"><title>{e.kind} ({e.algorithm}) - '
                f'HP {e.hp}/{e.max_hp}, {len(e.path)} steps to go</title>{shape}</g>'
                f'<text x="{cx - (2 if e.kind == "Raider" else 0)}" y="{cy + 1}" font-size="11" '
                f'font-weight="700" fill="white" text-anchor="middle" dominant-baseline="central" '
                f'pointer-events="none">{LABELS[e.algorithm]}</text>'
                f'<rect x="{cx - 11}" y="{cy - 16}" width="22" height="4" rx="2" fill="#1e293b" opacity="0.6"/>'
                f'<rect x="{cx - 11}" y="{cy - 16}" width="{22 * frac:.1f}" height="4" rx="2" '
                f'fill="{_hp_color(frac)}"/>')

    for (tx, ty), (ex, ey), kind in m.shots:
        if kind == "Cannon":
            add(f'<line x1="{_mid(tx)}" y1="{_mid(ty)}" x2="{_mid(ex)}" y2="{_mid(ey)}" '
                'stroke="#f97316" stroke-width="3.5" stroke-linecap="round"/>'
                f'<circle cx="{_mid(ex)}" cy="{_mid(ey)}" r="{CELL * 0.75}" fill="#fb923c" opacity="0.35"/>')
        else:
            add(f'<line x1="{_mid(tx)}" y1="{_mid(ty)}" x2="{_mid(ex)}" y2="{_mid(ey)}" '
                'stroke="#facc15" stroke-width="2.5" stroke-linecap="round"/>')

    if m.phase in ("won", "lost"):
        text = "🏆 Victory!" if m.phase == "won" else "💀 The castle has fallen"
        add(f'<rect width="{width}" height="{height}" fill="#0f172a" opacity="0.5"/>'
            f'<text x="{width / 2}" y="{height / 2}" font-size="44" font-weight="800" fill="white" '
            f'text-anchor="middle" dominant-baseline="central">{text}</text>')

    add("</svg>")
    return "".join(out)
