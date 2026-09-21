# Exam Ready S5 — prova generale e computer d'esame

**Stato: IN CORSO.** Base `04a2919`, branch `feature/exam-ready-v1.0`.
Scope autorizzato dal continua dell'utente il 20 settembre. Coordinatore
`/root`, responsabile CI `/root/exam_s5_rehearsal`, review distinta prima
del checkpoint. S6 resta successiva.

L'utente ha eseguito la demo direttamente sul proprio PC Omarchy Linux
al commit `7ea377e`, con esiti ricevuti il 21 settembre e registrati sotto.
La prova Debian sul server e la verifica della macchina d'esame sono evidenze
separate; entrambe vanno registrate senza estendere i risultati da un host
all'altro. Il piano Exam Ready principale resta il criterio di accettazione.

## Scope e preservazione

- Clone QA da commit, home/cache/interpreti inizialmente vuoti, setup con
  rete e comandi della guida senza rete dopo setup.
- Un SAT con struttura diversa dal caso canonico e un nuovo UNSAT, input
  errato, timeout, interruzione e seconda esecuzione. Aspettative dei test
  stabilite indipendentemente, mai passate alla demo come risultato atteso.
- Validazione input/hash/commit, quattro motori, trace, bundle e PDF;
  revisione visiva integrale dei nuovi PDF e materiali offline identificati.
- CI minima nel job renderer esistente: setup, suite e un input libero SAT;
  mantenere smoke v1, senza anticipare T99 o duplicare la pipeline.
- Istruzioni e prova Omarchy con prerequisiti verificati sulle fonti ufficiali,
  tempi misurati sul PC e apertura reale dei PDF. Nessuna installazione o
  modifica remota implicita prima di conoscere i prerequisiti mancanti.
- Preservare i quattro hunk README utente, sudoku3, QA e rollback. Backup
  iniziale in `build/exam-ready-s5/before/`. Nessun push/merge/tag/release.

## Checklist

- [x] Preflight CI e stato locale: `build/exam-ready-s5/preflight-ci.md`.
- [x] Modalità d'esame confermata: esecuzione locale su Omarchy.
- [x] CI mirata implementata, verificata localmente e revisionata (`7ea377e`).
- [x] Setup da clone/home/cache vuoti; log e ambiente conservati.
- [x] Suite, SAT/UNSAT e casi d'errore offline; prima run preservata.
- [x] Dossier/PDF validati e QA visiva completa sul server; finding chiusi.
- [x] Gate proporzionati sul candidato e review senza finding bloccanti.
- [x] Setup, suite, dossier e apertura PDF sul PC Omarchy; tempi registrati.
- [x] Materiali offline, hash, handoff e checkpoint locale delle correzioni.
- [ ] Apertura del PDF corretto su Omarchy, dopo il riscontro al vecchio commit.

## Gate

Una passata `make check` per l'integrazione della branch, test renderer
pertinenti e prove end-to-end del clone. Riusare i gate già verdi sui byte
invariati, compresa QA Pages S4; verificare eventuali sezioni documentali
nuove. Nessuna nuova campagna native/sanitizer/Valgrind per cambi soltanto
CI e documentali. La CI corrente conserva i propri job fino a T99.

La prova reale sul PC è acquisita. Il follow-up chiude i difetti visuali sul
server; resta da aprire il PDF corretto sul laptop. S5 resta IN CORSO fino
a quel riscontro. La pubblicazione verificata dal tag è S6.

## Riscontro della macchina d'esame — 21 settembre

Fonte: report dell'utente su Omarchy, branch `feature/exam-ready-v1.0`,
commit `7ea377e`. Rete scollegata manualmente dopo il setup,
`UV_OFFLINE=1` e `UV_PYTHON_DOWNLOADS=never`. I tempi qui sono quelli del
laptop; i PDF e i log locali del laptop non sono stati copiati sul server.

| Prova | Esito riferito | Tempo reale |
| --- | --- | --- |
| `make demo-setup` | PASS dopo installazione TeX Live; inizialmente mancava `pdflatex` | 28.644 s |
| `make demo-check` | PASS 6/6; durata interna 12.603 s | 12.781 s |
| `make demo INPUT=tests/instances/demo_sat.cm13` | SAT, quattro motori concordi, witness verificati, PDF aperto | 132.138 s |
| `make demo INPUT=tests/instances/pipeline_unsat_search.cm13` | UNSAT, quattro motori concordi, assegnamento/checker N/A, PDF aperto | 69.300 s |
| Input malformato | Errore parser; nessun UNSAT o dossier completato | Non misurato |
| `TIMEOUT=0.01` | Timeout esplicito 124; nessun dossier completato | Non misurato |
| Ctrl+C, seconda esecuzione e primo PDF | SIGINT 130, diagnostica preservata, nuova run SAT e primo PDF ancora presente | Non misurato |

Ambiente riferito: Python 3.14.7, Z3 5.1.0, NumPy 2.4.6, Pillow 12.2.0;
PNG, font e `libwang.so` caricati. Wang Z3 domina il tempo osservato sul laptop.
I codici 124/130 sono quelli della ricetta riportati da Make, non il codice
di uscita di Make stesso.

Percorsi sul laptop: primo SAT `build/demo/run-vzgafg1m/dossier/report.pdf`,
UNSAT `build/demo/run-y3hqhlzv/dossier/report.pdf`, riavvio SAT
`build/demo/run-2dttv76x/dossier/report.pdf`; diagnostiche interrotte
`build/demo/run-7g8yqqct` e `build/demo/run-xhx_xm0v` preservate.
Il difetto visuale UNSAT noto resta aperto in questa prova al vecchio commit:
non equivale all'accettazione dei PDF prodotti dal renderer corretto.

## Checklist ripetibile sul computer d'esame

Installare prima i prerequisiti della propria distribuzione dal
[README](../../README.md#quick-start), quindi eseguire dalla radice del clone:

```sh
git rev-parse HEAD
time make demo-setup
```

Scollegare la rete dopo il setup e usare i fixture validi del repository:

```sh
export UV_OFFLINE=1
export UV_PYTHON_DOWNLOADS=never
time make demo-check
time make demo INPUT=tests/instances/demo_sat.cm13
time make demo INPUT=tests/instances/pipeline_unsat_search.cm13
```

Questo comando UNSAT **sostituisce l'esempio ad hoc
`/tmp/tiling-exam-unsat.cm13`** della precedente checklist: due clausole con
header `p cm13 3 3` sono incomplete; cambiare l'header in `p cm13 3 2` viola
il dominio CM13. Il parser richiede `n` variabili, `n` clausole e tre
occorrenze per ogni variabile. Il fixture scelto è:

```text
p cm13 4 4
1 1 2 0
1 2 3 0
2 3 3 0
4 4 4 0
```

Le occorrenze sono corrette e la clausola finale impone `3*x4=1`, impossibile
per una variabile booleana. Nessun risultato atteso viene passato alla demo.
Aprire entrambi i PDF ai percorsi stampati, controllare accordo dei quattro
motori, figure e testi (MRV, propagazione, conflitto, rollback); nel dossier
UNSAT witness e checker devono essere non applicabili e la trace non deve
essere presentata come certificato indipendente.

Provare separatamente i due fallimenti attesi:

```sh
make demo INPUT=tests/fuzz/corpus/cm13/malformed_domain.cm13
make demo INPUT=tests/instances/demo_sat.cm13 TIMEOUT=0.01
```

Interrompere poi una demo SAT con Ctrl+C e rilanciarla. Verificare che usi
una nuova directory, conservi la diagnostica parziale e lasci apribile il
primo PDF riuscito. Registrare commit, durate e percorsi. Dopo la correzione
del layout basta ripetere l'apertura/QA del nuovo PDF UNSAT; la verifica
della versione pubblicata dal tag resta un criterio separato di S6.

## Correzioni dopo il riscontro Omarchy

- Trace: larghezza minima per separare testi e schede; altezza del corpo
  sufficiente per l'intera legenda, uniforme fra i frame animati. S5-I1 e il
  precedente residuo P-M1 chiusi nei PDF e negli asset rigenerati.
- Costruzione: il font fitting esistente si applica anche alle strisce fino
  a 15 segnali. Chiusa l'ulteriore sporgenza `r #12/#13/#14` rilevata dalla
  lettura completa del fixture usato sul laptop.
- Checklist: usa il fixture UNSAT valido esistente, con contratto CM13
  esplicito; README e diagnostica setup includono Arch/Omarchy.

Evidenze in `build/exam-ready-s5/omarchy-followup-20260921T134347Z/`:
regressioni prima/dopo, report `layout-review.md` e `fixture-final-review.md`,
PDF finali `narrow-final/dossier/report.pdf` e
`fixture-final/dossier/report.pdf`, entrambi di 26 pagine. Ogni ricomposizione
preserva cattura, input/hash, `run.json` e TeX, senza rilanciare i solver.
La nuova run del fixture è riuscita in 35.093 s sul server; questo tempo
non sostituisce i 69.300 s riferiti su Omarchy.

Copia comoda del PDF corretto sul server:
`~/dossiers/tiling-foundry-unsat-corrected-20260921.pdf`.
SHA-256 `ef3a444fdd2f6ad88c4c8f33b5dc2f5174ea4f1dd84d4b635651bee12b0c2c7d`.
Questa copia deve ancora essere aperta sul laptop: il riscontro originale
dell'utente riguarda la versione precedente del renderer.
