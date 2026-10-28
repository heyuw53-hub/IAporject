# Ordonnancement des OF – réduction du Taux de Chute

École d'automne de l'IA 2026 (Alsace Tech, 26–29 octobre) · Projet Schmidt-Groupe

Outil Python qui génère les OF d'une matière **semaine par semaine** : quantité à produire par composant, fréquence de commande et ordre de coupe. L'objectif est de **minimiser le taux de chute (TdC)** sans rupture à l'atelier de montage.

Version 1 : une seule matière, **215371 CHENE HONEY** (55 articles, environ 56 % des pièces et 62 % des m²), avec un pas de temps d'**une semaine**.

---

## 1. Contenu du dossier

```
IAporject/
├── run.py              ← le seul fichier à lancer
├── requirements.txt    bibliothèques nécessaires
├── README.md
├── ordo_of/            code (ne pas lancer ces fichiers un par un)
│   ├── __init__.py
│   ├── data.py         lecture des fichiers Excel, demande hebdomadaire
│   ├── nesting.py      imbrication : nombre de panneaux et TdC d'un lot
│   ├── planning.py     planification hebdomadaire des lots (+ MILP de comparaison)
│   ├── sequencing.py   ordre de coupe, liste des OF, simulation du stock tampon
│   ├── comparaison.py  graphiques au format Schmidt « TdC par Coloris »
│   └── main.py         scénarios, tableaux de résultats, graphiques
├── data/               ← y déposer les 3 fichiers Excel de Schmidt (non versionnés)
└── results/            créé automatiquement à l'exécution
```

## 2. Installation et lancement

1. Installer Python 3.10 ou une version plus récente, puis les bibliothèques (une seule fois) :
   ```
   pip install -r requirements.txt
   ```
2. Copier les trois fichiers Excel dans `data/`. Le nom exact n'a pas d'importance : chaque fichier est retrouvé par mot-clé.

   | Fichier | Mot-clé |
   |---|---|
   | Données articles et matières | `articles` |
   | OFs et TdC | `OFs` |
   | Mouvements de stock montage | `Mouvements` |

3. Lancer le programme :
   - **avec IDLE** : ouvrir `run.py`, puis appuyer sur F5 ;
   - **en terminal**, depuis le dossier `IAporject` : `python run.py`.

Durée d'exécution : environ 15 secondes, plus une minute la première fois, le temps de lire le fichier des mouvements (il est ensuite mis en cache dans `mouv.pkl`).

**Erreurs fréquentes**
- `attempted relative import` : un fichier de `ordo_of/` a été lancé directement. Il faut lancer `run.py`.
- `FileNotFoundError` : les fichiers Excel ne sont pas dans `data/`. On peut aussi indiquer leur dossier dans la variable d'environnement `ORDO_DATA`.

## 3. Paramètres

Les paramètres se trouvent en haut de `ordo_of/main.py`.

| Paramètre | Valeur | Signification |
|---|---|---|
| `MATIERE` | 215371 | Matière étudiée |
| `SS_WEEKS` | 0.5 | Stock de sécurité au montage, en semaines de demande |
| `SMAX_WEEKS` | 3.0 | Stock maximum au montage, en semaines de demande |
| `LOT_RULE` | `"min"` | `"min"` : OF ≥ QteParOF ; `"multiple"` : OF = k × QteParOF |
| `MAX_DELAI_SEMAINES` | 3 | Délai maximum entre le lancement d'un OF et sa livraison / l'utilisation de ses pièces |
| `RESTES_AGE_MAX` | 4 | Une zone libre ≥ ResteMin (800 × 800 mm) devient un reste ; il est réutilisé en priorité les semaines suivantes, puis mis au rebut après 4 semaines |

## 4. Modèle mathématique

**Indices**
- $i$ : article
- $t$ : semaine

**Données**
- $d_{i,t}$ : demande, issue des mouvements de stock (consommation + rebut)
- $q_i$ : QteParOF
- $a_i = X_iY_i$ : surface de l'article
- $A$ : surface d'un panneau

**Variables**
- $x_{i,t}$ : quantité coupée en semaine $t$
- $S_{i,t}$ : stock au montage
- $N_t$ : nombre de panneaux

**Objectif**

$$\min \sum_t N_t \quad\Longleftrightarrow\quad \min\ \text{TdC} = 1-\frac{\sum_{i,t} a_i x_{i,t}}{A\sum_t N_t}$$

**Contraintes** (délai d'une semaine : ce qui est coupé en $t$ est disponible en $t+1$)

| Contrainte | Expression |
|---|---|
| Bilan de stock | $S_{i,t+1} = S_{i,t} - d_{i,t} + x_{i,t}$ |
| Pas de rupture | $S_{i,t} - d_{i,t} \ge 0$ |
| Couverture de la semaine suivante | $S_{i,t+1} \ge d_{i,t+1} + S_s$ |
| Taille d'OF | $x_{i,t} = 0$ ou $x_{i,t} \ge q_i$ |
| Stock maximum | $S_{i,t+1} \le S_M$ |
| Stock tampon | pic ≤ 80 % × 3192 = 2553 pièces |
| Délai commande → livraison | ≤ 3 semaines : un OF lancé en $t$ est livré en $t+1$, et les pièces de remplissage ne couvrent que la demande de $t+1$ à $t+3$ |
| Coupe | sens du fil, trait de scie 4,4 mm, coupe de propreté 21 mm, chute réutilisable ≥ 800 × 800 mm |

$N_t$ est obtenu en **imbriquant réellement** les pièces de la semaine $t$.

## 5. Méthode

1. **Imbrication** (`nesting.py`) : coupe guillotine en 3 étapes (bandes, puis colonnes, puis pièces).
   - Les pièces de chaque bande sont choisies par un sac à dos en programmation dynamique, sur une grille de 1 mm.
   - Un même motif est répété tant que les quantités le permettent.
   - Les bandes sont rangées dans les panneaux par First Fit Decreasing.
   - On essaie la première coupe dans les deux sens (longueur et largeur) et on garde la meilleure.
   - Les pièces à fil ne pivotent pas.
2. **Planification** (`planning.py`) : on avance semaine par semaine.
   - Lot obligatoire : le plus petit multiple de QteParOF qui couvre la semaine suivante plus le stock de sécurité.
   - **Remplissage** : les vides des panneaux déjà ouverts reçoivent des pièces nécessaires plus tard, sans ouvrir de nouveau panneau et sans dépasser le stock maximum.
   - Un MILP (scipy/HiGHS) sur un modèle en surface est fourni à titre de comparaison.
3. **Séquencement** (`sequencing.py`) : les quantités sont découpées en OF de QteParOF pièces, puis le stock tampon est simulé pièce par pièce.
   - Entrée : 2 pièces ; sortie : 3 pièces.
   - Un OF ne sort que lorsqu'il est complet.

**Validation de l'imbrication** : appliquée aux OF historiques coupés jour par jour, elle donne un TdC de 19,7 %. Le TdC réel de la matière 215371 est d'environ 20 %.

## 6. Résultats

Un seul fichier : **`results/resultats_215371.xlsx`**, avec 3 feuilles.

| Feuille | Contenu |
|---|---|
| Production par semaine | Quantité à couper par article et par semaine (`2026/Sxx`), QteParOF, total ; en bas : total de pièces, panneaux et taux de chute de chaque semaine |
| Ordre de coupe | Pour chaque semaine, les panneaux dans l'ordre de coupe : articles, n° d'OF (`2026-S02-221736-1`), pièces sur le panneau, cumul de l'OF, « oui » quand l'OF est complet et sort du stock tampon, taille de l'OF, date de lancement et date de livraison (délai 7 jours ≤ 3 semaines) |
| Comparaison Schmidt | Les 5 graphiques Schmidt originaux (toutes matières, 215371, 221612, 220965, 219106) à gauche ; à droite, notre graphique au même format et aux mêmes semaines (bleu : OF regroupés par semaine ; gris : mêmes OF coupés par jour, notre recalcul) ; tableau des valeurs en dessous |

**Résultats principaux**
- Taux de chute de la méthode proposée (S02–S30) : **13,7 %**, sans rupture ; pic du stock tampon 1027 pièces (limite 2553) ; tous les OF ≥ QteParOF et délai ≤ 3 semaines.
- Comparaison avec Schmidt sur les mêmes semaines (S17–S42) : **20,0 % en réel → 14,5 %** en regroupant les mêmes OF par semaine.
- Les semaines S35 à S37 n'ont pas d'OF dans le fichier fourni : elles restent vides. Les valeurs Schmidt sont lues sur leurs graphiques.

## 7. Limites et suite

- L'imbrication est une heuristique écrite par l'équipe, différente de l'optimiseur de Schmidt. Elle permet de comparer les scénarios entre eux, mais ses valeurs absolues restent indicatives.
- La demande de la semaine suivante est supposée connue. Il faudra intégrer une prévision et son erreur.
- Le stock tampon ne contient ici que la matière 215371, alors qu'en réalité il est partagé entre plusieurs matières.
- Questions à poser au tuteur :
  - QteParOF est-il un multiple obligatoire ou un minimum ?
  - Quelle est la capacité de la scie par semaine ?
  - Quelle est la capacité du stock au montage ?
- Pistes pour la suite :
  - exporter les meilleures combinaisons de pièces (livrable 1) ;
  - faire pivoter les pièces sans fil dans l'imbrication, avant de comparer les autres matières (220965, 219106...) ;
  - tester une fréquence fixe par article ;
  - étendre l'outil aux autres matières.
