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

Les résultats sont écrits dans `results/`.

**`resultats_215371.xlsx`** contient 6 feuilles :

| Feuille | Contenu |
|---|---|
| Synthese | Comparaison des scénarios : TdC, panneaux, pièces, m² par panneau, nombre de lancements |
| Horizon de regroupement | TdC des OF historiques regroupés par 1 jour, 1, 2 ou 3 semaines (3 = maximum autorisé) |
| KPI hebdo B2 | Pour chaque semaine du scénario recommandé : pièces, pièces de remplissage, panneaux, TdC, stock, stock minimum (≥ 0 : pas de rupture), pic du stock tampon |
| Plan OF B2 (art x sem) | Quantité à lancer par article et par semaine (livrable 3) |
| Frequence par article | QteParOF, demande moyenne, fréquence (« 1 OF toutes les x semaines »), quantité moyenne par OF (livrable 2) |
| TdC hebdo | TdC hebdomadaire des scénarios B1, B2 et B3 |

**`tdc_hebdo.png`** et **`stock_tampon.png`** sont les graphiques correspondants.

**`ordre_de_coupe_215371.xlsx`** (livrable 3) contient 2 feuilles :

| Feuille | Contenu |
|---|---|
| Liste des OF | Un OF par ligne : n° d'OF (`2026-S02-221736-1`), article, quantité (≥ QteParOF), date de lancement, date de livraison, délai (7 jours ≤ 21), premier et dernier panneau de l'OF |
| Ordre de coupe | Pour chaque semaine, les panneaux dans l'ordre de coupe : articles, OF, pièces sur le panneau, cumul de l'OF, et « oui » quand l'OF est complet et sort du stock tampon |

L'ordre de coupe est choisi pour que les OF se complètent le plus tôt possible (pic du stock tampon le plus bas).

**`comparaison_schmidt/`** : comparaison avec les graphiques Schmidt « TdC par Coloris »

| Fichier | Contenu |
|---|---|
| `TdC_par_coloris_215371_propose.png` | Même format que Schmidt (mêmes semaines, étiquettes, tendance linéaire), avec les OF historiques regroupés par semaine |
| `comparaison_215371.png` | Courbe Schmidt et notre courbe sur le même graphique |
| `comparaison_TdC_par_coloris.xlsx` | Les valeurs semaine par semaine |

Les semaines S35 à S37 n'ont pas d'OF dans le fichier fourni : elles restent vides. Les valeurs Schmidt sont lues sur leurs graphiques.

**Résultats principaux** (période commune du 20/04 au 20/07/2026)

| Scénario | TdC |
|---|---|
| B0 – OF historiques coupés par jour (situation actuelle) | 19,7 % |
| B0w – mêmes OF regroupés par semaine | 14,5 % |
| B1 – lots hebdomadaires | 13,7 % |
| **B2 – lots hebdomadaires + remplissage (délai ≤ 3 semaines)** | **13,8 %** |
| B3 – MILP sur le modèle en surface | 14,5 % |

- **Le principal levier est le regroupement hebdomadaire.** Le TdC passe de 19,1 % (1 jour) à 14,3 % (1 semaine), puis 13,9 % (2 semaines) et 13,7 % (3 semaines, le maximum autorisé) : le gain diminue au-delà d'une semaine.
- **Avec la limite de 3 semaines, le remplissage n'apporte presque plus rien** (13,8 % contre 13,7 % pour B1) : on ne peut plus couper à l'avance des pièces nécessaires plus tard.
- **Comparaison avec Schmidt** (S17–S42) : 20,0 % en réel contre 14,5 % avec les mêmes OF regroupés par semaine.
- **Aucune rupture.** Le pic du stock tampon est de 1027 pièces, pour une limite de 2553.
- **Un modèle en surface seul ne suffit pas.** Le MILP fait moins bien que la règle simple : le TdC doit être évalué par une imbrication réelle.

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
