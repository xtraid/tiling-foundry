# Exam Ready S4 — percorso documentale per la difesa

> **For agentic workers:** usare `superpowers:subagent-driven-development`;
> owner editoriale distinto, review indipendente, QA finale del coordinatore.

**Stato: FATTO il 20 settembre 2026.** Verifica finale e checkpoint locale
registrati in `build/exam-ready-s4/handoff-final.md`.

**Goal:** un lettore trova problema, contributo, comandi e risultati senza
conoscere la storia interna del progetto.

**Architecture:** revisione editoriale delle sei pagine esistenti. La guida
porta in apertura setup, suite e nuovo input; dettagli v1 restano accessibili.
Nessuna nuova pagina, route, figura, astrazione o modifica funzionale.

**Tech stack:** Markdown/Liquid, Jekyll e checker Pages esistenti.

**Spec:** S4 della roadmap `2026-09-15-exam-ready-v1.0.md`, già approvata;
preflight concreto in `build/exam-ready-s4/preflight.md`. Base `400c332`.

## Vincoli

- Preservare esattamente le frasi modificate dall'utente nel README; root
  separa gli hunk della sessione dalle sue modifiche non committate.
- Preservare ancore, include, fonti, label semantiche, alt/caption e asset.
- Lingua delle pagine invariata, inclusa Presentazione in inglese e la
  sezione italiana della suite nella guida.
- Distinguere risultato teorico Yang–Zhang, implementazione e prove eseguite;
  witness SAT controllabile, UNSAT osservato senza certificato inventato.
- Mantenere indipendenza e dipendenze condivise dei quattro motori esplicite.
- Comandi già verificati S1–S3; nessun claim di release già pubblicata.
- Solo sei pagine; niente nuovi test che ripetano la prosa, nuovo codice,
  renderer, PDF, benchmark, lock o cambi ai checker.
- Preservare QA/rollback e sudoku3; nessuna pubblicazione o cleanup.

## Task 1 — Sei pagine coerenti

File: `README.md`, `docs/index.md`, `docs/run_dossiers.md`,
`docs/presentazione.md`, `docs/pipeline.md`, `docs/worked-example.md`.

- [x] README: correggere stato dei comandi, aggiungere percorso Presentazione
  e togliere identificatori di task interni dalla sequenza futura.
- [x] Home: aprire con formula, regione e risultato, collegare la guida demo.
- [x] Guida: tre comandi in apertura, suite/v2 prima dei casi v1; conservare
  tutte le ancore, il formato di input e i dettagli di compatibilità.
- [x] Presentazione/pipeline: aperture concrete, teoria/implementazione/prove
  distinte; mantenere casi osservati, SAT/UNSAT e confini di verifica.
- [x] Esempio: rendere leggibile il caso a tre variabili e la sua assegnazione,
  raccordare la riproduzione senza duplicare il quickstart.
- [x] Eseguire diff-check, pages-check e i due moduli di test dei checker.
- [x] Review indipendente di semantica, comandi, link e preservazione del WIP.

## Task 2 — QA e chiusura

- [x] Generare Pages con immagine Jekyll già presente, rete disabilitata,
  sorgente read-only e nuova directory di output conservata.
- [x] Eseguire checker HTML generato e verificare le cinque pagine pubblicate
  a desktop/390 px, incluse ancore, figure, navigazione e reduced motion.
- [x] Verificare i sei file congelati contro review e output; registrare
  limiti o finding, aggiornare roadmap e handoff, checkpoint locale.

S5 prova d'esame/CI e S6 pubblicazione restano successive. I gate si ampliano
solo se una modifica effettiva o un finding lo richiede.

## Evidenze di chiusura

- Review indipendente: `build/exam-ready-s4/review-20260920-resume.md`, nessun
  finding; sei file congelati per hash, README utente preservato.
- Gate: Pages 41 route, 26 test checker, Jekyll offline e checker HTML
  41 pagine/929 riferimenti. Report `resume-20260920T032702Z/checks.md`.
- Browser: cinque pagine × due viewport (1440/390 px) × due preferenze di
  movimento. Prima passata 18/20 verdi; i due casi guida con scroll animato
  sono verdi nel supplemento che attende l'arrivo all'ancora. Sei verifiche
  mirate aggiuntive su home, guida ed esempio. Tutti i tentativi conservati.
- QA visiva desktop/mobile: report in `build/exam-ready-s4/closure/`;
  immagine home verificata dopo scroll e decodifica. Nessun finding residuo.
- Solo documentazione; nessun rilancio di solver/PDF o rigenerazione degli
  asset. I quattro hunk README dell'utente restano separati dal checkpoint;
  `examples/sudoku3.cm13`, rollback e QA preservati.
