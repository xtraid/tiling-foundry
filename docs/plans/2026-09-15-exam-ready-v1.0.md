# Roadmap v1.0.0 — Exam Ready

Data: 15 settembre 2026. **Release: TODO.** Scope concordato per preparare la
difesa del progetto. **S1 e S2 sono FATTO**, con setup isolato e nuovi dossier
SAT/UNSAT offline verificati; S3–S6 e la pubblicazione restano da eseguire.

L'obiettivo è poter clonare una versione precisa, inserire una formula nuova,
eseguire il progetto con pochi comandi e mostrare un dossier completo con PDF.
La documentazione deve aiutare a spiegare contributi, correttezza e limiti.

**Milestone principale: v1.0.0 pubblicata e verificata come versione d'esame.**
Il checkpoint in fondo al piano si chiude soltanto dopo la verifica della
versione pubblicata. Un freeze locale o una PR integrata non lo completano.
Scadenza confermata dall'utente il 17 settembre: **mercoledì 23 settembre 2026**.
Obiettivo operativo: release pubblicata e verificata entro **domenica 20**, con
lunedì e martedì dedicati alle prove. L'orario della scadenza non è ancora indicato.

## Scope e ordine del lavoro

La release riguarda la baseline seriale esistente: riduzione Yang–Zhang,
reference, optimized, Boolean Z3, Wang Z3, checker, renderer e dossier.
Il lavoro aggiunge accesso semplice, riproducibilità e chiarezza espositiva.

Interfaccia prevista: **`demo-setup` implementato e verificato in S1**;
`demo` implementato e verificato in S2;
`demo-check` resta da implementare e verificare in S3:

```bash
make demo-setup
make demo INPUT=examples/professore.cm13
make demo-check
```

`demo` deve produrre il dossier completo e `report.pdf`, poi stamparne il
percorso. I nomi dei target potranno adattarsi ai comandi già esistenti,
mantenendo un solo percorso documentato. `professore.cm13` è il file da creare
con l'input proposto durante la dimostrazione.

| Sessione Astra xhigh | Stato | Risultato | Stima |
|---|---|---|---|
| S1 | FATTO | Clone pulito e setup completo | 2–3 ore |
| S2 | FATTO | Formula nuova → quattro motori → dossier e PDF | 4–6 ore |
| S3 | TODO | Suite breve commentata e regressioni della demo | 2–3 ore |
| S4 | TODO | Documentazione più chiara e utile alla difesa | 2–3 ore |
| S5 | TODO | Prova isolata, offline e sul computer dell'esame | 3–4 ore |
| S6 | TODO | PR, freeze, pubblicazione e verifica dal tag | 1–2 ore |

Totale stimato: **14–21 ore**, più **2–4 ore di riserva**. Sono stime di lavoro
con verifica e revisione, non garanzie; download, CI e ambiente possono
allungare il calendario. S2 contiene la maggiore incertezza tecnica.

Calendario obiettivo aggiornato il 19 settembre: chiusura S2 sabato 19, poi
S3/S4; S5 e S6 domenica 20, inclusa la prova sul computer dell'esame.
La QA di S2 ha richiesto correzioni sui nuovi input e il margine è diminuito.
Stima residua **dopo S2: 8–12 ore effettive**, più 2–4 ore di riserva e attese
esterne. La release verificata il 20 resta un obiettivo, non un esito garantito;
la prova sul computer dell'esame e la verifica dal tag pubblico sono necessarie.
Il calendario non anticipa l'autorizzazione alle singole sessioni o alla
pubblicazione e va rivisto se emergono problemi tecnici o indisponibilità.

## S1 — Clone pulito e setup completo

Verificare lo stato del repository e la base integrata prima di iniziare.
Lavorare sulla feature branch dedicata e conservare il file utente
`examples/sudoku3.cm13`, le QA e gli handoff precedenti.

- Preparare un target che costruisca la libreria e configuri i due ambienti
  Python con i lock esistenti, rispettando le versioni richieste.
- Elencare i prerequisiti Linux, incluso LaTeX e quanto serve al PDF; rendere
  comprensibile una dipendenza mancante prima di avviare la ricerca.
- Provare l'installazione in un clone pulito e in un ambiente isolato, senza
  riusare build, ambienti Python o file ignorati del server.
- Documentare download e comandi esatti; dopo il setup la demo deve poter
  funzionare senza rete. Non usare `pip` globale.

**Completamento:** il clone isolato arriva alla prima esecuzione documentata
con tutte le dipendenze necessarie al dossier, e conserva log e ambiente.

**Chiusura verificata il 15 settembre:** `make demo-setup` prepara la libreria
condivisa, i due ambienti Python con `uv sync --locked` e il PDF usando il
template reale. Clone, home, cache e installazione Python inizialmente vuoti;
home dell'host nascosta. Dopo il setup, il comando README sul SAT canonico è
riuscito con rete disabilitata tramite namespace: dossier/PDF di 23 pagine in
36,095 s, quattro motori concordi, sei checker verdi e trace complete.
Validati bundle, asset, copia input/hash e commit della fixture; QA visiva
campionata su cinque pagine. Verdi otto controlli d'errore del setup, 17 binari C,
build dello scaffold OpenMP e dieci test dossier v1/TeX. Review e re-review
senza finding residui. I tempi sono osservazioni di questa prova.

Base operativa `2e3ca52`; il candidato è verificato nel solo clone QA detached
`abe06ff`, tree `f38dca5`, con 463 input coincidenti prima del test. La sessione
è stata poi fissata nel checkpoint locale `e179cc1`, all'avvio di S2.
Evidenze, comandi, ambiente e handoff:
`build/exam-ready-s1/resume-20260915T161536/`. S1 verifica il caso noto già
distribuito; input nuovi SAT/UNSAT, QA completa e prova sul computer dell'esame
restano nelle sessioni successive.

## S2 — Input nuovo, dossier completo e PDF

Accettare direttamente un file Cubic Monotone 1-in-3 senza risultato atteso.
La guida deve spiegare il formato: intestazione `p cm13 n n`, con `n > 0`,
seguita da `n` clausole di tre indici positivi tra `1` e `n`, terminate da `0`.
Ogni variabile compare esattamente tre volte nell'intera formula; le eventuali
ripetizioni vengono contate. Non è un ingresso per SAT generico.

Il primo lavoro è risolvere il ruolo di `expected_status`, oggi presente nei
casi, nel documento della run, nei validatori e negli asset. Separare
l'aspettativa indipendente di un test noto dalla decisione osservata su input
libero: non copiare il risultato del solver in un campo poi presentato come
conferma indipendente. Conservare la compatibilità dei dossier precedenti.
Un eventuale adattamento contrattuale deve essere minimo, motivato dal caso
concreto e revisionato; non introdurre preventivamente schemi o framework.

- Conservare una copia immutabile dell'input con hash e commit del progetto.
  La riduzione e tutti i motori devono consumare quell'input identificato.
- Eseguire reference, optimized, Boolean Z3 e Wang Z3 una volta ciascuno;
  riusare adapter, esportatori, checker e catena di composizione esistenti.
  Figure e PDF consumano i risultati registrati, senza solve o rerun nascosti.
- Mostrare avanzamento reale: parsing, riduzione, motori, verifiche, figure,
  PDF. Identificare ogni esecuzione e impedire il riuso accidentale di output
  vecchi come risultato della nuova formula.
- Gestire timeout e interruzione sull'intero gruppo di processi, inclusi
  renderer e LaTeX; conservare log utili e liberare le risorse.
- Distinguere SAT, UNSAT, UNKNOWN, timeout, errore, disaccordo dei motori e
  trace tronca. Nessuno stato inconcludente può essere presentato come UNSAT.
- Presentare come riuscito soltanto un dossier completo e validato. Gli
  output parziali restano diagnostici. Non inventare witness o certificati
  UNSAT: dichiarare esattamente quali motori e controlli sostengono l'esito.
- Confrontare status e validità dei witness, senza richiedere che motori
  diversi trovino lo stesso witness. Non aggiungere vincoli iniziali nascosti
  per rendere più semplice la formula proposta.

**Completamento:** cambiare formula non richiede modifiche a codice o risultati
attesi; almeno un nuovo SAT e un nuovo UNSAT producono dossier e PDF coerenti.
Misurare separatamente la durata del dossier sulla macchina scelta, senza
promettere tempi costanti per qualsiasi formula.

**Chiusura verificata il 19 settembre:** candidato `98718b2`, dopo i checkpoint
contratti `a3ecd66`, comando `c737f7a` e fix di accettazione. Due input nuovi a
tre variabili, verificati per enumerazione indipendente, hanno prodotto dossier
completi nel clone QA con rete disabilitata: **SAT 70,316 s / 19 pagine** e
**UNSAT 37,702 s / 20 pagine**. Nessun risultato atteso passato alla demo;
copia/hash, quattro motori concordi, trace complete, bundle e asset validati.
Tutte le 39 pagine sono coperte dalla QA: lettura iniziale integrale, confronto
dei raster finali e ispezione di tutte le dieci pagine modificate.

Review del codice e dei fix senza finding residui; nessun finding PDF bloccante.
Resta la nota minore P-M1: una riga secondaria MRV è parzialmente coperta, ma le
informazioni della decisione sono ripetute interamente nel riquadro principale.
Le panoramiche di regioni larghe richiedono zoom, come documentato nella guida.
Renderer finale **337/337**; **87 asset canonici rigenerati identici**. Il gate
generale precedente aveva 17 C e 232 Python verdi; i fix successivi sono coperti
da gate mirati, test dei processi e nuove prove offline, senza ripetere i motori
all'interno di una run. Core, ABI, oracoli, lock e dossier v1 preservati.

Limite osservato: il primo SAT a sei variabili supera i 100000 eventi per trace.
Ora fallisce esplicitamente prima di export/Z3 (39,302 s nella prova), senza
dossier incompleto presentato come successo. Nessuna garanzia su input arbitrari.
Fonti: `build/exam-ready-s2/handoff-final.md`, `acceptance-summary-final.json`,
review finali SAT/UNSAT e [piano S2](2026-09-15-exam-ready-s2.md).
La prova sul computer dell'esame e la verifica della versione pubblicata restano
rispettivamente S5 e S6.

## S3 — Suite breve spiegabile durante l'esecuzione

Preparare sei controlli rappresentativi, annunciati con una frase che spieghi
cosa viene verificato e perché:

1. Lettura di un input valido.
2. Rifiuto di un input malformato o fuori dai vincoli del problema.
3. Caso SAT con verifica indipendente del witness.
4. Caso UNSAT noto, senza generare un witness inesistente.
5. Accordo reference/optimized e confronto con Z3 su istanze piccole.
6. Alterazione di una tessera e rifiuto del witness da parte del checker.

La suite deve fermarsi su un fallimento e restituire un esito di processo
corretto. Aggiungere regressioni mirate della nuova demo per timeout,
interruzioni, errori, output incompleti e seconda esecuzione, senza duplicare
l'intera suite del progetto nel comando dimostrativo.

**Completamento:** controlli comprensibili, fallimenti riconoscibili e durata
misurata. L'obiettivo di **30–60 secondi dopo il setup** riguarda questa suite,
non il dossier; non diventa una soglia temporale della CI.

## S4 — Documentazione leggibile e utile alla difesa

Revisionare README, home, guida alla demo, Presentazione, pipeline ed esempio
guidato. Mettere prima problema, contributo, comandi e risultato; eliminare
introduzioni generiche, ripetizioni, gergo superfluo e riferimenti ai task
interni dal percorso principale. Accorpare le spiegazioni duplicate e usare
frasi concrete, esempi reali e affermazioni misurate.

Rendere meno prominenti cronologie e dettagli operativi; conservare accessibili
prove, dati, riferimenti scientifici e limiti. Distinguere il risultato teorico
di Yang–Zhang, l'implementazione realizzata e le verifiche sperimentali.
Spiegare la differenza tra controllo di un witness SAT e risultato UNSAT.
Mantenere le etichette semantiche e le distinzioni necessarie alla correttezza.

**Completamento:** un lettore segue il percorso senza conoscere la storia dei
task; comandi, link, figure e pagine modificate passano i controlli pertinenti.

## S5 — Prova generale e verifica dell'ambiente d'esame

- Ripetere esattamente i comandi della guida da clone isolato: setup con rete,
  poi demo e suite senza rete, senza dipendenze da percorsi personali.
- Provare almeno un nuovo SAT e un nuovo UNSAT con struttura diversa dai casi
  canonici, oltre a input errato, timeout, interruzione e seconda esecuzione.
- Revisionare i nuovi PDF: input, risultati, titoli, didascalie, impaginazione
  e sezioni non applicabili. La compilazione riuscita da sola non basta.
- Aggiungere una verifica CI mirata della demo, usando gli stessi comandi
  locali; eseguire i gate pertinenti a codice, contratti, renderer e Pages.
- Provare sul computer della presentazione. Se si usa il server, verificare
  trasferimento e apertura della copia del dossier senza repository o rete.
- Preparare materiale offline coerente con la versione candidata, registrare
  tempi effettivi di suite e dossier e individuare eventuali problemi bloccanti.

**Completamento:** percorso riproducibile e prova reale di apertura riusciti,
QA conservata e revisione finale senza problemi bloccanti.

## S6 — Freeze, pubblicazione e controllo della versione distribuita

Completare PR e revisione, aggiornare i metadati di versione pertinenti e
preparare note di release con contenuto, piattaforma verificata, comandi e
limiti. Fissare commit e tree del candidato verificato e controllare la CI.
Dopo il merge, confrontare il tree integrato con il candidato; eventuali
differenze richiedono verifica prima del tag. Eseguire tag `v1.0.0` e GitHub
Release secondo l'autorizzazione del task applicabile, poi controllare il
risultato pubblico.

Provare un nuovo clone del tag pubblicato con gli stessi comandi documentati,
inclusa l'esecuzione offline dopo il setup. La formalizzazione di questo piano
non esegue pubblicazione o implementazione delle sessioni.

## CHECKPOINT PRINCIPALE — v1.0.0 PUBBLICATA E VERSIONE D'ESAME VERIFICATA

**Stato: TODO. Questo è il traguardo della preparazione tecnica.**

- [ ] S1–S5 concluse e verificate; nessun problema bloccante aperto, note
  minori residue esplicite e compatibili con la demo.
- [ ] PR integrata, revisione chiusa e CI pertinente verde sul codice
  candidato; SHA e tree integrati confrontati con quelli congelati.
- [ ] Tag `v1.0.0` e GitHub Release pubblici, coerenti con il commit verificato.
- [ ] Clone nuovo del tag: comandi della guida riusciti, demo e suite offline
  dopo il setup, nessuna dipendenza da file locali non distribuiti.
- [ ] Dossier completi validati su input nuovi SAT e UNSAT; PDF revisionati,
  suite commentata riuscita e tempi effettivi registrati.
- [ ] Guida e note della release riportano prerequisiti, comandi, contributi
  e limiti; materiali offline trasferiti e aperti sul computer dell'esame.
- [ ] Versione da mostrare fissata precisamente per demo, slide e materiali;
  conservati SHA, tag, URL release, log, ambiente, tempi e QA. Registrare
  anche gli hash degli eventuali allegati pubblicati.

**Segnare FATTO soltanto dopo pubblicazione e verifica successiva dal tag.**
Se emergono problemi, correggere e ripetere i controlli pertinenti prima della
chiusura; il solo merge o freeze non sostituisce questo checkpoint.

## Dopo la release e gestione delle sessioni

Ordine: **release verificata → prove e difesa → T99 → T100 → fase C → fase D**.
Restano fuori dallo scope Exam Ready: T99 completo, refactor T100, OpenMP,
`TaskPlan`, nuove ottimizzazioni, grandi campagne di benchmark, supporto
Windows/macOS e riscrittura integrale della documentazione.

Conservare indipendenza degli oracoli, ABI, ownership e semantica del core;
renderer e documentazione restano consumatori downstream. Non duplicare la
pipeline né trasformare `run.json` in un motore di orchestrazione.

Ogni sessione ha un responsabile distinto quando pratico; il coordinatore
verifica il risultato prima della chiusura. Lasciare un handoff breve con
stato (`TODO`, `IN CORSO`, `FATTO`, `BLOCCATO`), commit, risultati verificati,
evidenze, rischi e prossimo passo. Conservare QA e modifiche dell'utente;
eseguire controlli proporzionati ed evitare cambiamenti concorrenti alle
stesse dipendenze. Usare la sessione di riserva per problemi emersi, mantenendo
prioritari il checkpoint di pubblicazione e il tempo per le prove orali.
