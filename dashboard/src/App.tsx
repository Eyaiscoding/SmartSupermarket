import { useState, type FormEvent } from 'react';
import { Activity, AlertTriangle, ArrowRight, CalendarDays, Play, Zap } from 'lucide-react';
import { useDashboard } from './hooks/useDashboard';
import { SCENARIOS, type Scenario } from './api/types';
import { dateTime } from './lib/format';
import { StatusCards } from './components/StatusCards';
import { Finance } from './components/Finance';
import { Charts } from './components/Charts';
import { Operations } from './components/Operations';
const connectionLabels = {
  live: 'En direct',
  reconnecting: 'Reconnexion',
  offline: 'Hors ligne',
  mock: 'Démonstration',
};
export default function App() {
  const data = useDashboard();
  const [intensity, setIntensity] = useState<'neon' | 'soft'>(() => {
    try {
      return localStorage.getItem('b2g-intensity') === 'soft' ? 'soft' : 'neon';
    } catch {
      return 'neon';
    }
  });
  const [draft, setDraft] = useState(data.range);
  const [rangeError, setRangeError] = useState('');
  const last = data.records.at(-1);
  const breach = data.records.find((r) => !r.tier1Protected);
  function applyRange(event: FormEvent) {
    event.preventDefault();
    if (!draft.start || !draft.end || draft.start > draft.end) {
      setRangeError('La date de début doit précéder la date de fin.');
      return;
    }
    setRangeError('');
    data.setRange(draft);
  }
  function changeIntensity(value: 'neon' | 'soft') {
    setIntensity(value);
    try {
      localStorage.setItem('b2g-intensity', value);
    } catch {
      /* Theme remains usable when storage is disabled. */
    }
  }
  return (
    <div className="app dark" data-intensity={intensity}>
      <a className="skip-link" href="#main">
        Aller au contenu
      </a>
      <header className="topbar">
        <a href="#main" className="brand">
          <span className="brand-icon">
            <Zap size={22} />
          </span>
          <span>
            Supermarché <b>B2G</b>
            <small>BUILDING-TO-GRID</small>
          </span>
        </a>
        <div className="header-right">
          <span className={`connection ${data.status}`} role="status">
            <i />
            {connectionLabels[data.status]}
          </span>
          {data.mock && <span className="badge neutral">Données simulées</span>}
          <div className="intensity-control" role="group" aria-label="Intensité du thème">
            <span>Intensité</span>
            <div className="intensity-options">
              <button aria-pressed={intensity === 'neon'} onClick={() => changeIntensity('neon')}>
                Néon
              </button>
              <button aria-pressed={intensity === 'soft'} onClick={() => changeIntensity('soft')}>
                Doux
              </button>
            </div>
          </div>
        </div>
      </header>
      <main id="main">
        <div className="page-heading">
          <div>
            <span className="eyebrow">SUPERVISION ÉNERGÉTIQUE</span>
            <h1>
              L’énergie sous contrôle<span>.</span>
            </h1>
            <p>Réseau, stockage et flexibilité. Une vue d’ensemble de votre supermarché.</p>
          </div>
          <span className="simulation-tag">
            <Activity size={15} /> Simulation · été 2025
          </span>
        </div>
        <section className="toolbar" aria-label="Paramètres de simulation">
          <div className="mode-toggle" role="group" aria-label="Mode de visualisation">
            <button
              aria-pressed={data.mode === 'live'}
              className={data.mode === 'live' ? 'selected' : ''}
              onClick={() => data.setMode('live')}
            >
              <Activity size={15} />
              En direct
            </button>
            <button
              aria-pressed={data.mode === 'history'}
              className={data.mode === 'history' ? 'selected' : ''}
              onClick={() => data.setMode('history')}
            >
              <CalendarDays size={15} />
              Historique
            </button>
          </div>
          <div className="scenario-controls">
            <label htmlFor="scenario">Scénario</label>
            <select
              id="scenario"
              value={data.scenario}
              disabled={data.running}
              onChange={(e) => data.setScenario(e.target.value as Scenario)}
            >
              {Object.entries(SCENARIOS).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
            <button
              className="primary"
              onClick={data.run}
              disabled={data.running || data.runDisabled}
            >
              <Play size={14} />
              {data.running ? 'Simulation en cours…' : 'Lancer le scénario'}
            </button>
          </div>
        </section>
        {data.mode === 'history' && (
          <form className="date-controls" onSubmit={applyRange}>
            <label>
              Du{' '}
              <input
                aria-label="Date de début"
                type="date"
                min="2025-06-01"
                max="2025-09-30"
                required
                value={draft.start}
                onChange={(e) => setDraft({ ...draft, start: e.target.value })}
              />
            </label>
            <ArrowRight size={16} />
            <label>
              Au{' '}
              <input
                aria-label="Date de fin"
                type="date"
                min="2025-06-01"
                max="2025-09-30"
                required
                value={draft.end}
                onChange={(e) => setDraft({ ...draft, end: e.target.value })}
              />
            </label>
            <button type="submit" disabled={data.loading}>
              Afficher la période
            </button>
            <span className="muted">Du 01/06 au 30/09/2025 · bornes incluses</span>
            {rangeError && (
              <p role="alert" className="danger">
                {rangeError}
              </p>
            )}
          </form>
        )}
        {data.mock && (
          <div className="notice">
            <span className="dot export" />
            <span>
              {import.meta.env.VITE_USE_MOCK === 'true'
                ? 'Mode démonstration activé.'
                : 'Serveur indisponible : passage aux données de démonstration. Nouvelle vérification automatique.'}{' '}
              Un pas de 15 min toutes les 2,5 s.
            </span>
          </div>
        )}
        {data.runError && (
          <div className="error" role="alert">
            {data.runError}
          </div>
        )}
        {data.runSuccess && (
          <p className="notice" role="status">
            {data.mock
              ? 'Scénario de démonstration appliqué.'
              : 'Commande terminée. Les résultats disponibles sont affichés en direct ; l’historique dépend du stockage du serveur.'}
          </p>
        )}
        {data.error && (
          <div className="error" role="alert">
            {data.error}
            <button onClick={data.retry}>Réessayer</button>
          </div>
        )}
        {breach && (
          <div className="blocking-alert" role="alert">
            <AlertTriangle size={30} />
            <div>
              <strong>ALERTE CRITIQUE — Tier 1 non protégé</strong>
              <p>
                La protection de la réfrigération a été perdue le {dateTime(breach.timestamp)}.
                Intervention immédiate requise.
              </p>
            </div>
          </div>
        )}
        <div className="period-label">
          <span>
            {data.mode === 'live' ? 'FENÊTRE GLISSANTE · 96 PAS MAXIMUM' : 'PÉRIODE HISTORIQUE'}
          </span>
          <span>
            {last
              ? `${dateTime(data.records[0].timestamp)} → ${dateTime(last.timestamp)} · ${data.records.length.toLocaleString('fr-FR')} mesures`
              : 'En attente de mesures'}
          </span>
        </div>
        {data.loading ? (
          <div className="skeleton-grid" role="status" aria-label="Chargement des mesures">
            <span className="sr-only">Chargement des mesures…</span>
            {Array.from({ length: 6 }, (_, i) => (
              <div className="skeleton" key={i} />
            ))}
          </div>
        ) : last ? (
          <>
            <StatusCards record={last} />
            <Finance records={data.records} />
            <Charts records={data.records} />
            <Operations records={data.records} />
          </>
        ) : (
          <div className="card empty">
            <Activity size={32} />
            <h2>Aucune mesure disponible</h2>
            <p>
              {data.mode === 'live'
                ? 'Lancez un scénario pour alimenter le tableau de bord.'
                : 'Aucun résultat pour cette période. Choisissez d’autres dates ou lancez une simulation.'}
            </p>
          </div>
        )}
        <footer>
          <span>
            <Zap size={14} /> Supermarché B2G · MPC + DERMS
          </span>
          <span>Horaires de simulation · résolution 15 min · tarifs indicatifs</span>
        </footer>
      </main>
    </div>
  );
}
