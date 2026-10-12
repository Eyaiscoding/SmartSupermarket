# Supermarché B2G — dashboard

Application React + Vite + TypeScript strict, Tailwind CSS 4, Recharts, TanStack Query et WebSocket natif. Interface française responsive, thème sombre avec intensités Néon/Doux, suivi des charges critiques, énergie, finance et contrôle MPC/DERMS. Aucun fichier du backend n’est modifié.

## Installation

Node.js 22.12+ ou 24 LTS et npm sont nécessaires.

```sh
cd dashboard
npm install
cp .env.example .env
npm run dev
```

PowerShell : `Copy-Item .env.example .env`. Ouvrir l’adresse locale affichée par Vite. Pour lancer directement sans fichier `.env`, `npm install && npm run dev` suffit : la connexion réelle est tentée, puis le mode démonstration prend le relais si le serveur est inaccessible.

```sh
npm test
npm run lint
npm run format:check
npm run build
npm run preview
```

Test navigateur facultatif : `node scripts/browser-smoke.mjs` (Chrome installé, ou chemin via `CHROME_PATH`). Il démarre Vite sur le port 4173 avec une API interceptée dans la page, vérifie les interactions desktop/mobile, le repli mock, le retour au réel, le flux de 96 points, l’alerte Tier 1, la reconnexion et les erreurs d’historique. Les captures sont sauvegardées dans `artifacts/` (ignoré par Git). Aucun service backend n’est sollicité.

Le résultat de production est dans `dist/`, à servir par un hébergeur statique. Les variables Vite sont injectées à la compilation ; ne jamais y mettre de secret. Le serveur API doit autoriser l’origine du dashboard via CORS et proposer HTTPS/WSS si le dashboard est servi en HTTPS.

## Configuration

| Variable                  | Valeur par défaut       | Usage                                                                                      |
| ------------------------- | ----------------------- | ------------------------------------------------------------------------------------------ |
| `VITE_API_URL`            | `http://localhost:8000` | URL racine de FastAPI ; le WebSocket est dérivé automatiquement, y compris HTTPS → WSS.    |
| `VITE_USE_MOCK`           | `false`                 | `true` force les données simulées et désactive tout accès API.                             |
| `VITE_SCENARIO_TRANSPORT` | `websocket`             | `websocket` pour le backend actuel ; `rest` pour un backend diffusant ses exécutions POST. |

Redémarrer Vite après changement des variables. `.env.example` active explicitement la démonstration. Pour le réel, régler `VITE_USE_MOCK=false` et lancer le backend selon son README.

### Particularité du backend existant

Le backend de ce dépôt attend `{"scenario":"none"}` **sur le WebSocket** et lance une simulation propre à cette connexion. Il transmet les résultats après le calcul, puis une trame `{"type":"summary","data":...}`. `POST /api/v1/scenario` lance une autre simulation et ne diffuse pas vers les connexions WebSocket existantes. Le dashboard utilise donc par défaut une nouvelle connexion WebSocket pour chaque lancement, sans exécuter deux fois le scénario. Il n’envoie jamais automatiquement une commande de relance lors d’une reconnexion interrompue : cela évite les doubles exécutions.

Le mode `rest` utilise exactement `POST /api/v1/scenario` avec `{"scenario":"..."}`, écoute passivement le WebSocket et actualise les requêtes après la réponse. Il est prévu pour un serveur diffusant les exécutions POST. Avec le backend actuel, seules les mesures persistées sont récupérables dans ce mode. Une réponse 404 de `/latest` signifie qu’aucun résultat n’est encore disponible, pas que le serveur est hors ligne. L’historique réel nécessite le stockage TimescaleDB du backend ; une erreur 503 est affichée explicitement.

### Connexion et démonstration

- `/health` est contrôlé toutes les 15 secondes. Un échec active le mode démonstration, clairement indiqué. Un rétablissement repasse au réel, sans mélanger les jeux de données.
- Le flux natif se reconnecte avec délai exponentiel de 1 à 30 secondes et léger aléa. Les trames invalides sont signalées et ignorées. Un scénario interrompu doit être relancé explicitement. Délai maximal d’attente d’un scénario : 5 minutes.
- En direct, les 96 derniers horodatages uniques sont conservés et triés ; un doublon remplace la mesure précédente. Les totaux concernent cette fenêtre, et non une journée complète si moins de 96 pas sont disponibles.
- Les données simulées couvrent le 01/06/2025 au 30/09/2025 : 11 712 pas. Courbe solaire diurne, pointe du soir, SOC cyclique, actions et anomalies déterministes. Tier 1 toujours protégé, SOC entre 10 et 95 %. Un pas de 15 minutes avance toutes les 2,5 secondes. Les scénarios modifient réellement les données ; le pic de prix permet de tester la courbe tarifaire.
- Le sélecteur historique utilise des dates inclusives. Un échec de l’historique sur un serveur joignable reste une erreur réelle, sans substitution silencieuse de chiffres.

## Contrat des données

REST : `GET /health`, `GET /api/v1/latest` (un objet), `GET /api/v1/history?start=...&end=...` (un tableau), `POST /api/v1/scenario`. Flux : `/ws/stream`. Scénarios : `none`, `forced_grid_outage`, `price_spike`, `sensor_corruption`.

```json
{
  "timestamp": "2025-06-01 00:00:00",
  "coverage_ratio": 0.94,
  "coverage_status": "AT_RISK",
  "active_actions": ["peak_shaving", "hvac_soft_shed"],
  "tier_1_protected": true,
  "battery_soc": 62.3,
  "grid_power": 12.4,
  "p2p_energy": 0,
  "anomaly_flag": false,
  "anomaly_source": null,
  "energy_price": 0.18
}
```

`energy_price` est facultatif (ou null), en €/kWh. `p2p_energy`, malgré son nom, est une **puissance en kW**. Actions acceptées : `peak_shaving`, `hvac_soft_shed`, `valley_filling`, `hard_shedding`.

`src/api/adapter.ts` vérifie les données inconnues et les convertit en `TimestepRecord` ; les composants n’utilisent que ce type. Les statuts sont recalculés depuis le ratio : normal ≥ 0,95 ; à risque ≥ 0,90 ; critique < 0,90. Une violation Tier 1 est conservée et déclenche une alerte sur toute la période. Le SOC hors plage de sécurité 10–95 % reste visible, sans écrêtage des mesures réelles ; les nombres non finis, SOC hors 0–100 %, ratios hors 0–1 et champs mal typés sont rejetés.

Les horodatages sans fuseau sont traités comme des heures de simulation fixes, encodées et affichées en UTC pour éviter une conversion variable selon le navigateur. Les dates avec décalage explicite sont converties en UTC. Toutes les dates affichent le format français ; les jours et heures d’agrégation suivent cette même convention.

## Calculs et tarifs

Tous les tarifs indicatifs sont centralisés dans `src/config/market.ts` : achat 0,18 €/kWh, vente 0,08 €/kWh, P2P 0,12 €/kWh, durée 0,25 h. `GRID_IMPORT_SIGN` définit le signe d’import du backend ; l’adaptateur applique cette convention une seule fois. Le modèle interne utilise toujours import positif et export négatif.

Les fonctions pures de `src/lib/energy.ts` calculent :

- achat = `max(gridPower, 0) × 0.25` kWh ; vente = `max(-gridPower, 0) × 0.25` kWh ;
- coût = achat × prix du pas, avec valeur par défaut seulement si le prix manque ;
- revenu = vente × tarif de rachat ; solde = revenu − coût ;
- P2P = `abs(p2pPower) × 0.25` kWh ; valeur = volume × tarif P2P.

La valeur P2P est affichée séparément : la convention de règlement financier P2P n’est pas fournie par le backend. Elle n’est pas ajoutée au solde. Un prix nul ou négatif est valide. Les totaux additionnent uniquement les pas reçus, sans interpoler de données manquantes. Les compteurs d’actions comptent les pas actifs, pas les épisodes. Les curseurs réseau, batterie et solde sont synchronisés sur l’horodatage ; l’histogramme agrégé conserve son propre curseur pour ne pas associer des périodes différentes.

## Organisation

`src/api/` : contrat, validation, REST, générateur. `src/hooks/` : connexion, scénarios, cache et modes. `src/components/` : indicateurs, finance, graphiques, opérations. `src/config/market.ts` : paramètres du marché. `src/lib/` : calculs et formatage. Les tests Vitest couvrent les imports/exports, les prix absents/nuls/négatifs, les deux signes P2P, les agrégations, les seuils de couverture, les erreurs de contrat, le dédoublonnage et les invariants des données simulées.

## Theme

Thème sombre industriel, jaune fluorescent dominant et fuchsia pour les ventes et anomalies. La palette et les tokens Tailwind v4 sont centralisés dans `src/styles/theme.css` ; les composants SVG utilisent ces mêmes variables. Modifier ce fichier pour ajuster les couleurs. `src/styles.css` définit la mise en page, les jauges, les tableaux et les interactions.

Le sélecteur **Intensité → Néon / Doux** remplace le thème clair/sombre. Doux atténue le jaune et le fuchsia et désactive les halos. Le choix est conservé dans `localStorage` (`b2g-intensity`), avec repli Néon si le stockage est indisponible. `prefers-reduced-motion` désactive les animations, y compris la bordure d’alerte Tier 1. Inter et Space Grotesk sont chargées depuis Google Fonts avec `display=swap` et polices système de secours.

Les légendes nomment les séries, les exports sont tracés en tirets et les prix en pointillés. Les montants nets restent verts ou rouges selon leur signe ; les charges critiques conservent leurs indicateurs de protection. Les anciens tests unitaires sont inchangés ; le script navigateur historique cible encore l’ancien bouton clair/sombre et n’est donc pas adapté à ce thème.

## Future work

Le suivi des températures est affiché à côté du Tier 1 : état global, mesures des
quatre capteurs, plages configurées et début des alertes. Une protection électrique
ne garantit pas une température correcte. Les capteurs absents sont indiqués
« Indisponible » ; le mode mock actuel ne simule pas ces mesures.
Pour les données réelles, configurer côté backend
`B2G_SUPERMARKET_CSV=data1/dataset_modified.csv`. Les seuils sont des paramètres
de simulation à valider, documentés dans `../docs/DATASET.md`.

- La logique de trading de niveau 3 (MPC décidant de vendre) **ne fait pas partie de ce dashboard**. Il observe les échanges décidés par le backend.
- Exposer les vrais tarifs, le sens de règlement P2P et le fuseau de simulation dans le contrat.
- Unifier le lancement POST et la diffusion WebSocket côté backend ; ajouter identifiants de run, progression, reprise et annulation côté serveur.
- Ajouter authentification et autorisation côté serveur avant exposition publique, ainsi que des tests d’intégration contre l’infrastructure réelle.
