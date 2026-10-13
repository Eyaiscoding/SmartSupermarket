# Guide de Test Rapide - Dashboard B2G

## 🎯 Objectif
Comprendre le dashboard en 10 minutes en testant les deux modes et un scénario.

---

## 📍 Étape 1: Ouvrir le Dashboard

1. Ouvrez votre navigateur: **http://localhost:5173/**
2. Regardez en haut à droite:
   - **🔴 "Hors ligne"** → Backend pas connecté (mode mock)
   - **🟢 "En direct"** → Connecté au backend réel

---

## 📊 Étape 2: Comprendre les Métriques (Cartes en haut)

Vous voyez 6 cartes principales:

### 1. **Coverage Ratio** (Taux de couverture)
```
Formule: (PV + Batterie + Réseau) / Consommation totale
Exemple: 0.98 = 98% de la demande est couverte
```
- **NORMAL** (vert): > 95%
- **AT_RISK** (orange): 80-95%
- **CRITICAL** (rouge): < 80%

### 2. **Tier 1 Protected** (Réfrigération protégée)
```
✅ GREEN = Réfrigération toujours alimentée
❌ RED = Risque de rupture de la chaîne du froid
```
**C'est la métrique la plus critique!**

### 3. **Active Actions** (Actions MPC)
Ce que le contrôleur fait en ce moment:
- **Peak Shaving**: Utilise la batterie pour éviter les pointes
- **Valley Filling**: Charge la batterie quand l'électricité est pas chère
- **HVAC Soft Shed**: Réduit la climatisation
- **Hard Shedding**: Délestage d'urgence (équipements non-critiques coupés)

### 4. **Anomaly Detection**
- **🔴 Rouge**: Le ML a détecté une anomalie (capteur défaillant, valeur aberrante)
- Cliquez pour voir la source (ex: "temperature > 40°C inhabituel")

### 5. **Battery SoC** (État de charge)
```
Exemple: 72% = Batterie chargée aux 3/4
- 0-20%: Risque de blackout si coupure réseau
- 80-100%: Idéal pour affronter les pointes
```

### 6. **Grid Power** (Puissance réseau)
```
Positif: Import du réseau (achat d'électricité)
Négatif: Export vers le réseau (revente)
```

---

## 🔴 Étape 3: Mode "EN DIRECT" (Live)

### Comment ça marche:
```
Dashboard → WebSocket → Backend → Lance scenario_runner.py →
MQTT → Kafka → Forecasting → MPC → DERMS → Compliance →
Résultats retournent via WebSocket → Dashboard se met à jour
```

### Test:
1. Cliquez sur **"En direct"** (bouton en haut)
2. Sélectionnez un scénario: **"Pic de prix"**
3. Cliquez **"Lancer le scénario"**
4. Regardez:
   - Les cartes se mettent à jour toutes les 2-3 secondes
   - Le graphique "Prix de l'électricité" monte × 5
   - L'action "Peak Shaving" s'active automatiquement
   - La batterie se décharge pour éviter d'acheter cher

**Durée**: Le scénario traite 4 mois de données en 4-5 minutes

---

## 📅 Étape 4: Mode "HISTORIQUE" (History)

### Comment ça marche:
```
Dashboard → API GET /api/v1/history?start=2025-06-01&end=2025-06-05 →
TimescaleDB renvoie les records → Dashboard affiche TOUTE la période
```

### Test:
1. Cliquez sur **"Historique"**
2. Sélectionnez les dates:
   - Du: **2025-06-01**
   - Au: **2025-06-05**
3. Cliquez **"Afficher la période"**
4. Résultat: Vous voyez TOUS les points sur 5 jours (480 mesures)

**Avantage**: Idéal pour analyser les tendances, comparer des périodes

---

## 🧪 Étape 5: Les 4 Scénarios Expliqués

### 1. **Fonctionnement normal** (`none`)
- Dataset original, pas de stress
- Le système optimise les coûts en conditions normales
- Usage: Voir le comportement de base

### 2. **Coupure du réseau** (`forced_grid_outage`)
```python
grid_power = 0  # Pendant 16 timesteps (4h)
```
- Simule une panne réseau
- Le système doit tenir sur batterie + PV
- **À observer**: Tier 1 reste-t-il protégé?

### 3. **Pic de prix** (`price_spike`)
```python
energy_price *= 5  # Pendant 8 timesteps (2h)
```
- Électricité passe de 0.15€/kWh à 0.75€/kWh
- Le MPC active Peak Shaving
- La batterie se décharge pour éviter d'acheter
- **À observer**: Économies réalisées (carte Finance)

### 4. **Défaillance capteur** (`sensor_corruption`)
```python
temperature = 99.0  # Valeur aberrante
```
- Capteur de température envoie une valeur impossible
- L'Anomaly Detector (IsolationForest) flag l'anomalie
- **À observer**: Le système détecte-t-il l'erreur?

---

## 📈 Étape 6: Comprendre les Graphiques

### Graphique 1: **Flux énergétiques**
Montre 4 courbes superposées:
- **Demande** (ligne noire): Consommation totale du supermarché
- **PV** (ligne jaune): Production solaire
- **Batterie** (ligne bleue): Charge (+) / Décharge (-)
- **Réseau** (ligne verte): Import (+) / Export (-)

**Lecture**: À 10h00, si demande = 150 kW, PV = 80 kW, batterie décharge 30 kW → réseau fournit 40 kW

### Graphique 2: **Prix de l'électricité**
- Ligne rouge = Prix en €/kWh
- Zones grisées = Heures creuses (prix bas)
- **Comportement MPC**: Charge la batterie en heures creuses, décharge aux heures pleines

### Graphique 3: **État de charge batterie**
- Ligne bleue = SoC (%)
- Doit rester > 20% pour éviter les risques
- **Pattern normal**: Charge la nuit, décharge le jour

### Graphique 4: **Températures froides**
4 courbes:
- Display Freezer: -18°C (congélateurs vitrines)
- Freezer Room: -22°C (chambre froide négative)
- Display Refrigerator: +4°C (frigos vitrines)
- Cold Room: +2°C (chambre froide positive)

**Alertes**:
- 🟠 WARNING: Proche des limites
- 🔴 CRITICAL: Hors limites → Risque sanitaire

---

## 🔧 Étape 7: Configuration (Mode Mock vs Réel)

Le fichier `dashboard/.env` contrôle le mode:

### Mode Réel (backend connecté):
```bash
VITE_USE_MOCK=false
VITE_API_URL=http://localhost:8000
VITE_SCENARIO_TRANSPORT=websocket
```

### Mode Démo (données simulées):
```bash
VITE_USE_MOCK=true
```

**Note**: Si le backend ne répond pas, le dashboard passe automatiquement en mode mock (avec un message "Serveur indisponible")

---

## 🧪 Étape 8: Test Pratique Complet

### Test 1: Scénario "Pic de Prix" en Mode Live

1. **Ouvrir**: http://localhost:5173/
2. **Vérifier**: Connexion = 🟢 "En direct"
3. **Mode**: Cliquer "En direct"
4. **Scénario**: Sélectionner "Pic de prix"
5. **Lancer**: Cliquer "Lancer le scénario"
6. **Observer**:
   - Compteur "Simulation en cours..."
   - Prix de l'électricité × 5 (graphique rouge monte)
   - Active Actions = "Peak Shaving" apparaît
   - Grid Power diminue (on achète moins)
   - Battery SoC diminue (décharge pour compenser)
7. **Résultat final** (~5 min):
   - Message "Commande terminée"
   - Carte Finance montre les économies réalisées

### Test 2: Analyser une Période en Mode Historique

1. **Mode**: Cliquer "Historique"
2. **Dates**: 
   - Du: 2025-06-15
   - Au: 2025-06-20
3. **Afficher**: Cliquer "Afficher la période"
4. **Observer**:
   - Tous les graphiques affichent 5 jours complets
   - Zoomer sur le graphique flux énergétiques
   - Voir les patterns journaliers (charge nuit, décharge jour)
   - Identifier les jours avec anomalies (drapeaux rouges)

### Test 3: Comparer Scénarios

1. **Lancer** "Fonctionnement normal" → Noter le Tier 1 Protected
2. **Lancer** "Coupure du réseau" → Comparer:
   - Tier 1 reste-t-il ✅?
   - Coverage Ratio descend à combien?
   - Hard Shedding s'active-t-il?

---

## 🎓 Concepts Clés à Retenir

### 1. **Tier 1 = Priorité Absolue**
La réfrigération DOIT toujours être alimentée. Si Tier 1 passe à ❌, c'est une alerte critique (rupture chaîne du froid → pertes produits → risque sanitaire).

### 2. **MPC = Cerveau du Système**
Le contrôleur prédictif optimise sur 1 heure (4 timesteps):
- Minimise les coûts
- Protège Tier 1
- Respecte les contraintes batterie (SoC, puissance)

### 3. **Pipeline Temps Réel**
Chaque timestep (15 min en simulation, instantané en temps réel):
```
Données → Prévision → Optimisation → Dispatch → Vérification → Dashboard
```

### 4. **Modes Complémentaires**
- **Live**: Voir ce qui se passe MAINTENANT (monitoring opérationnel)
- **Historique**: Analyser le PASSÉ (reporting, audit, optimisation)

---

## 🐛 Troubleshooting

### Problème: Dashboard affiche "Hors ligne" ou "Mode démonstration"

**Cause**: Backend FastAPI ne répond pas

**Solution**:
```powershell
# Vérifier que le backend tourne
docker compose ps backend

# Tester l'API
curl http://localhost:8000/health

# Relancer si besoin
docker compose restart backend
```

### Problème: "Aucune mesure disponible" en mode Historique

**Cause**: Aucun scénario n'a été lancé, TimescaleDB est vide

**Solution**:
1. Passer en mode "En direct"
2. Lancer un scénario (n'importe lequel)
3. Attendre la fin
4. Repasser en mode "Historique"

### Problème: WebSocket se déconnecte sans cesse

**Cause**: Le backend exécute un scénario (CPU occupé)

**Solution**: Attendre la fin du scénario (5 minutes max)

---

## 📚 Pour Aller Plus Loin

- **Documentation complète**: `DASHBOARD_EXPLICATION.md` (600+ lignes)
- **Architecture technique**: `ARCHITECTURE_TECHNIQUE.md`
- **Guide présentation**: `GUIDE_PRESENTATION.md`
- **Dataset**: `docs/DATASET.md`

---

## ✅ Checklist de Test

- [ ] J'ai ouvert le dashboard (http://localhost:5173/)
- [ ] J'ai vérifié la connexion (🟢 En direct)
- [ ] J'ai compris les 6 métriques principales
- [ ] J'ai lancé un scénario en mode Live
- [ ] J'ai observé les graphiques se mettre à jour
- [ ] J'ai testé le mode Historique
- [ ] J'ai comparé "Fonctionnement normal" vs "Pic de prix"
- [ ] Je comprends la différence entre Mock et Réel
- [ ] J'ai lu la section Troubleshooting

**Durée totale**: 15-20 minutes

---

**Bon test! 🚀**
