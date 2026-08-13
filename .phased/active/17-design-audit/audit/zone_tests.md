# Zona 2 — I test che cementano

Metodo (dall'issue #17, lente 2 specie 2): **l'unità di rimozione è la COPPIA**
— ramo di codice + test che lo cementa. Per ogni difesa specie-1 della fase 2
(`audit/zone_recycling_code.md`, schede D1..D8) la guardia è stata tolta
sperimentalmente, i quattro file di test spa sono stati eseguiti **senza `-x`**
per raccogliere TUTTI i test che cadono, e il sorgente è stato ripristinato
subito dopo.

Comando di ogni esperimento:

```
pytest tests/test_spa_move.py tests/test_spa_commander.py \
       tests/test_spa_evaluator.py tests/test_spa_monitor.py -q -rf --tb=line
```

249 test raccolti, verde di partenza 249 passati. Ogni esperimento è stato
applicato e revocato da uno script che riscrive il file e poi ne rimette il
testo originale byte per byte; alla fine `git status --porcelain` non mostra
nulla sotto `src/` né sotto `tests/`. **Nessun esperimento sopravvive nel
commit.**

Per ogni test che cade si risponde alla domanda dell'issue — *questo scenario
esiste nel prodotto reale?* — con analisi dei chiamanti, non con opinione.

Tutti i verdetti restano VUOTI: sono del titolare, al walkthrough.

---

## Sezione A — Esperimenti di rimozione (schede D1..D7)

### T-D1 — `recycle_worker`: la guardia sul worker in-process
**Guardia tolta**: `commander.py:3130-3131` (le due righe della `ValueError`
"is the in-process worker").
**Test caduti** (1):
- `tests/test_spa_move.py::test_the_in_process_worker_is_never_recycled`
  (`tests/test_spa_move.py:2455-2467`).

**Lo scenario esiste nel prodotto?** No. Il test costruisce lo scenario a mano:
finge il worker in-process (`commander.worker = SimpleNamespace(name=local)`,
`tests/test_spa_move.py:2462`) e poi **chiama `recycle_worker` direttamente**
sul nome locale (`tests/test_spa_move.py:2467`). In produzione l'unico
chiamante è `recycle_pass` (`commander.py:3021`), che passa l'esito di
`recycle_candidate()`; quel selettore salta già il worker in-process
(`commander.py:3001-3002`), e la prima metà dello stesso test lo verifica
(`assert commander.recycle_candidate() == "W:w-2"`,
`tests/test_spa_move.py:2465`).
**Natura del test**: metà cammino reale (il selettore salta), metà contratto
del metodo pubblico (il rifiuto diretto). Solo la seconda metà cade.
**Proposta di coppia**: se il titolare sceglie l'opzione D1 «un solo posto»,
la coppia da togliere è `commander.py:3130-3131` + le due righe
`tests/test_spa_move.py:2466-2467`, lasciando in piedi l'asserzione sul
selettore. Se invece si tiene la `ValueError` come contratto pubblico e si
toglie lo skip nel selettore, cade l'asserzione `recycle_candidate() == "W:w-2"`
e non queste due righe: **le due opzioni di D1 costano ciascuna metà di questo
test**, mai entrambe.
**Verdetto: —**

### T-D2 — `recycle_worker`: la guardia sullo stato non-`active`
**Guardia tolta**: `commander.py:3132-3133` (la `ValueError` "is {status}: not
recyclable").
**Test caduti**: **nessuno — la difesa è incementata.** 249 passati.

**Lo scenario esiste nel prodotto?** No, e ora è confermato da due lati: la
fase 2 ha mostrato che fra la scelta (`commander.py:3018`) e il controllo
(`commander.py:3132`) non c'è `await`, e la suite non contiene un solo test che
chiami `recycle_worker` su una riga non-`active`. Gli otto chiamanti di test
(`tests/test_spa_move.py:2184`, `2207`, `2233`, `2467`, `2503`, `2517`, `2543`,
`2677`) passano tutti o un worker `active` o il worker in-process.
**Proposta**: rimozione secca delle due righe — nessun test da toccare. È la
voce a costo zero fra le difese specie-1.
**Verdetto: —**

### T-D3 — `recycle_worker`: la guardia sul worker inesistente
**Guardia tolta**: `commander.py:3127-3129` sostituite da
`entry = self.worker_roster[name]`.
**Test caduti**: **nessuno — la difesa è incementata.** 249 passati.

**Lo scenario esiste nel prodotto?** No: il nome arriva dal roster e la
sepoltura di una riga avviene `TOMBSTONE_SECONDS` (3600s, `commander.py:363`)
dopo la morte. Nessun test chiama `recycle_worker` con un nome ignoto.
**Proposta di coppia**: la proposta D3 (tre righe → una, stesso errore rumoroso
`KeyError`) non ha alcun test da rimuovere insieme. Il messaggio dell'errore
cambia — da `"no such worker to recycle: 'X'"` a un `KeyError` nudo — e nessuna
asserzione lo legge.
**Verdetto: —**

### T-D4 — `warn_stalled_evacuation`: il timbro assente
**Guardia tolta**: il ramo `since is None` di `commander.py:3084`, trasformato
in `AssertionError` rumorosa (esperimento di raggiungibilità: se un test passa
di lì, l'esperimento lo fa esplodere).
**Test caduti**: **nessuno — il ramo non è mai percorso.** 249 passati.

**Lo scenario esiste nel prodotto?** No. Il metodo è chiamato solo su righe
`evacuating` (`commander.py:3036-3042`), e stato e timbro sono scritti in due
righe consecutive senza `await` (`commander.py:3153-3154`). L'unico test che
esercita il metodo per intero — `test_a_stalled_evacuation_is_reported`
(`tests/test_spa_move.py:2703-2715`) — **scrive il timbro esplicitamente**
(`row["evacuating_since"] = time.monotonic() - CONNECTION_MAX_AGE - 10`,
`tests/test_spa_move.py:2713`), quindi cementa il confronto temporale, non il
ramo `None`.
**Proposta di coppia**: nessun test da rimuovere. Restano le due opzioni della
scheda D4 — togliere `since is None or` (una riga `evacuating` senza timbro non
esiste) oppure renderlo errore rumoroso (che è ciò che l'esperimento ha
temporaneamente fatto, senza rompere nulla).
**Verdetto: —**

### T-D5 — `worker_time_to_limit`: il default `or []` sulla serie
**Guardia tolta**: `evaluator.py:318` → `list(series)[-1]["floor"]`.
**Test caduti**: **nessuno — il default è incementato.** 249 passati.

**Lo scenario esiste nel prodotto?** No, e nemmeno nei test: otto chiamanti di
`worker_time_to_limit` nella suite (`tests/test_spa_evaluator.py:472`, `479`,
`481`, `490`, `505`, `512`, `523`; `tests/test_spa_move.py:2357`) e nessuno
arriva alla riga 318 con una serie falsa — la velocità `None` li ferma prima
(`evaluator.py:315`). Il test del monitor che legge un `time_to_limit` senza
serie (`tests/test_spa_monitor.py:248-254`) si ferma allo stesso gate.
**Proposta**: rimozione secca di `or []` — nessun test da toccare.
**Verdetto: —**

### T-D6 — `install_in_custody`: il controllo di tipo sulla risposta
**Guardia tolta**: `commander.py:2591` → `if answer.get("joined"):`.
**Test caduti**: **nessuno — il ramo non-dict è incementato.** 249 passati.

**Lo scenario esiste nel prodotto?** No: il worker risponde sempre con un dict
(`worker.py:2350`). L'unico test che passa da `install_in_custody`
(`tests/test_spa_move.py:672`) riceve un dict vero.
**Proposta**: rimozione secca di `isinstance(answer, dict) and` — nessun test
da rimuovere. Una risposta di forma sbagliata alzerebbe un `AttributeError`
naturale, che è il rumore che la regola di casa chiede.
**Verdetto: —**

### T-D7 — `worker_floor_velocity`: velocità nulla sulla serie intera
**Guardia tolta**: `evaluator.py:292-293`, il `return None` sostituito da
`AssertionError` rumorosa.
**Test caduti** (1):
- `tests/test_spa_evaluator.py::test_floor_velocity_is_none_when_no_pair_is_separated_in_time`
  (`tests/test_spa_evaluator.py:515-523`).

**Lo scenario esiste nel prodotto?** Praticamente no, ed è esattamente il caso
che la scheda D7 consegna alla regola fondamentale (probabilità × esito). Il
test scrive **otto campioni con lo stesso identico `ts`**
(`tests/test_spa_evaluator.py:518-521`): `now = time.time()` letto una volta
sola e riusato nel ciclo. In produzione i campioni sono aggiunti uno per
finestra chiusa, con una `time.time()` per campione (`commander.py:1900`): otto
letture identiche di `time.time()` a distanza di una finestra l'una dall'altra.
**Natura del test**: è un test *della funzione*, non *dello scenario* — asserisce
il contratto «serie senza coppie separate nel tempo → `None`», che è
un'invariante matematica di `floor_slope`, non un evento del prodotto.
**Proposta di coppia**: se il titolare decide di rendere rumoroso il ramo, la
coppia da riscrivere è `evaluator.py:292-293` + questo test (che diventerebbe
un `pytest.raises`); se decide di tenerlo, la coppia resta com'è e la voce esce
dal ledger. **Non c'è una terza opzione «togli il ramo»**: senza il `return
None`, `max(velocity, accelerated)` a `evaluator.py:298` confronterebbe `None`
con un `float` e alzerebbe `TypeError` — un errore rumoroso ma nel posto
sbagliato, tre righe più in là della causa.
**Verdetto: —**

---

## Sezione B — Le guardie NECESSARIE (scheda D8): nessun esperimento

La scheda D8 di `zone_recycling_code.md` registra sei guardie **verificate
necessarie** con analisi dei chiamanti (una finestra di `await` reale fra la
lettura e l'uso, o un default davvero raggiungibile). Per decisione della fase 2
esse sono state escluse dagli esperimenti: toglierle non produce «quali test
cadono», produce una gara persa.

Nessuna di esse è stata toccata: `commander.py:3138`, `commander.py:3148-3152`,
`commander.py:3060-3061`, `commander.py:3069`, `commander.py:3064`,
`commander.py:2265-2266`, `commander.py:2967-2968`.

Una sola annotazione utile alla fase 5, letta e non sperimentata: la guardia
`commander.py:3177-3178` (`wait_worker_ready` che alza subito su una riga già
`dead`) — la premessa della necessità di `commander.py:3138` — **è cementata**
da `tests/test_spa_move.py::test_the_wait_aborts_at_once_on_a_replacement_already_dead`
(`tests/test_spa_move.py:2549-2558`), che ne misura anche il tempo (`< 1.0s`
contro i 30s di `READY_TIMEOUT`). Coppia sana: ramo raggiungibile, test che lo
raggiunge.

**Verdetto: —** (registrate come non-voci, se il titolare concorda)

---

## Sezione C — Igiene: la voce `LocalPool.settled` dell'issue #17

**Cosa dice l'issue**: «`LocalPool.settled` in `tests/test_spa_move.py`, helper
morto che legge la convenzione `None` abolita» — da localizzare, elencare chi lo
chiama, proporne la rimozione.

**Cosa c'è nell'albero** (verificato 2026-08-13, come già rilevato in fase 1):

1. **`LocalPool.settled` non esiste.** La classe `LocalPool`
   (`tests/test_spa_move.py:149-189`) ha quattro metodi — `__init__`, `start`,
   `add_worker`, `stop` — più la property `names`. Nessun `settled`.
2. **`settled_at` esiste ed è vivo** — funzione a livello di modulo, non metodo
   di `LocalPool` (`tests/test_spa_move.py:78-87`). Attende che la mappa nomini
   la destinazione e che nessun hold di quell'utente sia in piedi. **16
   chiamanti** nella suite: `tests/test_spa_move.py:546`, `748`, `768`, `783`,
   `816`, `835`, `848`, `869`, `915`, `975`, `1010`, `1047`, `1202`, `1281`,
   `1506`, `2773`. Non è codice morto: è il modo in cui l'intera sezione «la
   login non spedisce» asserisce dove un utente è FINITO, dato che il
   trasferimento è staccato (docstring del modulo,
   `tests/test_spa_move.py:23-28`).
3. **La convenzione `None` che `LocalPool` usa non è abolita.** L'unico `None`
   convenzionale della classe è `process=None` nella riga di roster di un worker
   in-process (`tests/test_spa_move.py:172`, documentato a
   `tests/test_spa_move.py:153-154`). La firma di `new_roster_row` lo ammette
   ancora esplicitamente — `process: subprocess.Popen[bytes] | None`
   (`commander.py:976`) — e il commander legge quel `None` in tre punti vivi:
   `commander.py:1089` (`process is None or process.poll() is not None`),
   `commander.py:1136` (`if entry["process"] is not None`), oltre alla lettura a
   `commander.py:863`. Stessa convenzione usata da `enroll`
   (`tests/test_spa_move.py:211`).

**Proposta**: **nessuna rimozione**. La voce dell'issue non ha un referente
nell'albero corrente: niente helper morto, niente convenzione abolita. Le due
letture possibili sono (a) la voce descriveva uno stato precedente del file, poi
già ripulito; (b) intendeva un altro simbolo. Se il titolare ricorda quale
simbolo aveva in mente, la scheda si riapre in un colpo solo; altrimenti va
nella sezione «Scartate» del registro di fase 5, con questa motivazione.
**Verdetto: —**

---

## Sezione D — Rassegna dei test difensivi (solo lettura, nessun esperimento)

Rassegna dei quattro file (`tests/test_spa_move.py` 121 test,
`tests/test_spa_commander.py` 60, `tests/test_spa_evaluator.py` 47,
`tests/test_spa_monitor.py` 17 — 245 funzioni, 249 casi raccolti) cercando test
che esercitino **solo** un ramo difensivo. La lettura basta: dove il test
asserisce un errore rumoroso su un input che il chiamante di produzione non
produce, non serve toglierlo per sapere cosa cade — cade solo lui.

### TS1 — I test di contratto sugli errori rumorosi del fold
`tests/test_spa_commander.py::test_discard_connection_edge_on_a_missing_set_raises`
(`tests/test_spa_commander.py:393-398`),
`::test_discard_page_edge_on_a_missing_set_raises`
(`tests/test_spa_commander.py:401-404`),
`::test_a_malformed_event_is_an_explicit_error`
(`tests/test_spa_commander.py:407-410`).
**Cosa asserisce ciascuno**: un `KeyError` su una struttura che il worker, in
produzione, forma sempre intera.
**Perché NON sono voci di ledger**: sono la faccia-test della regola di casa
stessa — «mai gestione silenziosa». Il ramo che cementano non è una difesa da
togliere, è l'assenza di difesa resa visibile: se domani qualcuno aggiungesse un
`.get(..., set())` di comodo, questi tre test cadrebbero, ed è precisamente il
loro mestiere. Registrati perché la fase 5 non li confonda con la specie 2.
**Verdetto: —**

### TS2 — I test «unknown worker / unknown user» degli osservatori
`tests/test_spa_evaluator.py::test_rates_none_for_an_unknown_worker`
(`tests/test_spa_evaluator.py:341`),
`::test_window_floor_of_a_silent_or_unknown_worker_is_none`
(`tests/test_spa_evaluator.py:416`),
`tests/test_spa_commander.py::test_worker_floors_reads_none_for_an_unknown_worker`
(`tests/test_spa_commander.py:926`),
`::test_an_unknown_user_consumed_nothing` (`tests/test_spa_commander.py:690`).
**Osservazione**: qui il ramo difeso è raggiungibile per davvero — sono
osservatori (evaluator, monitor, letture di consumo) interrogati da superfici
esterne (`metrics_view`, `monitor_state`) su nomi che possono essersi spenti fra
la fotografia e la lettura; `tests/test_spa_monitor.py:130`
(`test_monitor_state_skips_a_row_swept_mid_photo`) documenta esattamente quella
finestra.
**Proposta**: nessuna. Registrati come non-voci per chiudere la rassegna in
modo esplicito — non è vero che ogni ramo `None` sia una difesa da togliere.
**Verdetto: —**

### TS3 — Il solo test *della funzione* trovato nella zona del riciclo
`tests/test_spa_evaluator.py::test_floor_velocity_is_none_when_no_pair_is_separated_in_time`
— già trattato in T-D7, dove ha un esperimento a sostegno. Nominato qui per
completezza della rassegna: è l'unico test dei quattro file la cui premessa
(otto letture identiche di `time.time()`) non è costruibile dal prodotto.
**Verdetto: —** (rimanda a T-D7)

---

## Stato dell'albero

- Esperimenti eseguiti: 7 (T-D1..T-D7), ciascuno seguito dal ripristino del
  testo originale del file toccato.
- `pytest tests/ -q` a fine fase: **1569 passati, 2 saltati**.
- `git status --porcelain`: solo `.phased/`. Nessun file sotto `src/` o `tests/`
  modificato.

## Conteggio

**12 schede**, tutte con verdetto VUOTO:
7 esperimenti di rimozione (T-D1..T-D7) · 1 registrazione delle guardie
necessarie (sezione B) · 1 igiene (`LocalPool.settled`, sezione C) ·
3 di rassegna (TS1..TS3). A queste si aggiungono le due conclusioni trasversali
annotate sopra, che non sono schede e non hanno casella di verdetto (la coppia
sana di `wait_worker_ready`, l'assenza di cementazione per D2/D3/D4/D5/D6).

Esito quantitativo della lente: su sette difese specie-1, **cinque sono
completamente incementate** (D2, D3, D4, D5, D6 — nessun test cade) e due hanno
un test ciascuna (D1, D7), in entrambi i casi un test che costruisce a mano uno
scenario che il prodotto non produce.
