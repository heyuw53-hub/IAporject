"""
Run all scenarios for one material and write results to ./results

    python -m ordo_of.main            (data read from $ORDO_DATA, default /mnt/user-data/uploads)

Scenarios
  B0  historical OFs, cut day by day (current practice)       -> calibration of the nester
  B0w historical OFs, regrouped by week
  B1  weekly batch, policy: lots = smallest multiple of QteParOF covering next week + SS
  B2  B1 + gap filling with future needs (stock cap = SMAX_WEEKS of demand)   <- proposed
  B3  MILP lot-sizing on the area model (+ gap filling)        -> shows the limit of an area-only model
"""
import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .data import load_material, weekly_demand, historical_ofs
from .nesting import BestNester, Panel
from .planning import params, simulate, milp_plan
from .sequencing import week_buffer, cutting_order, LIMIT
from . import comparaison

MATIERE = 215371
SS_WEEKS = 0.5
SMAX_WEEKS = 3.0
LOT_RULE = "min"   # "min": OF >= QteParOF ; "multiple": OF = k * QteParOF
# délai max. entre le lancement d'un OF et la livraison / l'utilisation de ses pièces
MAX_DELAI_SEMAINES = 3
OUT = "results"


def tdc(df):
    return 1 - df.piece_area.sum() / df.consumed_area.sum()


def run():
    os.makedirs(OUT, exist_ok=True)
    mat, art = load_material(MATIERE)
    D = weekly_demand(art)
    panel = Panel(L=int(mat.X), W=int(mat.Y),
                  reste_min_l=int(mat.ResteMin_X), reste_min_w=int(mat.ResteMin_Y))
    nester = BestNester({a: (r.X, r.Y, r.SensFil) for a, r in art.iterrows()}, panel)
    p = params(art, D, ss_weeks=SS_WEEKS, smax_weeks=SMAX_WEEKS)
    print(f"material {MATIERE}: {len(art)} articles, {len(D)} weeks of demand "
          f"({D.index[0].date()} .. {D.index[-1].date()})")

    # ---------------- B0: historical OFs
    of = historical_ofs(art)
    rows = []
    for (wk, day), g in of.groupby(["week", "DateProd"]):
        r = nester.nest(g.groupby("Article")["Qté cdée"].sum().to_dict())
        rows.append({"week": wk, "piece_area": r["piece_area"], "consumed_area": r["consumed_area"],
                     "panels": r["n_panels"], "pieces": int(g["Qté cdée"].sum()), "n_OF": g.Article.nunique()})
    b0 = pd.DataFrame(rows).groupby("week").sum()
    rows = []
    for wk, g in of.groupby("week"):
        r = nester.nest(g.groupby("Article")["Qté cdée"].sum().to_dict())
        rows.append({"week": wk, "piece_area": r["piece_area"], "consumed_area": r["consumed_area"],
                     "panels": r["n_panels"], "pieces": int(g["Qté cdée"].sum()), "n_OF": g.Article.nunique()})
    b0w = pd.DataFrame(rows).set_index("week")

    hor = []
    for lab, key in [("1 jour", of.DateProd), ("1 semaine", of.week),
                     ("2 semaines", of.week.dt.isocalendar().week // 2),
                     ("3 semaines (max. autorisé)", of.week.dt.isocalendar().week // 3)]:
        pa = ca = npan = 0
        for _, g in of.groupby(key):
            r = nester.nest(g.groupby("Article")["Qté cdée"].sum().to_dict())
            pa += r["piece_area"]; ca += r["consumed_area"]; npan += r["n_panels"]
        hor.append({"regroupement des OF": lab, "TdC": 1 - pa / ca, "panneaux": npan})
    hor = pd.DataFrame(hor)
    print(hor.to_string(index=False))

    # ---------------- B1 / B2 / B3
    b1, X1 = simulate(p, D, nester, "policy", fill=False, max_weeks=MAX_DELAI_SEMAINES)
    b2, X2 = simulate(p, D, nester, "policy", fill=True, lot_rule=LOT_RULE,
                      max_weeks=MAX_DELAI_SEMAINES)
    plan, res = milp_plan(p, D)
    b3, X3 = simulate(p, D, nester, "plan", plan, fill=False, max_weeks=MAX_DELAI_SEMAINES)

    # ---------------- ordre de coupe, liste des OF et stock tampon (scénario proposé)
    desig = art["Désignation article"].to_dict()
    peaks, ordre, ofs = [], [], []
    for w, row in b2.iterrows():
        x = row["_x"][row["_x"] > 0].to_dict()
        r_ordre, r_of, peak = cutting_order(w, row["_panels"], x, p.q, desig)
        ordre += r_ordre; ofs += r_of; peaks.append(peak)
    b2["buffer_peak"] = peaks
    ofs = pd.DataFrame(ofs)
    assert (ofs["Délai (jours)"] <= 7 * MAX_DELAI_SEMAINES).all()
    with pd.ExcelWriter(os.path.join(OUT, f"ordre_de_coupe_{MATIERE}.xlsx")) as xw:
        ofs.to_excel(xw, sheet_name="Liste des OF", index=False)
        pd.DataFrame(ordre).to_excel(xw, sheet_name="Ordre de coupe", index=False)
    print(f"{len(ofs)} OF, {len(ordre)} lignes d'ordre de coupe")

    # ---------------- synthesis (full period and window common with history)
    common = b1.index.intersection(b0.index)
    syn = []
    for name, df in [("B0 historique / jour", b0), ("B0w historique / semaine", b0w),
                     ("B1 lot hebdo (règle)", b1), ("B2 lot hebdo + remplissage", b2),
                     ("B3 MILP (modèle surface)", b3)]:
        c = df.loc[df.index.intersection(common)]
        syn.append({
            "scénario": name,
            "TdC période commune": tdc(c),
            "TdC toute la période": tdc(df),
            "panneaux (commune)": int(c.panels.sum()),
            "pièces (commune)": int(c.pieces.sum()),
            "m² pièces / panneau (commune)": c.piece_area.sum() / 1e8 / c.panels.sum(),
            "lancements article×lot (commune)": int(c.n_OF.sum()),
        })
    syn = pd.DataFrame(syn)
    print(syn.to_string(index=False))
    print(f"buffer peak B2: max {max(peaks):.0f} (limit {LIMIT})")

    # ---------------- per-article frequency and quantity (proposed scenario)
    n_weeks = len(X2)
    freq = pd.DataFrame({
        "Désignation": art["Désignation article"],
        "QteParOF": p.q,
        "demande moy./sem.": p.dbar.round(1),
        "semaines avec OF": (X2 > 0).sum(),
        "fréquence (1 OF tous les x sem.)": (n_weeks / (X2 > 0).sum().replace(0, np.nan)).round(2),
        "qté moy. par OF": (X2.sum() / (X2 > 0).sum().replace(0, np.nan)).round(0),
        "qté totale": X2.sum().astype(int),
    })
    plan_out = X2.copy()
    plan_out.index = plan_out.index.strftime("%Y-%m-%d")

    kpi = b2.drop(columns=["_panels", "_x"]).copy()
    kpi["TdC"] = kpi.tdc
    with pd.ExcelWriter(os.path.join(OUT, f"resultats_{MATIERE}.xlsx")) as xw:
        syn.to_excel(xw, sheet_name="Synthese", index=False)
        hor.to_excel(xw, sheet_name="Horizon de regroupement", index=False)
        kpi.index = kpi.index.strftime("%Y-%m-%d")   # date only, no hh:mm
        kpi.index.name = "semaine"
        kpi.to_excel(xw, sheet_name="KPI hebdo B2")
        plan_out.T.to_excel(xw, sheet_name="Plan OF B2 (art x sem)")
        freq.sort_values("demande moy./sem.", ascending=False).to_excel(xw, sheet_name="Frequence par article")
        th = pd.DataFrame({"B1": b1.tdc, "B2": b2.tdc, "B3": b3.tdc})
        th.index = th.index.strftime("%Y-%m-%d")
        th.index.name = "semaine"
        th.to_excel(xw, sheet_name="TdC hebdo")

    # ---------------- figures
    fig, ax = plt.subplots(figsize=(10, 4))
    s0 = (1 - b0.piece_area / b0.consumed_area)
    s0 = s0.reindex(pd.date_range(s0.index.min(), s0.index.max(), freq="W-MON"))
    nz = lambda df: df.tdc.where(df.panels > 0)
    ax.plot(s0.index, s0, "o-", label="B0 historique (OF coupés par jour)")
    ax.plot(b1.index, nz(b1), "s-", label="B1 OF regroupés par semaine")
    ax.plot(b2.index, nz(b2), "^-", label="B2 B1 + remplissage")
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_ylabel("Taux de chute")
    ax.set_title(f"Taux de chute hebdomadaire – matière {MATIERE}")
    ax.legend(); ax.grid(alpha=.3); fig.autofmt_xdate(); fig.tight_layout()
    fig.savefig(os.path.join(OUT, "tdc_hebdo.png"), dpi=150)

    fig, ax = plt.subplots(figsize=(10, 3.5))
    ax.bar(b2.index, b2.buffer_peak, width=5)
    ax.axhline(LIMIT, color="r", ls="--", label="80 % de 3192")
    ax.set_ylabel("Pic stock tampon (pièces)"); ax.legend(); fig.autofmt_xdate(); fig.tight_layout()
    fig.savefig(os.path.join(OUT, "stock_tampon.png"), dpi=150)
    # ---------------- comparaison avec les graphiques Schmidt « TdC par Coloris »
    comparaison.run(OUT, matieres=(MATIERE,))
    return syn


if __name__ == "__main__":
    run()
