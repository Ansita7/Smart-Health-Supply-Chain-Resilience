"""PulseGrid core: synthetic data, days-to-empty forecast, transfer planner.
Pure Python, no dependencies. Same logic as the web prototype."""
import math
import random
from collections import defaultdict

MEDICINES = {"ORS sachets": 2.6, "Paracetamol": 1.4, "Amoxicillin": 1.8, "Antimalarial": 3.0}
DISTRICTS = [(200, 150), (520, 120), (800, 190), (300, 400), (620, 380), (850, 460)]
KM_PER_UNIT = 0.4
SHORTAGE_DAYS = 7      # below this a centre is flagged red
TARGET_DAYS = 14       # plan tops a centre up to this much cover
DONOR_KEEP_DAYS = 25   # a donor never drops below this much cover
CELL = 60              # spatial grid cell size


def make_centres(n=500, seed=7):
    rnd = random.Random(seed)
    centres = []
    for i in range(n):
        d = i % len(DISTRICTS)
        gx, gy = DISTRICTS[d]
        g = lambda: (rnd.random() + rnd.random() + rnd.random() - 1.5) * 90
        c = {"id": i, "district": d,
             "x": min(980, max(20, gx + g())), "y": min(580, max(20, gy + g() * 0.8)),
             "daily_use": {}, "stock": {}}
        for med in MEDICINES:
            use = 6 + rnd.random() * 12
            r = rnd.random()
            cover = rnd.random() * 7 if r < .16 else 45 + rnd.random() * 30 if r < .4 else 9 + rnd.random() * 26
            c["daily_use"][med] = use
            c["stock"][med] = use * cover
        centres.append(c)
    return centres


def demand(c, med, outbreak):
    """Daily use, scaled by outbreak pressure (0 to 100)."""
    return c["daily_use"][med] * (1 + (MEDICINES[med] - 1) * outbreak / 100)


def days_left(c, med, outbreak=0):
    return c["stock"][med] / demand(c, med, outbreak)


def status(c, med, outbreak=0):
    d = days_left(c, med, outbreak)
    return "red" if d < SHORTAGE_DAYS else "amber" if d < 14 else "green"


def plan(centres, med, outbreak=0):
    """Greedy nearest-surplus transfers, most urgent shortage first."""
    grid = defaultdict(list)
    spare = {}
    for c in centres:
        s = c["stock"][med] - demand(c, med, outbreak) * DONOR_KEEP_DAYS
        if s > 0:
            spare[c["id"]] = s
            grid[(int(c["x"] // CELL), int(c["y"] // CELL))].append(c)
    short = sorted((c for c in centres if days_left(c, med, outbreak) < SHORTAGE_DAYS),
                   key=lambda c: days_left(c, med, outbreak))
    moves = []
    for t in short:
        need = demand(t, med, outbreak) * TARGET_DAYS - t["stock"][med]
        cx, cy = int(t["x"] // CELL), int(t["y"] // CELL)
        for r in range(0, 5):
            if need <= 0:
                break
            for a in range(cx - r, cx + r + 1):
                for b in range(cy - r, cy + r + 1):
                    if max(abs(a - cx), abs(b - cy)) != r:
                        continue
                    for d in grid.get((a, b), []):
                        if need <= 0:
                            break
                        q = min(spare[d["id"]], need)
                        if q <= 0:
                            continue
                        spare[d["id"]] -= q
                        need -= q
                        moves.append({"from": d["id"], "to": t["id"], "medicine": med, "quantity": round(q),
                                      "km": round(math.hypot(d["x"] - t["x"], d["y"] - t["y"]) * KM_PER_UNIT),
                                      "why": f"Centre {t['id']} has {days_left(t, med, outbreak):.1f} days left; "
                                             f"centre {d['id']} has surplus."})
    return [m for m in moves if m["quantity"] > 0]


def apply_moves(centres, moves):
    by_id = {c["id"]: c for c in centres}
    for m in moves:
        by_id[m["from"]]["stock"][m["medicine"]] -= m["quantity"]
        by_id[m["to"]]["stock"][m["medicine"]] += m["quantity"]
