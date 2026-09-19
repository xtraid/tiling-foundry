# Exam Ready S3 — suite breve narrata

> **For agentic workers:** usare `superpowers:subagent-driven-development`;
> responsabile S3 distinto, review indipendente e accettazione del coordinatore.

**Goal:** `make demo-check` esegue sei controlli rappresentativi, spiega cosa
dimostrano e si ferma al primo fallimento con un codice di uscita corretto.

**Architecture:** un comando lineare usa parser, adapter native, oracoli e
checker esistenti. Riusa il supervisore di `tools/demo.py` senza modificarlo.
Ogni motore viene eseguito una volta per caso; non genera dossier o PDF.

**Tech stack:** Linux, Python stdlib e ambiente core lockato, libreria C e Z3.

**Spec:** sezione S3 del piano `2026-09-15-exam-ready-v1.0.md`, già approvato.
Preflight tecnico: `build/exam-ready-s3/preflight.md`. Base locale `0247b29`.

## Vincoli globali

- Nessuna modifica a core, ABI, oracoli, formati, lock, renderer o supervisore S2.
- Sei blocchi annunciati prima di eseguirli; nessun framework di registrazione.
- Aspettative SAT/UNSAT note indipendentemente e distinte dall'esito osservato.
- UNKNOWN, eccezioni, disaccordo e witness non validi interrompono la suite.
- Nessun download o setup implicito; prerequisiti mancanti indicano il setup.
- Nessuna attesa artificiale: 30–60 secondi è un obiettivo da misurare,
  non una soglia CI. Misurare separatamente dal dossier.
- Preservare README utente, `examples/sudoku3.cm13` e ogni QA/rollback.
- Unica PR complessiva in S6; qui solo checkpoint locali.

## Decisioni concrete

1. Leggere `tests/instances/pipeline_sat.cm13` col parser C e controllarne
   il contenuto atteso.
2. Rifiutare `tests/fuzz/corpus/cm13/malformed_domain.cm13` precisamente come
   errore di dominio: un errore I/O non dimostra il rifiuto dell'input.
3. Risolvere il SAT con reference e verificare tiling e assegnazione tramite
   il percorso indipendente esistente. Il caso ammette `(False, True, False)`.
4. Risolvere `tests/instances/pipeline_unsat_search.cm13`: la clausola
   `4 4 4` richiederebbe `3*x4 = 1`. Richiedere UNSAT e witness assenti.
5. Confrontare i risultati reference già ottenuti con optimized, Boolean Z3
   e Wang Z3 su entrambi i casi. Controllare i witness SAT, senza richiedere
   che motori indipendenti scelgano lo stesso witness.
6. Copiare il tiling SAT e sostituire una sola tessera con un ID valido che
   viola un bordo imposto. Il checker deve rifiutare la copia e accettare
   ancora l'originale. Stampare la cella e gli ID coinvolti.

Una directory nuova `build/demo-check/run-*` conserva il log. Il worker scrive
un marker privato `complete` contenente `6/6\n` soltanto dopo tutti i controlli;
il parent richiede exit zero e marker esatto prima di annunciare successo.
CLI: `--timeout` positivo/finito, default 300, e `--output` nuovo facoltativo.
Make passa `TIMEOUT` raw nell'ambiente. Codici diretti: 124 timeout,
130/143 interruzioni, 1 fallimento, 2 argomenti; Make restituisce il suo nonzero.

## Review focus

- Errore infrastrutturale scambiato per rifiuto del parser.
- UNKNOWN o witness mancante/alterato scambiato per risultato terminale valido.
- Uscita zero senza tutti i controlli scambiata per suite riuscita.
- Timeout/interruzione propagati male dalla nuova entrypoint al supervisore.
- Seconda invocazione che riusa o altera i risultati della prima.

## Task 1 — Comando, regressioni e guida

File: nuovo `tools/demo_check.py`, `tests/python/test_demo_check.py`,
target in `Makefile`, sezione in `docs/run_dossiers.md`.

- [ ] Scrivere e osservare test fallenti per i sei controlli e i fallimenti
  elencati sopra; registrare RED/GREEN nel report di implementazione.
- [ ] Implementare il comando minimo con le API indicate nel preflight.
- [ ] Verificare una sola chiamata per motore/caso e il tamper di una tessera
  con ID valido; mantenere attivi i controlli anche con Python ottimizzato.
- [ ] Provare errori parser, UNKNOWN, disaccordo, witness invalidi e fail-fast.
- [ ] Provare marker assente/errato, codici di errore, argomenti invalidi,
  directory esistente e passaggio letterale di TIMEOUT da Make.
- [ ] Eseguire test S3 e regressioni CLI/processi S2. La matrice reale del
  supervisore esiste già: non duplicarla, aggiungere il collegamento S3.
- [ ] Documentare sei controlli, comandi, prerequisiti, log e limiti.
- [ ] Review indipendente, correzioni pertinenti e checkpoint locale.

## Task 2 — Accettazione e chiusura

- [ ] Aggiornare il clone QA preservato al candidato revisionato.
- [ ] Eseguire due `make demo-check` offline, misurando separatamente i tempi.
- [ ] Verificare sei controlli, esito zero e directory distinte; confrontare
  hash di log e marker della prima esecuzione dopo la seconda.
- [ ] Verificare fonti congelate, modifiche utente preservate e gate pertinenti.
- [ ] Registrare evidenze, note residue e stato S3 nella roadmap e nell'handoff.

S4–S6 restano successive; il successo della suite sul server non sostituisce
la prova sul computer dell'esame o la verifica dal tag pubblico.
