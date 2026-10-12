# Phase 3 — inspection préalable des données

Inspection du 12/10/2026, avant modification du pipeline.

## Structure et alignement

| Fichier réel | Rôle détecté | Lignes | Colonnes |
|---|---|---:|---:|
| `data1/dataset_modified.csv` | Supermarché | 11 712 | 34 |
| `data1/smart_supermarket_neighbor_buildings_4months_15min1.csv` | Voisins | 70 272 | 8 |

Les noms sont inversés par rapport au descriptif fourni. Les deux séries vont du 2025-06-01 00:00:00 au 2025-09-30 23:45:00. Chaque bâtiment possède exactement les 11 712 horodatages du supermarché, espacés de 900 secondes, sans trous ni doublons de clé. Aucune valeur manquante ou non finie. Les 30 colonnes historiques du supermarché sont identiques à `data/dataset.csv`.

## Statistiques numériques

Unités inférées des noms et du schéma existant : puissances en kW, températures en °C. Aucun seuil sanitaire n'est déduit des plages observées.

### `dataset_modified.csv`

| Colonne | Unité | Minimum | Maximum | Moyenne | Valeurs manquantes |
|---|---|---:|---:|---:|---:|
| `occupancy` | personnes | 0.0000 | 188.0000 | 53.679559 | 0 |
| `temperature` | °C | 17.0000 | 39.2000 | 28.892623 | 0 |
| `humidity` | % | 43.3000 | 85.0000 | 65.305302 | 0 |
| `display_freezer_temp` | °C | -23.8000 | -12.6000 | -19.382812 | 0 |
| `freezer_room_temp` | °C | -27.4000 | -19.0000 | -23.815232 | 0 |
| `display_refrigerator_temp` | °C | 1.5000 | 7.3000 | 3.969356 | 0 |
| `cold_room_temp` | °C | 0.5000 | 4.0000 | 2.150803 | 0 |
| `solar_irradiance` | W/m² | 0.0000 | 1040.4000 | 179.196294 | 0 |
| `pv_voltage` | V | 0.0000 | 400.0000 | 204.573711 | 0 |
| `pv_current` | A | 0.0000 | 281.3900 | 48.373510 | 0 |
| `pv_power` | kW | 0.0000 | 112.4400 | 18.180545 | 0 |
| `total_consumption` | kW | 25.0390 | 58.1400 | 39.457799 | 0 |
| `display_freezer_power` | kW | 2.5000 | 4.8910 | 3.544638 | 0 |
| `display_refrigerator_power` | kW | 3.2000 | 6.4460 | 4.741336 | 0 |
| `cold_room_power` | kW | 4.3680 | 9.3250 | 6.833117 | 0 |
| `freezer_room_power` | kW | 5.9010 | 8.7430 | 7.395658 | 0 |
| `hvac_power` | kW | 0.0000 | 17.5080 | 7.437175 | 0 |
| `lighting_power` | kW | 0.6000 | 7.3980 | 3.292035 | 0 |
| `checkout_power` | kW | 0.1000 | 6.3600 | 1.810901 | 0 |
| `it_power` | kW | 2.3000 | 3.7800 | 2.905543 | 0 |
| `other_appliance_power` | kW | 0.7000 | 2.5750 | 1.499722 | 0 |
| `battery_voltage` | V | 580.0000 | 602.5000 | 581.908214 | 0 |
| `battery_current` | A | -25.8600 | 25.8600 | 0.047380 | 0 |
| `battery_capacity` | kWh | 250.0000 | 250.0000 | 250.000000 | 0 |
| `battery_soc` | % | 20.0000 | 76.2400 | 25.672532 | 0 |
| `battery_power` | kW | -15.0000 | 15.0000 | 0.029168 | 0 |
| `grid_power` | kW | -82.1910 | 72.2230 | 21.348655 | 0 |
| `energy_price` | EUR/kWh | 0.1037 | 0.3137 | 0.205252 | 0 |
| `demand_response` | sans unité | 0.0000 | 1.0000 | 0.048156 | 0 |
| `p2p_energy` | kW | -2.9740 | 2.4940 | -0.043811 | 0 |
| `forecast_consumption` | kW | 19.4660 | 61.9670 | 39.456968 | 0 |
| `forecast_pv` | kW | 0.0000 | 115.5950 | 18.569262 | 0 |
| `anomaly_score` | sans unité | 0.0000 | 0.4380 | 0.063235 | 0 |

### `smart_supermarket_neighbor_buildings_4months_15min1.csv`

| Colonne | Unité | Minimum | Maximum | Moyenne | Valeurs manquantes |
|---|---|---:|---:|---:|---:|
| `distance_km` | km | 0.5000 | 4.8000 | 2.150000 | 0 |
| `consumption_kw` | kW | 1.2000 | 241.6000 | 74.888704 | 0 |
| `energy_production_kw` | kW | 0.0000 | 360.2000 | 32.050477 | 0 |
| `energy_offer_kw` | kW | 0.0000 | 80.0000 | 7.673177 | 0 |

## Voisins

| Identifiant | Type | Distance (km) | Types de production observés |
|---|---|---:|---|
| B01 | Entrepôt logistique | 1.2 | Aucune, Solaire PV |
| B02 | École | 0.8 | Aucune, Solaire PV |
| B03 | Bureaux | 2.5 | Aucune, Solaire PV |
| B04 | Résidentiel | 0.5 | Aucune, Solaire PV |
| B05 | Hôtel | 3.1 | Aucune, Solaire PV |
| B06 | Usine légère | 4.8 | Aucune, Solaire PV |

## Cohérence et hypothèses

- La production réelle est nommée `energy_production_kw`, acceptée comme alias de `production`. Normalisation des en-têtes Unicode, espaces et casse, notamment distance_Km.
- Les chemins explicites Unicode sont acceptés, y compris les noms accentués. Les variables B2G_SUPERMARKET_CSV et B2G_NEIGHBORS_CSV utilisent par défaut les rôles réellement observés ci-dessus, sans renommer les données.
- 1 320 offres dépassent le surplus disponible, avec un excès maximal de 0,1 kW. Hypothèse : arrondis indépendants. Le matching plafonne chaque offre au minimum de l'offre annoncée et du surplus calculé.
- Les distances et types de bâtiment sont constants. Les types de production varient entre « Aucune » et « Solaire PV ». La liste statique indique la technologie observée et tous les types rencontrés ; le matching utilise le type du pas.
- P2P positif = import, négatif = export. Les champs p2p_import et p2p_export sont des puissances non négatives en kW ; conversion en kWh par multiplication par 0,25 h.
- Le CSV brut ne satisfait pas toujours le bilan énergétique : résidu absolu maximal 30,525 kW et moyen 8,474124 kW. Inverser le signe P2P ne résout pas l'écart (maximum 36,087 kW). Aucune correction silencieuse des données brutes.
- DERMS recalcule déjà le résidu réseau sans intégrer le P2P historique. En mode Phase 3, les nouvelles transactions remplacent ce P2P synthétique pour éviter un double comptage. Le bilan physique après dispatch utilise la consommation effective après délestage.
- Prix indicatifs en EUR/kWh, frais de transport financiers, sans pertes physiques supplémentaires ni taxes. Facteurs de production égaux à 1 par défaut. Les économies mesurent le gain par rapport à l'échange réseau remplacé.
- Les horodatages sans fuseau désignent une horloge de simulation commune. Les offres manquantes ou invalides ne sont jamais interpolées.
- Les températures restent facultatives. Une mesure manquante n'est pas remplie artificiellement pour la déclarer sûre.

Les spécifications détaillées des parties B et C étaient absentes du message reçu ; seuils, temporisations et écrans restent à préciser.
