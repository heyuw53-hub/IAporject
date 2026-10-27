"""
Intra-week sequencing of panels and buffer (stock tampon) simulation.

Rules from the company sheet:
  - a piece enters the buffer when it is cut (1 time unit per piece)
  - an OF leaves the buffer only when all its pieces are in it
  - exit rate = 3 pieces for every 2 entering  -> 1.5 pieces per time unit
  - capacity 3192, target <= 80 % (2553)

OFs: the weekly quantity of an article is split into OFs of QteParOF pieces
(last OF = remainder). Pieces of an article fill its OFs in order.
"""
import numpy as np

CAP = 3192
LIMIT = int(0.8 * CAP)
OUT_RATE = 1.5


def split_ofs(x, q):
    """x: {art: qty}, q: {art: lot} -> list of OF sizes per article"""
    ofs = {}
    for a, n in x.items():
        n = int(n)
        if n <= 0:
            continue
        lot = max(int(q[a]), 1)
        sizes = [lot] * (n // lot) + ([n % lot] if n % lot else [])
        ofs[a] = sizes
    return ofs


def simulate_buffer(panel_seq, ofs):
    """Return occupancy curve (one point per piece cut) and peak."""
    ofs = {a: list(s) for a, s in ofs.items()}
    filled = {a: 0 for a in ofs}        # pieces cut into the current OF of a
    queue = 0.0                          # pieces of complete OFs waiting to exit
    occ, curve = 0.0, []
    for items in panel_seq:
        for a, n in items.items():
            for _ in range(n):
                occ += 1
                if a in ofs and ofs[a]:
                    filled[a] += 1
                    if filled[a] >= ofs[a][0]:
                        queue += ofs[a].pop(0)
                        filled[a] = 0
                out = min(OUT_RATE, queue)
                queue -= out
                occ -= out
                curve.append(occ)
    # drain at the end of the week
    return np.array(curve), (max(curve) if curve else 0.0)


def sequence_greedy(panels, ofs):
    """
    Order panels so OFs are completed as early as possible:
    next panel = the one whose pieces most belong to articles already started,
    tie-break: fewest pieces of not-yet-started articles.
    """
    remaining = list(range(len(panels)))
    started, seq = set(), []
    # start with the article that has the smallest weekly quantity to clear it fast
    while remaining:
        def score(j):
            it = panels[j]
            tot = sum(it.values())
            inside = sum(n for a, n in it.items() if a in started)
            new = tot - inside
            return (inside / tot if tot else 0, -new)
        j = max(remaining, key=score)
        remaining.remove(j)
        seq.append(panels[j])
        started |= set(panels[j])
    return seq


def week_buffer(panels, x, q, greedy=True):
    ofs = split_ofs(x, q)
    seq = sequence_greedy(panels, ofs) if greedy else panels
    curve, peak = simulate_buffer(seq, ofs)
    return curve, peak, seq
