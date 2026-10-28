"""
Programme principal : produit un seul fichier  results/resultats_<matière>.xlsx

    python run.py

Feuilles :
  1. Production par semaine : quantité à couper par article et par semaine
  2. Ordre de coupe         : panneaux dans l'ordre de coupe, avec les OF et leurs dates
  3. Comparaison Schmidt    : graphique Schmidt original + notre graphique au même format
                              + tableau des valeurs

Méthode retenue : lots hebdomadaires (OF = besoin de la semaine suivante + stock de
sécurité, arrondi à QteParOF), imbrication de toute la semaine en une fois,
remplissage des chutes avec des pièces nécessaires dans les 3 semaines au plus.
"""
import os
import tempfile

import numpy as np
import pandas as pd
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Font, PatternFill, Alignment

from .data import load_material, weekly_demand
from .nesting import BestNester, Panel
from .planning import params, simulate
from .sequencing import cutting_order, LIMIT
from . import comparaison

MATIERE = 215371
SS_WEEKS = 0.5            # stock de sécurité au montage (semaines de demande)
SMAX_WEEKS = 3.0          # stock maximum au montage (semaines de demande)
LOT_RULE = "min"          # "min" : OF >= QteParOF ; "multiple" : OF = k x QteParOF
MAX_DELAI_SEMAINES = 3    # délai max. entre lancement de l'OF et utilisation des pièces
OUT = "results"


def _label(w):
    iso = w.isocalendar()
    return f"{iso[0]}/S{iso[1]:02d}"


def _style(ws, widths, freeze="B2"):
    head = PatternFill("solid", fgColor="DDEBF7")
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = head
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    ws.freeze_panes = freeze


def run():
    os.makedirs(OUT, exist_ok=True)
    mat, art = load_material(MATIERE)
    D = weekly_demand(art)
    panel = Panel(L=int(mat.X), W=int(mat.Y),
                  reste_min_l=int(mat.ResteMin_X), reste_min_w=int(mat.ResteMin_Y))
    nester = BestNester({a: (r.X, r.Y, r.SensFil) for a, r in art.iterrows()}, panel)
    p = params(art, D, ss_weeks=SS_WEEKS, smax_weeks=SMAX_WEEKS)

    # ---------- planification hebdomadaire
    kpi, X = simulate(p, D, nester, "policy", fill=True, lot_rule=LOT_RULE,
                      max_weeks=MAX_DELAI_SEMAINES)
    tdc = 1 - kpi.piece_area.sum() / kpi.consumed_area.sum()
    print(f"matière {MATIERE} : {len(X)} semaines, TdC = {tdc:.1%}, "
          f"{int(kpi.panels.sum())} panneaux, stock min. {kpi.min_stock_after.min():.0f}")

    # ---------- feuille 1 : production par article et par semaine
    prod = X.T.astype(int)
    prod.columns = [_label(w) for w in X.index]
    prod.insert(0, "Désignation", art["Désignation article"])
    prod.insert(1, "QteParOF", p.q)
    prod["Total"] = prod.iloc[:, 2:].sum(axis=1)
    prod = prod.sort_values("Total", ascending=False)
    prod.index.name = "Article"
    tot = pd.DataFrame([["TOTAL pièces", ""] + list(prod.iloc[:, 2:].sum())],
                       columns=prod.columns, index=[""])
    tdc_row = pd.DataFrame([["Taux de chute", ""] + [round(v * 100, 1) if n else None
                            for v, n in zip(kpi.tdc, kpi.panels)] + [round(tdc * 100, 1)]],
                           columns=prod.columns, index=[""])
    pan_row = pd.DataFrame([["Panneaux", ""] + list(kpi.panels.astype(int)) + [int(kpi.panels.sum())]],
                           columns=prod.columns, index=[""])
    sheet1 = pd.concat([prod, tot, pan_row, tdc_row])
    sheet1.index.name = "Article"

    # ---------- feuille 2 : ordre de coupe (avec les dates des OF)
    desig = art["Désignation article"].to_dict()
    ordre, ofs, peaks = [], [], []
    for w, row in kpi.iterrows():
        x = row["_x"][row["_x"] > 0].to_dict()
        r_ordre, r_of, peak = cutting_order(w, row["_panels"], x, p.q, desig)
        ordre += r_ordre; ofs += r_of; peaks.append(peak)
    ofs = pd.DataFrame(ofs)
    assert (ofs["Délai (jours)"] <= 7 * MAX_DELAI_SEMAINES).all()
    sheet2 = pd.DataFrame(ordre).merge(
        ofs[["OF", "Quantité", "Date lancement", "Date livraison"]], on="OF", how="left")
    sheet2 = sheet2.rename(columns={"Quantité": "Taille OF"})
    sheet2["Semaine"] = sheet2["Semaine"].str.replace("-", "/")
    print(f"{len(ofs)} OF, pic du stock tampon {max(peaks):.0f} (limite {LIMIT})")

    # ---------- feuille 3 : comparaison avec Schmidt
    tmp = tempfile.mkdtemp()
    sch = comparaison.SCHMIDT[MATIERE]
    weeks = list(sch)
    ours = comparaison.weekly_tdc(MATIERE)
    y_nous = [ours.B0w.get(s, np.nan) * 100 for s in weeks]
    img_schmidt = comparaison.schmidt_image(MATIERE, os.path.join(tmp, "schmidt.png"))
    img_nous = os.path.join(tmp, "nous.png")
    comparaison.chart_format_schmidt(MATIERE, weeks, y_nous, img_nous)
    sheet3 = pd.DataFrame({
        "Semaine": [f"2026/S{s}" for s in weeks],
        "TdC Schmidt (%)": [sch[s] for s in weeks],
        "TdC OF regroupés par semaine (%)": np.round(y_nous, 2),
    })
    ok = ~np.isnan(y_nous)
    moy = pd.DataFrame({"Semaine": ["Moyenne (semaines communes)"],
                        "TdC Schmidt (%)": [round(np.mean(sheet3["TdC Schmidt (%)"][ok]), 2)],
                        "TdC OF regroupés par semaine (%)": [round(np.nanmean(y_nous), 2)]})
    sheet3 = pd.concat([sheet3, moy], ignore_index=True)
    print(f"comparaison Schmidt : {moy.iloc[0, 1]} % -> {moy.iloc[0, 2]} %")

    # ---------- écriture
    path = os.path.join(OUT, f"resultats_{MATIERE}.xlsx")
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        sheet1.to_excel(xw, sheet_name="Production par semaine")
        sheet2.to_excel(xw, sheet_name="Ordre de coupe", index=False)
        sheet3.to_excel(xw, sheet_name="Comparaison Schmidt", index=False)

        ws = xw.sheets["Production par semaine"]
        _style(ws, {"A": 10, "B": 32, "C": 10}, freeze="D2")
        for row in ws.iter_rows(min_row=ws.max_row - 2, max_row=ws.max_row):
            for c in row:
                c.font = Font(bold=True)

        ws = xw.sheets["Ordre de coupe"]
        _style(ws, {"A": 10, "B": 11, "C": 9, "D": 32, "E": 20, "F": 12, "G": 10,
                    "H": 12, "I": 9, "J": 14, "K": 14}, freeze="A2")
        ws.auto_filter.ref = ws.dimensions

        ws = xw.sheets["Comparaison Schmidt"]
        _style(ws, {"A": 26, "B": 15, "C": 18}, freeze="A2")
        ws["E1"] = "Schmidt – TdC réel (graphique original)"
        ws["E1"].font = Font(bold=True, size=12)
        im = XLImage(img_schmidt); im.width, im.height = 1300, 410
        ws.add_image(im, "E2")
        ws["E24"] = "Proposé – mêmes OF regroupés par semaine (même format)"
        ws["E24"].font = Font(bold=True, size=12)
        im = XLImage(img_nous); im.width, im.height = 1300, 413
        ws.add_image(im, "E25")
        n = len(sheet3) + 3
        ws[f"A{n}"] = "Semaines S35 à S37 : pas d'OF dans le fichier fourni."
        ws[f"A{n + 1}"] = "Valeurs Schmidt lues sur leur graphique."
    print("écrit :", path)
    return path


if __name__ == "__main__":
    run()
