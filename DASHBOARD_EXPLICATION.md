# Guide d'explication du tableau de bord — Smart Supermarket B2G

**Description** : Documentation complète du tableau de bord de pilotage énergétique Building-to-Grid  
**Date** : Janvier 2025

---

## 1. Vue d'ensemble

Le tableau de bord **Smart Supermarket B2G** est l'interface de supervision d'un système de gestion énergétique intelligent pour supermarchés. Il permet de :

- **Visualiser en temps réel** les flux énergétiques (réseau électrique, production solaire, batterie de stockage)
- **Piloter automatiquement** les équipements critiques (réfrigération, CVC, éclairage) via un contrôleur prédictif (MPC)
- **Garantir la continuité** des équipements Tier 1 (réfrigération) même en cas de coupure réseau
- **Optimiser les coûts** en exploitant l'autoconsommation, les heures creuses et les échanges pair-à-pair (P2P)
- **Tester des scénarios de stress** (coupure, pic de prix, défaillance capteur) pour valider la résilience du système

Le dashboard affiche les métriques opérationnelles, financières et de conformité sous forme de cartes, graphiques et tables interactives. Il fonctionne en **mode En Direct** (connecté au backend) ou en **mode Démonstration** (simulation locale).

---

## 2. Architecture du flux de données

```
┌──────────────┐
│  Dataset CSV │  (4 mois, pas de 15 min)
│  Jun-Sep 2025│
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────┐
│                    PIPELINE BACKEND (Python)                      │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. INGESTION       → Chargement du CSV, timestamps                │
│  2. FORECASTING     → RandomForest : prévision PV + demande       │
│                       Détection anomalies + estimation flexibilité │
│  3. MPC             → Contrôle prédictif horizon glissant (1h)    │
│  4. DERMS           → Dispatch batterie / réseau / P2P            │
│  5. COMPLIANCE      → Vérification Tier 1, cascade délestage      │
│  6. SORTIE          → JSON + CSV + rapport conformité             │
│                                                                   │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │   API FastAPI   │
                  │  port 8000      │
                  └────┬────────┬───┘
                       │        │
            ┌──────────┘        └──────────┐
            │                               │
            ▼                               ▼
    ┌──────────────┐              ┌──────────────────┐
    │  REST API    │              │  WebSocket /ws   │
    │  /api/v1/... │              │  streaming temps │
    └──────────────┘              │  réel            │
                                  └─────────┬────────┘
                                            │
                                            ▼
                                  ┌──────────────────┐
                                  │   DASHBOARD      │
                                  │   React + Vite   │
                                  │   port 5173      │
                                  └──────────────────┘
```

### Détail des étapes du pipeline

- **Ingestion** : Lecture du fichier CSV contenant les données de production PV, consommation, températures sur 4 mois (juin-septembre 2025) avec un pas de temps de 15 minutes (96 mesures par jour).

- **Forecasting** : Un modèle RandomForest entraîné prédit la production solaire et la demande à 1 heure (4 pas). Le module détecte aussi les anomalies (capteurs défaillants, valeurs aberrantes) et estime la flexibilité disponible (charge déplaçable).

- **MPC (Model Predictive Control)** : Le contrôleur prédictif calcule les décisions optimales de charge/décharge batterie et d'import/export réseau sur un horizon glissant de 1 heure. Il choisit parmi 4 actions : écrêtage des pointes, réduction CVC, charge en heures creuses, délestage renforcé.

- **DERMS (Distributed Energy Resource Management System)** : Traduit les commandes MPC en dispatch physique : puissance batterie, puissance réseau (grid), échanges P2P avec le microgrid local.

- **Compliance** : Vérifie que le Tier 1 (réfrigération) reste protégé et que les températures sont dans les plages de sécurité. Si nécessaire, déclenche le délestage en cascade (T4 → T3 → T2, sans toucher T1).

- **Sortie** : Génère des fichiers JSON et CSV dans le dossier `output/` avec tous les timesteps, ainsi qu'un rapport de conformité (% de temps Tier 1 protégé).

### Exemple de payload WebSocket

Lorsque le backend envoie un record via WebSocket, le message JSON a cette structure :

```json
{
  "timestamp": 1717228800000,
  "coverageRatio": 0.98,
  "coverageStatus": "NORMAL",
  "activeActions": ["valley_filling"],
  "tier1Protected": true,
  "batterySoc": 72.3,
  "gridPower": 12.5,
  "p2pPower": 3.2,
  "anomalyFlag": false,
  "anomalySource": null,
  "energyPrice": 0.18,
  "temperatures": {
    "display_freezer_temp": -18.2,
    "freezer_room_temp": -22.1,
    "display_refrigerator_temp": 4.3,
    "cold_room_temp": 2.8
  },
  "temperatureAlerts": [],
  "temperatureStatus": "OK"
}
```

---

## 3. Les deux modes du dashboard

### Mode En Direct (Live)

Le mode **En Direct** connecte le dashboard au backend Python en temps réel :

1. **Vérification de disponibilité** : Le dashboard interroge `GET /health` toutes les 15 secondes pour savoir si le serveur est accessible.
2. **Connexion WebSocket** : Si le serveur répond, ouverture d'une connexion WebSocket sur `ws://localhost:8000/ws/stream`.
3. **Streaming des données** : Le serveur envoie un nouveau record toutes les quelques secondes (simulation accélérée ou tempo réel selon configuration).
4. **Fenêtre glissante** : Le dashboard conserve les 96 derniers pas de temps reçus (= 24 heures à raison de 15 min par pas).
5. **Lecture de la dernière mesure** : Parallèlement, le dashboard appelle `GET /api/v1/latest` toutes les 15 secondes pour s'assurer de la cohérence.
6. **Reconnexion automatique** : Si la connexion WebSocket est coupée (perte réseau, redémarrage serveur), le dashboard tente de se reconnecter avec un backoff exponentiel (1s → 2s → 4s → ... → max 30s).

**Indicateur visuel** : Badge bleu "En direct" avec un point vert pulsant.

### Mode Historique

Le mode **Historique** permet d'interroger une plage de dates complète :

1. **Sélection de dates** : L'utilisateur choisit une date de début et une date de fin (plage disponible : 01/06/2025 → 30/09/2025).
2. **Appel REST** : Le dashboard envoie une requête `GET /api/v1/history?start=2025-06-01 00:00:00&end=2025-06-30 23:59:59`.
3. **Réception groupée** : Le serveur renvoie un tableau JSON contenant tous les records de la période demandée (par exemple, 2880 records pour 30 jours).
4. **Affichage** : Tous les graphiques et métriques sont calculés sur l'ensemble de la plage.

**Indicateur visuel** : Badge "Historique" avec icône calendrier, sélecteurs de dates.

### Mode Démonstration (Mock)

Si le backend n'est pas accessible (ou si `VITE_USE_MOCK=true` dans `.env`), le dashboard bascule automatiquement en **mode Démonstration** :

- Les données sont générées localement par une fonction TypeScript (`mock.ts`).
- La progression simule le temps qui avance : +1 pas de 15 min toutes les 2,5 secondes.
- La plage couvre également juin-septembre 2025.
- Les scénarios peuvent être lancés instantanément (simulation locale).

**Indicateur visuel** : Badge jaune "Données simulées".

### Tableau comparatif

| Critère                   | En Direct            | Historique           | Démonstration        |
|---------------------------|----------------------|----------------------|----------------------|
| **Source de données**     | Backend Python       | Backend Python       | Génération locale JS |
| **Connexion**             | WebSocket streaming  | REST bulk GET        | Aucune               |
| **Latence**               | Temps réel (~1-2s)   | Instantané (bulk)    | Instantané           |
| **Scénarios**             | Lancement via WS     | Pas de lancement     | Lancement instant    |
| **Fenêtre affichée**      | 24h glissantes       | Toute la plage       | 4 mois               |
| **Cas d'usage**           | Démo live, monitoring| Analyse a posteriori | Démo sans serveur    |

---

## 4. Les métriques expliquées une par une

### 4.1 Cartes de statut (StatusCards)

Le dashboard affiche 4 cartes KPI en haut de l'interface.

#### Taux de couverture des besoins (Coverage Ratio)

**Formule** :  
`coverageRatio = énergie_disponible / énergie_demandée`

où `énergie_disponible = PV + batterie + réseau + P2P`.

**Seuils** :
- ≥ 95% → **NORMAL** (fond vert, icône ✓)
- ≥ 90% et < 95% → **AT_RISK** (fond orange, icône ⚠)
- < 90% → **CRITICAL** (fond rouge, icône ✕)

**Exemple** : Si la demande est de 50 kW et que le système fournit 49 kW, le ratio est 98% → NORMAL.

**Ce que ça signifie** : Un ratio < 100% indique un déficit énergétique. Le MPC déclenche alors des actions de délestage pour équilibrer l'offre et la demande.

#### Protection Tier 1 (tier1Protected)

**Valeur** : `true` (vert) ou `false` (rouge)

**Signification** : Indique si les équipements de réfrigération (Tier 1) sont alimentés et fonctionnent dans leurs plages de température de sécurité.

**Conséquences si `false`** :
- Risque de rupture de la chaîne du froid
- Perte de marchandises périssables
- Non-conformité réglementaire (HACCP)

**Ce que le système fait** : En cas de coupure réseau, la batterie est prioritairement allouée au Tier 1. Les autres équipements (CVC, éclairage) sont délestés en cascade (T4 → T3 → T2) avant de toucher T1.

#### État de charge de la batterie (batterySoc)

**Valeur** : pourcentage de 0% à 100%

**Plage de sécurité** : 10% à 95%
- En dessous de 10% : risque de vieillissement prématuré (décharge profonde)
- Au-dessus de 95% : risque de surcharge

**Exemple** : `batterySoc = 72.3%` → la batterie contient 72,3 kWh si sa capacité totale est de 100 kWh.

**Ce qu'on observe** :
- Charge (SOC augmente) : pendant les heures creuses ou quand PV > demande
- Décharge (SOC diminue) : pendant les pointes de demande ou quand PV = 0 (nuit)

**Actions automatiques** :
- `valley_filling` : charge la batterie la nuit quand le prix est bas
- `peak_shaving` : décharge la batterie le soir pour éviter d'acheter au tarif plein

#### Puissance réseau (gridPower)

**Valeur** : kW (kilowatts)

**Convention de signe** :
- **Positif** : import depuis le réseau (le supermarché achète de l'électricité)
- **Négatif** : export vers le réseau (le supermarché vend son surplus solaire)

**Exemple** :
- `gridPower = +12.5 kW` → le supermarché importe 12,5 kW du réseau
- `gridPower = -5.3 kW` → le supermarché exporte 5,3 kW vers le réseau

**Puissance P2P (p2pPower)** :
- Échanges pair-à-pair avec d'autres bâtiments du microgrid local
- Tarif intermédiaire : 0,12 €/kWh (vs 0,18 € achat réseau, 0,08 € vente réseau)

---

### 4.2 Bilan financier (Finance)

Le panneau **Finance** affiche 6 métriques calculées sur la période affichée (24h en mode Live, toute la plage en mode Historique).

#### Calcul détaillé de chaque métrique

**1. Énergie achetée (kWh)**  
Formule : `Σ (gridPower × 0,25 h)` pour tous les pas où `gridPower > 0`

Exemple : Si pendant 1 heure (4 pas de 15 min), le supermarché importe 10 kW :  
`4 × 10 kW × 0,25 h = 10 kWh`

**2. Énergie vendue (kWh)**  
Formule : `Σ (|gridPower| × 0,25 h)` pour tous les pas où `gridPower < 0`

Exemple : Si pendant 30 min (2 pas), le supermarché exporte 8 kW :  
`2 × 8 kW × 0,25 h = 4 kWh`

**3. Énergie P2P (kWh)**  
Formule : `Σ (p2pPower × 0,25 h)` pour tous les pas

**4. Coût achats (€)**  
Formule : `Σ (énergie_achetée × prix_achat)`

- Prix par défaut : 0,18 €/kWh
- En scénario `price_spike` : 0,90 €/kWh pendant la période de pic

Exemple : 10 kWh achetés à 0,18 €/kWh → **1,80 €**

**5. Revenus vente (€)**  
Formule : `énergie_vendue × 0,08 €/kWh` (tarif de rachat fixe)

Exemple : 4 kWh vendus → **0,32 €**

**6. Solde net (€)**  
Formule : `revenus_vente - coût_achats`

Exemple : 0,32 € - 1,80 € = **-1,48 €** (coût net)

#### Exemple chiffré complet (24h)

| Métrique          | Valeur       |
|-------------------|--------------|
| Énergie achetée   | 85,2 kWh     |
| Énergie vendue    | 12,7 kWh     |
| Énergie P2P       | 8,3 kWh      |
| Coût achats       | 15,34 €      |
| Revenus vente     | 1,02 €       |
| **Solde net**     | **-14,32 €** |

**Interprétation** : Sur 24h, le supermarché a un coût net de 14,32 € pour son électricité (après déduction de la revente solaire).

---

### 4.3 Graphiques (Charts)

Le dashboard affiche 4 graphiques interactifs réalisés avec la bibliothèque Recharts.

#### Graphique 1 : Échanges avec le réseau (Grid Exchanges)

**Axes** :
- X : temps (horodatage)
- Y gauche : puissance (kW)
- Y droite : prix (€/kWh)

**Courbes** :
- **Import réseau** (jaune, ligne pleine) : `gridPower > 0`
- **Export réseau** (fuchsia, ligne pleine) : `|gridPower|` quand `gridPower < 0`
- **Prix de l'énergie** (pointillés gris, axe Y droite) : visible uniquement en scénario `price_spike`

**Points d'anomalie** :
- Cercles fuchsia sur la courbe d'import : indiquent un timestep où `anomalyFlag = true`

**Exemple de lecture** :
- À 19h, la courbe d'import monte à 35 kW (pic de demande soirée)
- À 14h, la courbe d'export atteint 15 kW (surplus solaire)
- En scénario `price_spike`, entre 18h et 21h, la ligne de prix passe de 0,18 € à 0,90 €/kWh

#### Graphique 2 : Réserve de la batterie (Battery Reserve)

**Axes** :
- X : temps
- Y : SOC (State of Charge) en %

**Zones** :
- **Zone jaune** (10% - 95%) : plage de sécurité
- **Zone rouge** (< 10% ou > 95%) : sortie de la plage recommandée

**Courbe** :
- Ligne bleue : `batterySoc`

**Exemple de lecture** :
- À 3h du matin, SOC = 18% (fin de la décharge nocturne, action `valley_filling` va démarrer)
- À 12h, SOC = 86% (chargé par le solaire)
- À 20h, SOC = 45% (décharge pour écrêter la pointe du soir)

#### Graphique 3 : Énergie achetée & vendue (Energy Bought/Sold)

**Type** : graphique en barres agrégées

**Axes** :
- X : temps (agrégation par période : 15 min / 1h / 1 jour selon la plage affichée)
- Y : énergie (kWh)

**Barres** :
- **Vert** : énergie achetée (import réseau)
- **Orange** : énergie vendue (export réseau)

**Exemple de lecture** :
- La barre verte de 19h-20h atteint 8,5 kWh (pic de consommation)
- La barre orange de 13h-14h atteint 3,2 kWh (vente du surplus solaire)

#### Graphique 4 : Solde net cumulé (Cumulative Net Balance)

**Axes** :
- X : temps
- Y : solde cumulé (€)

**Courbe** :
- **Verte** si positif (le supermarché a gagné de l'argent en net)
- **Rouge** si négatif (coût net)

**Formule** :
À chaque pas : `solde_cumulé += (revenus_vente - coût_achats)` de ce pas

**Exemple de lecture** :
- À minuit, solde = 0 €
- À 14h, solde = -2,80 € (achats du matin)
- À 15h, solde = -2,40 € (vente solaire a réduit la perte)
- À minuit suivant, solde = -14,32 € (coût net de la journée)

---

### 4.4 Opérations (Operations)

Le panneau **Opérations** affiche 3 éléments.

#### Timeline des actions MPC

**Type** : frise chronologique horizontale

**Segments colorés** représentant les 4 actions possibles :
- **Bleu** : `peak_shaving` (écrêtage des pointes)
- **Vert** : `hvac_soft_shed` (réduction CVC)
- **Jaune** : `valley_filling` (charge en heures creuses)
- **Rouge** : `hard_shedding` (délestage renforcé)

**Lecture** :
- Chaque segment s'étend sur la durée où l'action est active
- Plusieurs actions peuvent être superposées (ex : `valley_filling` + `hvac_soft_shed`)

**Exemple** :
- De 2h à 6h : segment jaune (`valley_filling` — charge batterie la nuit)
- De 18h à 20h : segments bleu + rouge (`peak_shaving` + `hard_shedding` — coupure réseau)

#### Table des anomalies

**Colonnes** :
- Horodatage : date et heure du timestep
- Source : description de l'anomalie (ex : "Capteur de température incohérent", "Défaillance du réseau")

**Tri** : par défaut antichronologique (plus récentes en haut)

**Exemple** :
| Horodatage          | Source                              |
|---------------------|-------------------------------------|
| 2025-07-15 14:30:00 | Capteur de température incohérent   |
| 2025-07-15 14:15:00 | Capteur de température incohérent   |

#### Hiérarchie des tiers de délestage

**Représentation** : 4 cartes empilées de T1 (haut) à T4 (bas)

**Tier 1 — Réfrigération (CRITIQUE)** :
- Vitrines surgelés, chambres de congélation, vitrines réfrigérées, chambres froides
- **Badge** : vert (OK) / orange (WARNING) / rouge (CRITICAL) selon `temperatureStatus`
- **Protection** : toujours alimenté en priorité, même en coupure réseau

**Tier 2 — CVC (IMPORTANT)** :
- Chauffage, ventilation, climatisation
- Peut être réduit (`hvac_soft_shed`) en cas de tension énergétique

**Tier 3 — Éclairage (MODÉRÉ)** :
- Éclairage de surface, de sécurité, des parkings
- Peut être réduit ou coupé partiellement

**Tier 4 — Confort (BAS)** :
- Bornes de recharge VE, services auxiliaires
- Premier à être délesté

**Ordre de délestage** : T4 → T3 → T2 → (jamais T1)

---

## 5. Les scénarios en détail

Le dashboard permet de tester 4 scénarios :

### Fonctionnement normal (none)

**Ce qui change** : Rien. Le dataset est rejouué tel quel, sans injection de perturbation.

**Ce qu'on voit** :
- Courbe de production solaire suit un arc sinusoïdal : 0 kW la nuit, pic à 62 kW vers 13h
- Courbe de demande : 20 kW la nuit, 37 kW en journée (7h-22h), pic à 42 kW vers 19h
- Batterie oscille entre 18% (fin de nuit) et 86% (après-midi)
- Import réseau principalement le soir (18h-23h) quand solaire = 0
- Export réseau à midi quand solaire > demande
- Revenus de vente : environ 1 € par jour
- Coût net : environ 14 € par jour

**Actions observées** :
- `valley_filling` : nuit (2h-6h) — charge batterie au tarif bas
- `peak_shaving` : soirée (18h-22h) — décharge batterie pour limiter les achats

**Intérêt** : Établir une référence de performance normale pour comparer avec les scénarios de stress.

---

### Coupure du réseau (forced_grid_outage)

**Ce qui change** :
- **Backend réel** : rows 200 à 215 du dataset (environ 4 heures), `gridPower` forcé à 0
- **Mode mock** : de 18h à 20h, `gridPower` forcé à 0

**Ce qu'on voit** :
- La courbe d'import réseau (jaune) tombe brutalement à 0 pendant 2-4h
- `coverageRatio` chute à 82%-88% → badge **CRITICAL** (rouge)
- `tier1Protected` reste à **true** (vert) : la batterie alimente la réfrigération
- Action `hard_shedding` apparaît (segment rouge sur la timeline)
- Batterie se décharge rapidement : SOC passe de 72% à 35% en 2h
- Tiers T4, T3, T2 sont délestés (éteints)

**Pourquoi c'est utile** :
- Démontre la résilience du système : Tier 1 protégé même sans réseau
- Valide la hiérarchie de délestage automatique
- Montre l'autonomie sur batterie (typiquement 2-4h selon la charge)

**Exemple de lecture** :
À 19h15 (milieu de la coupure) :
- `coverageRatio = 0.85` (85% des besoins couverts)
- `batterySoc = 41%` (en chute)
- `gridPower = 0 kW`
- `tier1Protected = true`
- `activeActions = ["hard_shedding"]`

---

### Pic de prix (price_spike)

**Ce qui change** :
- **Backend réel** : rows 500 à 507 (2 heures), `energyPrice` multiplié par 5
- **Mode mock** : de 18h à 21h, `energyPrice = 0,90 €/kWh` (vs 0,18 € normal)

**Ce qu'on voit** :
- Une nouvelle courbe apparaît sur le graphique "Échanges avec le réseau" : ligne pointillée grise (prix)
- Cette ligne bondit de 0,18 € à 0,90 €/kWh entre 18h et 21h
- Le panneau Finance montre une explosion du coût des achats :
  - Période normale (18h-19h) : 0,18 € × 10 kW × 1h = 1,80 €
  - Période pic (19h-20h) : 0,90 € × 10 kW × 1h = **9,00 €**
- Le MPC réagit : action `peak_shaving` intensifiée
- La batterie se décharge plus fortement pour éviter d'acheter au prix fort
- Import réseau réduit autant que possible

**Pourquoi c'est utile** :
- Démontre l'optimisation financière automatique du MPC
- Valide la capacité à arbitrer entre batterie et réseau selon le prix
- Montre l'impact d'une tarification dynamique (Time-of-Use, Real-Time Pricing)

**Exemple de lecture** :
À 19h30 (milieu du pic) :
- `energyPrice = 0,90 €/kWh`
- `gridPower = 2,3 kW` (réduit au minimum)
- `batterySoc = 68% → 52%` (décharge rapide)
- Coût marginal : 2,3 kW × 0,25h × 0,90 € = 0,52 € pour ce pas (vs 0,10 € en temps normal)

---

### Défaillance capteur (sensor_corruption)

**Ce qui change** :
- **Backend réel** : rows 1000 à 1003 (1 heure), température de l'un des capteurs forcée à 99,0 °C
- **Mode mock** : de 14h à 15h, `anomalyFlag = true`, `anomalySource = "Capteur de température incohérent"`

**Ce qu'on voit** :
- Sur le graphique "Échanges avec le réseau", des **points fuchsia** apparaissent sur la courbe d'import
- La table des anomalies se remplit d'entrées :
  ```
  | 2025-07-15 14:45:00 | Capteur de température incohérent |
  | 2025-07-15 14:30:00 | Capteur de température incohérent |
  | 2025-07-15 14:15:00 | Capteur de température incohérent |
  | 2025-07-15 14:00:00 | Capteur de température incohérent |
  ```
- La carte Tier 1 affiche un badge **WARNING** ou **CRITICAL** (orange/rouge)
- Possibilité d'une alerte dans `temperatureAlerts` : "display_freezer_temp : Température hors limites (99,0 °C)"

**Pourquoi c'est utile** :
- Valide la détection d'anomalies du module Forecasting
- Montre que le système peut continuer à fonctionner en mode dégradé (ignorer le capteur défaillant et utiliser un modèle de fallback)
- Démontre la traçabilité : chaque anomalie est horodatée et loggée

**Exemple de lecture** :
À 14h30 (milieu de la défaillance) :
- `anomalyFlag = true`
- `anomalySource = "Capteur de température incohérent"`
- `temperatures.display_freezer_temp = 99.0` (aberrant)
- `temperatureStatus = "CRITICAL"`
- Le système peut décider de passer en mode de sécurité : augmenter la puissance de réfrigération par précaution

---

## 6. Configuration

### Variables d'environnement

Le fichier `dashboard/.env` contrôle le comportement du dashboard. Créer ce fichier à partir de `dashboard/.env.example` :

```env
VITE_API_URL=http://localhost:8000
VITE_USE_MOCK=true
VITE_SCENARIO_TRANSPORT=websocket
```

#### VITE_API_URL

**Valeur** : URL du backend FastAPI (par défaut `http://localhost:8000`)

**Quand la changer** :
- Si le backend tourne sur un autre port : `http://localhost:8080`
- Si le backend est déployé sur un serveur : `https://api.smartsupermarket.example.com`

#### VITE_USE_MOCK

**Valeur** : `true` ou `false` (ou non défini)

**Comportement** :
- `true` → Force le mode Démonstration (pas de tentative de connexion au backend)
- `false` ou non défini → Mode normal (connexion au backend si disponible, sinon fallback sur mock)

**Quand utiliser `true`** :
- Démonstration sans serveur (laptop non connecté, présentation offline)
- Développement frontend sans démarrer le backend
- Tests locaux rapides

**Quand utiliser `false`** :
- Intégration complète avec le backend Python
- Démonstration du système complet (ingestion, MPC, streaming)
- Tests de bout en bout

#### VITE_SCENARIO_TRANSPORT

**Valeur** : `websocket` ou `rest`

**Comportement** :
- `websocket` (recommandé) → Lancement de scénario via WebSocket :
  - Ferme la connexion existante
  - Ouvre une nouvelle connexion
  - Envoie `{ "scenario": "price_spike" }` au serveur
  - Reçoit les records en streaming temps réel
  - Timeout de 5 minutes
  
- `rest` → Lancement de scénario via REST :
  - Envoie `POST /api/v1/scenario { "scenario": "price_spike" }`
  - Le serveur traite en synchrone (peut prendre plusieurs secondes)
  - Puis le dashboard rafraîchit les caches (history, latest)

**Quand utiliser `websocket`** : Pour une expérience immersive avec progression visible étape par étape.

**Quand utiliser `rest`** : Pour des tests automatisés ou des environnements où les WebSockets sont bloqués (certains proxies).

---

## 7. Guide de test pratique

### Test 1 — Mode Démonstration (sans serveur)

**Objectif** : Vérifier que le dashboard fonctionne standalone, sans dépendance backend.

**Étapes** :

1. Ouvrir `dashboard/.env` et ajouter :
   ```env
   VITE_USE_MOCK=true
   ```

2. Démarrer le dashboard :
   ```bash
   cd dashboard
   npm run dev
   ```

3. Ouvrir un navigateur à `http://localhost:5173`

4. **Observer** :
   - Badge jaune **"Données simulées"** en haut à droite
   - Les métriques changent automatiquement toutes les 2,5 secondes (progression rapide)
   - Les graphiques se remplissent progressivement

5. **Tester les scénarios** :
   - Sélectionner "Coupure du réseau" dans le menu déroulant
   - Cliquer sur le bouton **"Lancer le scénario"**
   - Observer immédiatement :
     - La courbe d'import tombe à 0 entre 18h et 20h
     - Le badge de couverture passe à CRITICAL (rouge)
     - L'action `hard_shedding` apparaît (segment rouge)

6. **Tester le mode Historique** :
   - Cliquer sur l'onglet **"Historique"**
   - Sélectionner "01/06/2025" (début) et "07/06/2025" (fin)
   - Cliquer **"Afficher"**
   - Observer : tous les graphiques affichent 7 jours complets (672 points)

**Résultat attendu** : Le dashboard fonctionne intégralement sans serveur. Les données sont cohérentes (cycle solaire, batterie, scénarios).

---

### Test 2 — Mode Connecté (avec backend)

**Objectif** : Vérifier l'intégration complète avec le pipeline Python.

**Prérequis** :
- Python 3.11+ installé
- Dépendances backend installées (`pip install -r requirements.txt`)

**Étapes** :

1. Ouvrir `dashboard/.env` et **supprimer** ou commenter la ligne `VITE_USE_MOCK=true` :
   ```env
   VITE_API_URL=http://localhost:8000
   # VITE_USE_MOCK=true   (commenté ou supprimé)
   VITE_SCENARIO_TRANSPORT=websocket
   ```

2. Démarrer le backend dans un terminal :
   ```bash
   cd SmartSupermarket
   uvicorn src.api.fastapi_app:app --reload
   ```
   Vérifier le message :
   ```
   INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
   ```

3. Démarrer le dashboard dans un autre terminal :
   ```bash
   cd dashboard
   npm run dev
   ```

4. Ouvrir `http://localhost:5173`

5. **Observer** :
   - Badge bleu **"En direct"** avec un point vert pulsant
   - Les métriques s'actualisent en temps réel (toutes les 1-2 secondes)
   - Console du navigateur (F12) : messages WebSocket `[WebSocket] Connexion établie`, `[WebSocket] Message reçu: {...}`

6. **Tester un scénario** :
   - Sélectionner "Coupure du réseau"
   - Cliquer **"Lancer le scénario"**
   - Observer dans la console backend (terminal Uvicorn) :
     ```
     INFO:     WebSocket client connected
     INFO:     Running scenario: forced_grid_outage
     INFO:     Streaming 1152 records...
     ```
   - Observer dans le dashboard :
     - Barre de progression "Scénario en cours..." avec spinner
     - Les records arrivent un par un (effet de streaming)
     - Durée : environ 30-60 secondes pour tout le dataset
     - À la fin : badge **"Scénario terminé"** (vert)

7. **Vérifier les alertes CRITICAL** :
   - Pendant la coupure (rows 200-215, soit vers 18h-20h dans le dataset) :
     - Badge de couverture devient **CRITICAL** (rouge)
     - `coverageRatio` < 90%
     - Action `hard_shedding` visible sur la timeline

8. **Tester le mode Historique** :
   - Cliquer sur l'onglet **"Historique"**
   - Sélectionner "15/06/2025" à "16/06/2025"
   - Cliquer **"Afficher"**
   - Vérifier dans la console backend :
     ```
     INFO:     GET /api/v1/history?start=2025-06-15 00:00:00&end=2025-06-16 23:59:59
     INFO:     Returning 192 records
     ```
   - Observer : les graphiques affichent 2 jours complets instantanément

**Résultat attendu** : Le dashboard est connecté au backend, les scénarios déclenchent le pipeline Python, les données sont cohérentes avec le fichier CSV source.

---

### Test 3 — Lancer le pipeline complet (mode CLI)

**Objectif** : Exécuter le pipeline Python en ligne de commande et générer les fichiers de sortie.

**Étapes** :

1. Ouvrir un terminal dans le dossier racine `SmartSupermarket`

2. Lancer le pipeline avec le scénario `price_spike` :
   ```bash
   python scenario_runner.py --scenario price_spike
   ```

3. **Observer la sortie console** :
   ```
   === Smart Supermarket Energy Management Simulation ===
   Scenario: price_spike
   
   [1/5] Ingestion des données...
   ✓ Chargé 1152 timesteps (2025-06-01 → 2025-09-30)
   
   [2/5] Forecasting (prévision + anomalies)...
   ✓ Modèle RandomForest entraîné (R² = 0.94)
   ✓ 4 anomalies détectées
   
   [3/5] MPC (contrôle prédictif)...
   ✓ 1152 décisions calculées
   
   [4/5] DERMS (dispatch batterie/réseau)...
   ✓ Batterie : 348 cycles de charge/décharge
   ✓ P2P : 127 kWh échangés
   
   [5/5] Compliance (vérification Tier 1)...
   ✓ Tier 1 protégé : 100.0% du temps
   ✓ Aucune violation de température
   
   === Sortie ===
   ✓ output/output_price_spike.json (127 KB)
   ✓ output/output_price_spike.csv (89 KB)
   ✓ output/compliance_report_price_spike.json (2 KB)
   
   Durée totale : 8.3s
   ```

4. **Vérifier les fichiers générés** :
   ```bash
   ls output/
   ```
   Résultat :
   ```
   output_price_spike.json
   output_price_spike.csv
   compliance_report_price_spike.json
   ```

5. **Examiner le rapport de conformité** :
   ```bash
   cat output/compliance_report_price_spike.json
   ```
   Exemple de contenu :
   ```json
   {
     "scenario": "price_spike",
     "total_timesteps": 1152,
     "tier1_protected_percentage": 100.0,
     "temperature_violations": 0,
     "total_energy_bought_kwh": 2847.3,
     "total_energy_sold_kwh": 421.8,
     "net_cost_eur": 478.91,
     "average_coverage_ratio": 0.97
   }
   ```

6. **Lancer le backend avec ces données** :
   Le backend lit automatiquement les fichiers `output/output_*.json` pour alimenter les endpoints `/api/v1/latest` et `/api/v1/history`.

**Résultat attendu** : Le pipeline s'exécute sans erreur, génère des fichiers JSON/CSV cohérents, et le rapport montre que Tier 1 est protégé à 100%.

---

## 8. Comprendre ce qui se passe "sous le capot"

**Scénario** : L'utilisateur clique sur "Lancer le scénario" avec "Pic de prix" sélectionné.

### Étape par étape

**1. Clic sur le bouton "Lancer le scénario"** (Dashboard React)

Le composant `App.tsx` appelle la fonction `launchScenario('price_spike')` du hook `useDashboard.ts`.

**2. Vérification du mode** (useDashboard.ts)

- Si `VITE_USE_MOCK=true` → le mock local est réinitialisé avec le scénario, aucune communication serveur
- Sinon → le hook vérifie le statut de connexion backend (`isOnline`)

**3. Lancement via WebSocket** (useStream.ts)

Si `VITE_SCENARIO_TRANSPORT=websocket` :
- Le hook `useStream` ferme la connexion WebSocket existante (s'il y en a une)
- Ouvre une nouvelle connexion sur `ws://localhost:8000/ws/stream`
- Dès l'ouverture, envoie un message JSON :
  ```json
  { "scenario": "price_spike" }
  ```

**4. Réception par le serveur FastAPI** (fastapi_app.py)

L'endpoint WebSocket `/ws/stream` reçoit le message et :
- Parse le JSON pour extraire `scenario_name = "price_spike"`
- Appelle le module `scenario_runner.py` avec ce paramètre

**5. Exécution du pipeline** (scenario_runner.py)

Le pipeline s'exécute en 6 étapes :

**Étape 1 — Ingestion** :
- Chargement du fichier CSV `data/energy_data_supermarket.csv`
- 1152 lignes (4 mois × 30 jours × 96 mesures/jour)
- Colonnes : timestamp, pv_production_kw, demand_kw, battery_soc_pct, grid_power_kw, temperatures...

**Étape 2 — Forecasting** :
- Un modèle RandomForest (pré-entraîné ou entraîné à la volée) prédit la production PV et la demande pour les 4 prochains pas (= 1 heure)
- Le module de détection d'anomalies analyse les températures et les puissances pour identifier les valeurs aberrantes
- Estimation de la flexibilité disponible (charge déplaçable) pour chaque timestep

**Étape 3 — Injection du scénario** :
Pour `price_spike` :
- Identifier les rows 500 à 507 (environ 2 heures dans le dataset)
- Modifier la colonne `energy_price` : multiplier par 5 (0,18 € → 0,90 €)

**Étape 4 — MPC (Model Predictive Control)** :
- Pour chaque timestep, optimisation d'un problème de contrôle sur un horizon de 1 heure (4 pas)
- Objectif : minimiser le coût total tout en respectant les contraintes (SOC batterie, puissance max, protection Tier 1)
- Sortie : décision de charge/décharge batterie, puissance réseau à importer/exporter
- Actions annotées : si prix > seuil → activer `peak_shaving`

**Étape 5 — DERMS** :
- Traduction des décisions MPC en commandes physiques
- Dispatch de la puissance entre batterie, réseau, et P2P
- Vérification des limites techniques (rampe de charge, SOC, puissance de crête)

**Étape 6 — Compliance** :
- Pour chaque timestep, vérifier que `tier1_protected = true`
- Si `coverageRatio < 0,90` → déclencher le délestage en cascade (T4 → T3 → T2)
- Vérifier les températures : si hors plage → lever une alerte
- Sortie : rapport de conformité (% du temps où T1 est protégé, nb de violations)

**6. Streaming des records** (fastapi_app.py)

Le serveur envoie les records un par un via WebSocket :

```python
for record in results:
    await websocket.send_json(record)
    await asyncio.sleep(0.05)  # 50 ms entre chaque record (simulation rapide)
```

Chaque record est un dictionnaire Python converti en JSON :
```json
{
  "timestamp": 1717228800000,
  "coverageRatio": 0.94,
  "coverageStatus": "AT_RISK",
  "activeActions": ["peak_shaving"],
  "tier1Protected": true,
  "batterySoc": 68.2,
  "gridPower": 5.3,
  "p2pPower": 2.1,
  "anomalyFlag": false,
  "anomalySource": null,
  "energyPrice": 0.90,
  ...
}
```

**7. Réception par le dashboard** (useStream.ts)

Le hook `useStream` reçoit chaque message WebSocket :
- Validation du JSON avec Zod (`adapter.ts`) : vérification que tous les champs obligatoires sont présents et ont le bon type
- Transformation en objet TypeScript `TimestepRecord`
- Ajout au tableau `records` (max 96 éléments conservés en fenêtre glissante)

**8. Mise à jour de l'interface** (React)

Les composants React réagissent aux changements du tableau `records` :

- **StatusCards** : recalcule les 4 KPI à partir du dernier record
- **Finance** : recalcule les 6 métriques en sommant sur tous les records
- **Charts** : Recharts redessine les 4 graphiques avec les nouvelles données
- **Operations** : met à jour la timeline des actions et la table des anomalies

**Exemple concret pour le graphique "Échanges avec le réseau"** :
- Le composant extrait de chaque record : `{ timestamp, gridPower, energyPrice }`
- Si `gridPower > 0` → point sur la courbe d'import (jaune)
- Si `gridPower < 0` → point sur la courbe d'export (fuchsia)
- Si `energyPrice` présent → point sur la courbe de prix (pointillés gris)
- Recharts dessine les 3 courbes superposées avec 2 axes Y

**9. Fin du scénario** (fastapi_app.py)

Après avoir envoyé tous les records, le serveur envoie un message spécial :
```json
{ "type": "summary" }
```

Le hook `useStream` détecte ce message et met `scenarioRunning = false` → le spinner disparaît, badge "Scénario terminé" s'affiche.

**10. Timeout de sécurité**

Si le scénario prend plus de 5 minutes (timeout configuré dans `useStream.ts`), la connexion WebSocket est fermée automatiquement et un message d'erreur est affiché.

---

## 9. Ce qui est simulé vs ce qui est réel

### Ce qui EST réel dans cette démo

✅ **Architecture du pipeline** : Les 6 étapes (ingestion, forecasting, MPC, DERMS, compliance, sortie) correspondent à une architecture industrielle réelle pour un BEMS (Building Energy Management System).

✅ **Algorithme MPC** : Le contrôleur prédictif utilise des techniques d'optimisation (programmation linéaire ou quadratique) réellement employées dans les microgrids.

✅ **Hiérarchie de délestage** : La notion de Tiers (T1 = critique, T4 = non essentiel) est une pratique standard en gestion de charge (Demand Response).

✅ **Tarification dynamique** : Les prix de l'électricité en temps réel (Real-Time Pricing) et les tarifs de rachat (Feed-in Tariff) existent dans de nombreux pays.

✅ **Intégration batterie + solaire + réseau** : Les calculs de flux d'énergie, de SOC, et d'arbitrage économique sont fidèles aux systèmes réels de stockage d'énergie (ESS).

✅ **Détection d'anomalies** : Les modèles de ML (RandomForest, isolation Forest) sont couramment utilisés pour la surveillance prédictive des équipements.

### Ce qui EST simulé (pas encore déployé)

⚠️ **Dataset** : Les données CSV sont synthétiques (générées par un script), pas issues d'un vrai supermarché. Les profils de consommation et de production solaire sont réalistes mais fictifs.

⚠️ **Communications avec les équipements** : Le système ne communique pas (encore) avec de vrais onduleurs, BMS (Battery Management System), ou automates CVC. Les "commandes" sont simulées dans le code.

⚠️ **Capteurs IoT** : Les températures sont des valeurs du dataset CSV, pas des lectures MQTT en temps réel depuis des sondes physiques. L'intégration Mosquitto (MQTT broker) est prévue mais pas encore configurée.

⚠️ **Marché P2P** : Les échanges pair-à-pair sont calculés théoriquement, mais il n'y a pas (encore) de blockchain ou de plateforme de microgrid réelle connectée.

⚠️ **Prévisions météo** : Le module de forecasting n'appelle pas (encore) d'API météo externe (OpenWeather, Météo France). Les prévisions sont basées sur l'historique du dataset.

### Prochaines étapes pour passer en production

1. **Intégration MQTT** : Connecter Mosquitto pour recevoir les données des capteurs en temps réel (températures, puissance PV, SOC batterie).

2. **API de commande** : Développer des adaptateurs (drivers) pour piloter les équipements physiques (onduleurs solaires SMA/Fronius, BMS Tesla/LG, contrôleurs CVC Siemens/Schneider).

3. **Base de données historique** : Remplacer les fichiers CSV par une base TimeSeries (InfluxDB, TimescaleDB) pour stocker et requêter des millions de mesures.

4. **Prévisions météo** : Intégrer une API météo pour améliorer les prédictions de production solaire (couverture nuageuse, irradiance).

5. **Marché P2P** : Connecter le système à une plateforme de microgrid (Energy Web Chain, GridSingularity) pour les échanges réels.

6. **Certification** : Faire certifier le système de gestion de la réfrigération (HACCP, EN 12830) et les fonctions de sécurité (fail-safe, redondance).

---

**Fin du document**

Pour toute question technique, consulter les fichiers sources :
- `dashboard/src/hooks/useDashboard.ts` (logique principale)
- `dashboard/src/services/client.ts` (API et WebSocket)
- `src/scenario_runner.py` (pipeline backend)
- `src/api/fastapi_app.py` (endpoints REST et WebSocket)

**Version** : 1.0 — Janvier 2025
