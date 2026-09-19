# Exam Ready S2 — input libero e dossier completo

> **For agentic workers:** usare `superpowers:subagent-driven-development` per
> eseguire e revisionare i task in sequenza. Il coordinatore verifica la chiusura.

**Goal:** `make demo INPUT=...` produce un dossier/PDF completo e verificato da
una formula CM1-in-3 nuova, senza risultato atteso fornito dall'utente.

**Architecture:** estendere in modo compatibile i contratti esistenti per
un'aspettativa assente; riusare la cattura v2 e i suoi consumatori. Un processo
supervisore gestisce il limite complessivo e l'interruzione del worker e dei
suoi figli. Nessuna seconda pipeline o seconda esecuzione dei motori.

**Tech stack:** Python stdlib, libreria C e adapter esistenti, ambienti uv
lockati, Z3, renderer esistente e pdfLaTeX. Linux resta la piattaforma supportata.

**Spec:** sezione S2 di `2026-09-15-exam-ready-v1.0.md`. L'analisi concreta dei
confini è conservata in `build/exam-ready-s2/contract-design.md`.

## Vincoli globali

- Base di sessione `e179cc1` (S1 verificata e committata localmente).
- Una PR complessiva in S6; commit locali per checkpoint. Nessun push/merge/tag.
- Core C, ABI, ownership, oracoli, lock e asset canonici restano invariati.
- Dossier v1 invariati; dossier v2 precedenti ancora leggibili e generabili.
- Ogni motore eseguito una volta. Il PDF consuma solo la cattura validata.
- Input nuovo copiato prima del parsing; hash, esportatori e motori usano quei byte.
- SAT richiede witness validi; UNSAT non inventa witness o certificati.
- UNKNOWN, timeout, errori, disaccordo e trace incomplete non producono successo.
- Non cancellare `examples/sudoku3.cm13`, QA, log, fixture o rollback precedenti.
- S3 suite narrata, S4 riscrittura documentale e S5 CI/QA finale restano separati.

## Decisioni del design

### Aspettativa assente e risultato osservato

`MultiEngineRunCase.expected_status` diventa `str | None`; nei trasporti il
campo resta obbligatorio e accetta `null`, `sat` o `unsat`. Il comando diretto
passa sempre `None`. Builder e validator stabiliscono prima che tutti i quattro
stati siano terminali e uguali; soltanto dopo controllano un'eventuale aspettativa.

```python
observed_status = statuses["reference"]
if any(status not in {"sat", "unsat"} for status in statuses.values()):
    raise PipelineSnapshotError("full-pipeline dossier forbids UNKNOWN results")
if any(status != observed_status for status in statuses.values()):
    raise PipelineSnapshotError("engine status mismatch")
if case.expected_status is not None and case.expected_status != observed_status:
    raise PipelineSnapshotError("known expected status mismatch")
```

Tutti i rami di witness, verifiche, tempi applicabili, asset e PDF usano lo stato
osservato. `agreement.expected_status` conserva esattamente l'aspettativa, anche
nulla. Gli stati duplicati in agreement devono coincidere con i rispettivi motori.

Il manifest narrativo autonomo necessita di un discriminante osservato esplicito
solo nella nuova forma; la forma legacy e gli hash canonici restano invariati:

```json
{"id":"demo-run","expected_status":null,"observed_status":"sat","source_sha256":"<sha256>"}
```

La nuova forma richiede `observed_status` esattamente quando expected_status è
null; i casi noti conservano i tre campi precedenti. Le ricevute dispongono già
dei quattro stati in agreement: non aggiungere un altro campo. Il PDF nuovo
indica che non è stato fornito un risultato atteso. I vecchi lettori stretti non
leggono la nuova variante; il codice aggiornato continua a leggere quella vecchia.

### Comando e controllo dei processi

Interfaccia principale: `make demo INPUT=percorso.cm13`, con `TIMEOUT=300` come
default configurabile in secondi. Il percorso diretto Python espone anche
output e capacità trace per diagnostica e test; rifiuta timeout non finiti o
non positivi e capacità fuori dal contratto esistente (2–100000 eventi).

Il supervisore usa soltanto stdlib, seleziona il Python core installato da S1 e
avvia un worker con `start_new_session=True`. Il limite include preflight,
copia input, parsing, riduzione, motori, validatori, renderer e LaTeX. In caso
di timeout/SIGINT/SIGTERM termina l'intero gruppo, attende brevemente e usa
SIGKILL per i figli ancora attivi. Raccoglie sempre il worker; nessun subprocess
di rendering o PDF può sopravvivere alla terminazione gestita.

Ogni invocazione crea una directory distinta sotto `build/demo/`, con input
immutabile, log e sottocartella dossier. Un output esplicito esistente è un
errore: non sovrascrivere o riutilizzare una run. I byte dell'input e il nome
originale sono registrati prima di avviare i motori; nei contratti si mantiene
un nome relativo portabile per la copia. Nessuna interpolazione shell dell'input.

Il worker chiama un solo percorso condiviso in `dossier.multi_engine`.
Il percorso dei casi JSON continua a chiamare lo stesso percorso, mantenendo
i metadati legacy. La sorgente viene copiata prima della cattura anche per i
casi JSON; native capture e trace exporter ricevono la copia, non l'originale.
Un callback facoltativo Python segnala parsing, riduzione, reference, optimized,
Boolean Z3, Wang Z3, verifiche, figure e PDF nei punti reali di esecuzione.
Il callback non cambia ABI o semantica dei solver.

Solo un worker concluso correttamente con dossier/PDF completi può stampare il
percorso di successo. Errori conservano input/log e indicano chiaramente lo stato
diagnostico. Eventuali artefatti parziali non sono presentati come dossier riusciti.

## Task 1 — Contratti e consumatori

File: `python/formats/run_case_v2.py`, `run_dossier_v2{,_builder,_bundle}.py`,
`narrative_assets.py`, `run_report_v2_tex.py`; `python/dossier/narrative_assets.py`;
`renderer/wang_narrative.py`; tre schemi JSON pertinenti; test dossier/renderer.

- [x] Aggiungere prima test fallenti per null SAT/UNSAT, aspettativa opposta,
  disaccordo, UNKNOWN e trace incompleta; preservare i test legacy.
- [x] Applicare i rami osservati descritti sopra e la variante chiusa del manifest.
- [x] Validare i collegamenti tra run e artefatti: source hash nativo, stato e
  completezza delle trace, stato dei summary Z3. Testare alterazioni coerenti
  degli hash del contenitore, così il test verifica il legame semantico.
- [x] Testare ricevute nullable e manifest alterato; il PDF mostra l'aspettativa
  assente. Controllare che i dati canonici non cambino.
- [x] Eseguire i test pertinenti, review indipendente e commit del checkpoint.

## Task 2 — Cattura da file e comando supervisionato

File: `python/dossier/multi_engine.py`, `python/native/multi_engine_pipeline.py`,
nuovo ingresso `tools/demo.py` e piccolo worker/modulo Python se necessario;
`Makefile`, README, guida dossier e test demo dedicati.

- [x] Test fallenti: file nuovo esterno, percorso con spazi, output già presente,
  input alterato dopo copia, un solo invio a ogni motore, progressione reale.
- [x] Estrarre il percorso condiviso della cattura senza duplicarne il corpo;
  copiare e fissare l'input prima del parsing e degli hash degli esportatori.
- [x] Aggiungere supervisore e worker con timeout complessivo e terminazione
  del gruppo; tenere insieme solo gli helper necessari a questo comando.
- [x] Testare timeout e interruzione con figli reali, incluso un figlio che
  ignora SIGTERM; nessun processo vivo residuo e nessun successo parziale.
- [x] Testare input malformato, dipendenza PDF mancante, trace troncata, errore,
  UNKNOWN e disaccordo; i messaggi distinguono questi esiti da UNSAT.
- [x] Documentare comandi, formato `p cm13 n n`, occorrenze cubicità, output,
  limite globale, diagnosi e assenza di garanzie temporali su input arbitrario.
- [x] Review del task e commit dopo i controlli pertinenti.

## Task 3 — Accettazione S2 e handoff

- [x] Usare due input nuovi conservati in `build/exam-ready-s2/inputs/`, con
  esiti individuati per enumerazione indipendente e mai passati alla demo.
  I primi casi a sei variabili restano evidenza dei limiti: il SAT ha superato
  100000 eventi per entrambe le trace e raggiunto il timeout di 300 s. Dopo il
  rifiuto anticipato delle trace incomplete, verificare i PDF su due nuovi casi
  a tre variabili (otto assegnazioni enumerate), senza aumentare i limiti.
- [x] Eseguire realmente entrambi i comandi, con rete disabilitata dopo il setup.
- [x] Riaprire dossier e asset coi validator; verificare copia/hash input,
  expected_status null, quattro motori concordi e trace complete.
- [x] Revisionare i PDF SAT/UNSAT e misurare separatamente ciascuna esecuzione.
- [x] Eseguire suite Python e renderer pertinenti, check documentali e regressioni
  v1/v2; niente matrice prestazionale non pertinente.
- [x] Review finale del range S2, chiudere finding e ricontrollare i fix.
- [x] Registrare commit, hash, log, limiti e QA; aggiornare S2 a FATTO soltanto
  dopo tutti i criteri. S3–S6 e pubblicazione restano TODO.

## Verifica del piano

| Confine | Produzione/consumo e verifica |
|---|---|
| Task 1 → Task 2 | None indica aspettativa assente; il worker lo passa senza solve preventivo. |
| Task 2 → Task 3 | Input copiato e run unica; QA controlla hash, esiti, trace e terminazione. |
| Task 1 → Task 3 | Vecchi dossier restano validi; nuove ricevute/PDF esplicitano l'assenza d'aspettativa. |
| Task 1 interno | Schemi, validator, builder, renderer e PDF condividono la distinzione atteso/osservato. |
| Task 2 interno | Timeout copre il worker completo; output parziale resta diagnostico. |
| Task 3 interno | Un test compilato o PDF aperto da solo non chiude i criteri di correttezza. |

Il piano applica lo scope S2 approvato. Le scelte di timeout, nome della copia
e variante nullable sono dettagli implementativi motivati dai confini esistenti;
restano soggetti a review. Non richiedono una nuova pipeline o un nuovo schema.

## Chiusura S2 — 19 settembre 2026

**FATTO** sul candidato `98718b2f3ef3bba48adb33af77615d0fac280c1c`.
I checkpoint precedenti sono `a3ecd66` (contratti), `c737f7a` (comando),
`5f722de` (rifiuto anticipato trace incomplete) e `a3b9723` (contact sheet).
L'ultimo fix riassume le annotazioni di costruzione solo quando non entrano;
frame canonici e dettaglio del singolo crossover restano invariati.

| Accettazione offline finale | SAT | UNSAT |
|---|---|---|
| Input nuovo | `inputs/acceptance-sat.cm13` | `inputs/acceptance-unsat.cm13` |
| Variabili / assegnazioni enumerate | 3 / 8 | 3 / 8 |
| Aspettativa passata alla demo | nessuna | nessuna |
| Esito dei quattro motori | SAT | UNSAT |
| Trace native | complete | complete |
| Witness check | sei superati | sei non applicabili |
| Durata completa osservata | 70,316 s | 37,702 s |
| PDF | 19 pagine | 20 pagine |

I percorsi di evidenza sono relativi a `build/exam-ready-s2/`.
`acceptance-summary-final.json` conserva percorsi e SHA-256 degli input/PDF;
`acceptance-validation-final.log` registra la riapertura con i validator.
`acceptance-final-page-comparison.json` copre le 39 pagine: 29 identiche alla
prima QA integrale, dieci modificate e ricontrollate visivamente nei report
`acceptance-sat-pdf-final-review.md` e `acceptance-unsat-pdf-final-review.md`.
Nessun problema bloccante; nota minore P-M1 MRV conservata ed esplicita.

Verifiche: `acceptance-gates.json` distingue il gate generale precedente
(17 C / 232 Python) dai gate incrementali dei fix; renderer finale 337/337,
87 asset canonical-pages rigenerati identici e 91 file protetti invariati.
Review cumulativa e dei singoli fix conservate; README dell'utente preservato.

I primi tentativi falliti restano evidenza, non risultati riusciti: trace oltre
capacità nel SAT a sei variabili, contact sheet troppo grande, annotazioni
costruzione sovrapposte. Le correzioni sono revisionate e verificate; i limiti
restano espliciti e i dati originali conservati. Setup S2 usa il clone isolato
e cache S1 già preparate, con rete disabilitata: non è una nuova prova di
installazione a cache vuota. Quel criterio è coperto dalla chiusura S1.

S3–S6 e pubblicazione restano TODO. Fonte operativa: `handoff-final.md`.
