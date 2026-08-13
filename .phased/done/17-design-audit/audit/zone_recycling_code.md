# Zona 1 — Il codice del riciclo contro le autorità

**Workflow**: wf#17 design audit · **Fase**: 2 · **Data**: 2026-08-13
**Zona**: `recycling-code` — `src/genro_asgi/spa/commander.py` (3183 righe),
`src/genro_asgi/spa/evaluator.py` (360 righe), letti per intero.
**Autorità**: `audit/00_authorities.md` (fase 1).

**Stato**: schede da walkthrough. Ogni scheda porta almeno un `file:riga` e una
casella **Verdetto: —** che questa run non riempie mai. Nessuna riga di
sorgente è stata toccata.

Sigle: **F** fedeltà (lente 1) · **N** battesimo · **D** difesa per scenario
impossibile (specie 1) · **I** indirezione senza significato (specie 3) ·
**C** castello di pezze (specie 4) · **H** igiene.

---

## Lente 1 — Fedeltà alle autorità

### F1 — Il task `planner` con `decision_interval` contro il battito a tre forze
**Autorità dice** (BRIEF Q3a, brief:100-112): «Pool-shape decisions (rebalance,
recycling, compaction) leave the probe return and move to their own global
periodic task, interval per-group config, default 5 minutes […] Probes stay at
5s for HEALTH only». BRIEF §7 battezza `planner`, «the periodic task, sibling
of `caretaker`».

**Il codice fa**: le decisioni di forma del pool vivono ancora **dentro il
ritorno della sonda**. `probe_worker` archivia e chiama `pool_beat()` alla riga
successiva (`commander.py:969-970`); `pool_beat` (`commander.py:2633`) sceglie
la passata con un XOR sulle tre forze (`commander.py:2656-2664`), guardato dai
tre flag `compacting`/`rebalancing`/`recycling` (`commander.py:597-599`). La
docstring di `probe_worker` dichiara esplicitamente il contrario del BRIEF: «the
probe return IS the pool's heartbeat» (`commander.py:933`), che è la decisione
wf#5 f8 che il BRIEF ha **superata**. Nessun task periodico esiste: `planner` e
`decision_interval` hanno zero occorrenze in `src/` e in `tests/` (verificato
2026-08-13).

**Delta**: **assente** — il BRIEF ha superato wf#5 f8, il codice ha implementato
wf#5 f8.

**Opzioni**: (a) implementare il `planner` come task periodico e ridurre la
sonda a sola salute; (b) registrare la revisione al contrario (il battito sulla
sonda resta, il BRIEF Q3a viene emendato a verbale).

**Verdetto: —**

### F2 — Il modello PLAN (una lettura → redistribuzione → sostituzioni dal peggiore → compattazione)
**Autorità dice** (BRIEF Q3b, brief:114-136): «the commander reads the WHOLE
pool once […] and builds an ordered PLAN of steps from that single reading, then
executes it sequentially. The plan as a whole is the one operation in flight; a
tick landing mid-plan does nothing. Ratified step order: rebalance → replacements
(worst first, possibly several, sequential) → compaction». E: «the
`compacting`/`rebalancing` flags collapse into the single plan-in-flight state».

**Il codice fa**: nessun oggetto piano esiste. `pool_beat`
(`commander.py:2656-2664`) sceglie **una sola** forza per battito, in XOR, e
ogni forza rilegge il pool da sé: `rebalance_pass` rilegge `rebalance_excess()`
all'inizio (`commander.py:2748`), `recycle_pass` rilegge `recycle_candidate()`
(`commander.py:3018`), `compact_pass` rilegge `active_workers` e il libro
mastro a ogni giro del suo `while` (`commander.py:2904-2910`). I tre flag NON
sono collassati: sono tre attributi distinti (`commander.py:597-599`), letti
insieme una volta sola (`commander.py:2656`) — che è il «never together» del
BRIEF, ma ottenuto con tre flag invece che con uno stato di piano-in-volo.
La sostituzione è **una per passata** e non «possibly several»:
`recycle_pass` prende «the single worst candidate and ends»
(`commander.py:3011-3021`), e `recycle_candidate` rifiuta di scegliere se
un'evacuazione è già aperta (`commander.py:2994-2995`).

**Delta**: **derivato** (drifted) — l'ordine di precedenza esiste ed è quello
del BRIEF (eccesso → perdita → slack, `commander.py:2636-2642`), ma la
meccanica è la XOR per battito che il BRIEF ha superato, non il piano ordinato
costruito da una lettura sola.

**Opzioni**: (a) costruire il piano (una lettura, lista di passi, uno stato
`plan-in-flight` che sostituisce i tre flag); (b) emendare il BRIEF Q3b
registrando che la XOR con precedenza è la meccanica scelta, e togliere dal
BRIEF la frase sui flag collassati.

**Verdetto: —**

### F3 — `designated_reception` per l'accoglienza condannata
**Autorità dice** (BRIEF Q4-bis, brief:151-166): «when the plan condemns THE
RECEPTION, a fresh worker is spawned and the reception ROLE is assigned to it —
a declared revision of the wf#5 "positional, no flag and no election" decision
(a designation pointer on the commander, positional fallback when the designated
one dies)». BRIEF §7 battezza `designated_reception` (pointer, None = regola
posizionale) e `condemned_workers`.

**Il codice fa**: l'accoglienza è **rimasta posizionale**. `reception`
(`commander.py:629-636`) è `active_workers[0]`, con la docstring che cita la
decisione wf#5 superata: «Positional, like the legacy reception: no flag and no
election». Nessun puntatore di designazione esiste: `designated_reception` e
`condemned_workers` hanno zero occorrenze in `src/` e `tests/`.
Il meccanismo che **di fatto** sostituisce l'accoglienza è un effetto
collaterale del flag di evacuazione: `recycle_worker` mette lo stato a
`evacuating` (`commander.py:3153`), che toglie il worker da `active_workers`
(`commander.py:613-617`) e quindi dall'accoglienza posizionale — la docstring lo
dichiara (`commander.py:3104-3106`). Il worker fresco è già stato registrato
prima del flag (`commander.py:3134-3136`), quindi diventa l'ultimo attivo, non
il primo: la nuova accoglienza è il **secondo worker più vecchio ancora attivo**,
non il rimpiazzo fresco che il BRIEF designa.

**Delta**: **assente** come simbolo, **divergente** come comportamento (il ruolo
si sposta, ma su un worker già esistente invece che sul fresco).

**Opzioni**: (a) implementare il puntatore `designated_reception` con fallback
posizionale, assegnandolo al rimpiazzo; (b) registrare che lo spostamento
posizionale è sufficiente e emendare Q4-bis.

**Nota collegata** (NOTES notes:75, deferita dal titolare): «GUESTS ARE
RELOCATED TOO during an evacuation […] their forced destination is the NEW
reception». Oggi gli ospiti non sono rilocati affatto: `rebalance_weights`
dichiara che un ospite «is on no map and never moves»
(`commander.py:2801-2805`), e l'evacuazione lavora su `drain_order`, che legge
la riga del roster (`commander.py:2953-2954`) — le mezze righe degli ospiti ci
sono, ma `evacuation_pass` salta chi non è sulla mappa
(`commander.py:3062-3063`). Resta PENDING come dicono le NOTES.

**Verdetto: —**

### F4 — Spawn a libro mastro (`capacity_headroom`)
**Autorità dice** (BRIEF Q4, brief:138-150): «at plan build,
`capacity_headroom()` says whether the pool can absorb the sick worker's users —
if not, `scale(target + 1)` FIRST […]; if the room is there, no new process at
all». Contro-decisione (NOTES notes:11-13): «THE SICK WORKER IS FLAGGED ONLY
AFTER ITS SUCCESSOR REGISTERED».

**Il codice fa**: il riciclo **spawna sempre**, senza consultare il libro
mastro. `recycle_worker` chiama `spawn_worker()` incondizionatamente
(`commander.py:3134`) e attende il rimpiazzo (`commander.py:3136`); il flag
arriva dopo (`commander.py:3153`) — la contro-decisione delle NOTES è
implementata alla lettera, e la docstring la cita in maiuscolo
(`commander.py:3111-3113`). `capacity_headroom` (`commander.py:2872`) esiste ma
ha **un solo lettore**, la compattazione (`commander.py:2908`): il riciclo non
lo legge mai. Il TARGET non viene toccato dal riciclo — la docstring lo
dichiara, «the replacement covers the flagged source, one for one»
(`commander.py:3107-3109`) — quindi il pool si allarga di fatto di un worker
per la durata dell'evacuazione, senza passare da `scale`.

**Delta**: **divergente** — le due autorità non dicono la stessa cosa (fase 1,
F4) e il codice ha seguito le NOTES. Il ramo «se lo spazio c'è, nessun processo
nuovo» del BRIEF non esiste.

**Opzioni**: (a) aggiungere il gate del libro mastro prima dello spawn (e
decidere cosa fa il riciclo quando lo spazio c'è: evacuare senza rimpiazzo);
(b) ratificare le NOTES come autorità prevalente ed emendare Q4.

**Verdetto: —**

### F5 — `floor_series_depth` 48 vs 72; minimo di fit 3 vs 6
**Autorità dice** (BRIEF Q6, brief:208-223): «Series depth K — default 48 points
(one per 5-min window ≈ 4 hours of evidence)» e «Minimum 3 points before judging
= MODULE CONSTANT, not a kwarg». BRIEF Q2 (brief:97-98): «proposal K_min = 3;
below it T = ∞». NOTES notes:102-103 registra lo scarto già noto.

**Il codice fa**: `FLOOR_SERIES_DEPTH = 72` (`commander.py:334`), con la
docstring che motiva il 72 con una finestra di prova diversa da quella del
BRIEF: «72 of them span ~6 hours, the horizon a leak has to show itself over»
(`commander.py:332-334`) — il BRIEF diceva 4 ore. È kwarg per gruppo, come
chiesto (`commander.py:464`, letto a `commander.py:530`, usato come `maxlen` a
`commander.py:1004`). Il minimo di fit è `_FLOOR_FIT_MINIMUM = 6`
(`evaluator.py:91`), costante di modulo **privata** e non esportata
(`evaluator.py:81` elenca solo `COMPONENT_NAMES`, `SMOOTHING_ROWS`,
`OccupancyEvaluator`); letta a `evaluator.py:288` e `evaluator.py:295`, citata
nelle docstring come «six samples» (`evaluator.py:285`, `evaluator.py:307`).
Le altre due kwarg di Q6 ci sono con i valori del BRIEF:
`recycle_horizon_hours=12.0` (`commander.py:395`, `commander.py:465`) e il
tick — che però non esiste come tick (vedi F1).

**Delta**: **divergente sui valori** (72 vs 48, 6 vs 3), **conforme sulla
forma** (depth = kwarg, minimo = costante di modulo). Aggiunta: il BRIEF non
chiede che la costante sia privata.

**Opzioni**: (a) allineare ai valori del BRIEF (48 e 3); (b) ratificare 72 e 6
emendando Q6 e Q2 con la ragione dichiarata nelle docstring (finestra di prova
a 6 ore, robustezza del fit); (c) mista: allineare il default della serie,
tenere 6 come minimo statistico. La privatezza di `_FLOOR_FIT_MINIMUM` è una
sotto-domanda: pubblicarla in `__all__` la rende leggibile ai test e alla
configurazione futura.

**Verdetto: —**

### F6 — I nomi coniati durante la run e mai ratificati esplicitamente
**Autorità dice** (BRIEF §7, brief:260-261): il mandato era «reasonable names
for a reader who knows nothing». NOTES notes:81-84 e notes:109-114 elencano i
simboli coniati **da ratificare**; NOTES notes:127-128: «names ledger
unanswered = names stand».

**Il codice fa**: tutti e dieci i nomi esistono e sono in uso (schede N1-N10).
Tre nomi del pannello di finalize (NOTES notes:169-171) hanno esito diverso:
`RECYCLE_RETRY_SECONDS` esiste (`commander.py:403`) ma **non è esportata** —
`__all__` (`commander.py:304-321`) elenca `RECYCLE_HORIZON_HOURS` e non lei,
mentre i test la importano comunque (`tests/test_spa_move.py:58`);
`abandon_recycle` e il campo roster `recycle_failed_at` hanno **zero
occorrenze** in `src/` e `tests/` — il concetto è arrivato al codice come
attributo del commander `regeneration_failed_at` (`commander.py:596`), non come
campo di riga.

**Delta**: **conforme** ai dieci nomi, **divergente** sui tre del pannello (uno
non esportato, due mai nati con quel nome).

**Opzioni**: (a) battesimo al walkthrough voce per voce (schede N1-N10); (b)
decidere se `RECYCLE_RETRY_SECONDS` entra in `__all__` — oggi è una costante
pubblica di fatto, importata dai test, ma non dichiarata.

**Verdetto: —**

---

## Sezione di battesimo — i dieci nomi

Per ciascuno: dove è definito, cosa fa **davvero** in una frase, e 2-3
candidati (o «tenere» con la ragione). Il battesimo è del titolare.

### N1 — `floor_slope(samples)` · `evaluator.py:258`
**Semantica**: la pendenza Theil-Sen (mediana di tutte le pendenze a coppie) di
una lista di campioni `{ts, floor}`, in **byte all'ora**; `None` quando nessuna
coppia è separata nel tempo. È una funzione pura sui campioni passati, non
legge nessun worker.
**Chi la chiama**: `worker_floor_velocity` due volte (`evaluator.py:291` sulla
serie intera, `evaluator.py:296` sulla metà recente) e un test
(`tests/test_spa_evaluator.py:491`).
**Candidati**: `floor_slope` (tenere: dice soggetto + grandezza, ma non dice
l'unità né che è robusta) · `floor_climb_rate` · `floor_trend_per_hour`.
**Nota**: il BRIEF §7 battezza solo `worker_floor_velocity` (brief:266); questo
è il gradino sotto, e la parola `slope` è l'unica del gruppo che non porta
l'unità.
**Verdetto: —**

### N2 — `wait_worker_ready(name)` · `commander.py:3159`
**Semantica**: attende che **quel** worker passi ad `active`, con polling a 20ms
e `READY_TIMEOUT`; alza `TimeoutError` subito se la riga è già `dead`.
**Chi la chiama**: solo `recycle_worker` (`commander.py:3136`) e un test
(`tests/test_spa_move.py:2557`).
**Distinzione dal gemello**: `wait_workers_ready(count)` (`commander.py:795`)
conta i worker; questo aspetta **il proprio** rimpiazzo. La distinzione singolare/
plurale è l'unica cosa che separa i due nomi, e si legge male ad alta voce.
**Candidati**: `wait_for_worker` · `await_worker_registered` · tenere
`wait_worker_ready` accettando la vicinanza al plurale.
**Verdetto: —**

### N3 — `drain_order(worker)` · `commander.py:2947`
**Semantica**: gli utenti della riga del worker ordinati in due scaglioni
alfabetici: prima chi non ha chiamate in `pending`, poi gli altri.
**Chi la chiama**: `drain_worker` (`commander.py:2936`) e `evacuation_pass`
(`commander.py:3059`) — quindi non è più solo del drenaggio.
**Candidati**: `drain_order` (tenere: il nome dice «l'ordine di un drenaggio»
e l'evacuazione è un drenaggio) · `departure_order` · `idle_first_users`.
**Verdetto: —**

### N4 — `advance_evacuations()` · `commander.py:3025`
**Semantica**: **non muove nessuno**. Scorre le righe `evacuating`, ritira
quelle rimaste vuote, e per le altre chiama il report di stallo. È
contabilità sincrona, per battito.
**Chi la chiama**: solo `pool_beat` (`commander.py:2658`) e un test
(`tests/test_spa_move.py:2714`).
**Problema di nome**: `advance` promette movimento — «fai avanzare le
evacuazioni» — mentre il metodo chiude i libri di quelle già finite. È la
trappola dell'omonimia già vista in wf#4.
**Candidati**: `close_finished_evacuations` · `settle_evacuations` ·
`review_evacuations`.
**Verdetto: —**

### N5 — `evacuation_pass(worker)` · `commander.py:3044`
**Semantica**: la passata di **apertura**: muove ora solo gli utenti senza
chiamate pendenti, salta i mid-call senza attenderli, e ritira il worker se
resta vuoto alla fine.
**Chi la chiama**: solo `recycle_worker` (`commander.py:3156`).
**Candidati**: `evacuation_pass` (tenere: «pass» è il vocabolario già in uso —
`rebalance_pass`, `compact_pass`, `recycle_pass`) · `evacuate_the_idle` ·
`open_evacuation`.
**Nota**: gli altri `*_pass` sono passate **di forza**, prese da `pool_beat` e
guardate da un flag; questa è dentro `recycle_worker` e non ha flag proprio —
la simmetria del nome promette una simmetria di meccanica che non c'è.
**Verdetto: —**

### N6 — `evacuate_user(user, worker)` · `commander.py:2243`
**Semantica**: porta via **un** utente appena liberatosi da un worker in
evacuazione; se non riesce, lo **dimentica dalla superficie** (`remove_user`,
`commander.py:2273`) con un ERROR, così la prossima chiamata è un KeyError
rumoroso e il client rifà login.
**Chi la chiama**: solo `close_request` (`commander.py:2241`), come task
distaccato.
**Candidati**: `evacuate_user` (tenere) · `carry_user_out` · `move_freed_user`.
**Nota**: è il nome più carico del gruppo — «evacuare un utente» suggerisce
che l'utente esce dal sistema, mentre esce dal **worker**.
**Verdetto: —**

### N7 — `warn_stalled_evacuation(worker)` · `commander.py:3073`
**Semantica**: emette un WARNING quando un'evacuazione è aperta da più di
`CONNECTION_MAX_AGE` e non è ancora finita, con throttle a
`RECYCLE_RETRY_SECONDS` per worker.
**Chi la chiama**: solo `advance_evacuations` (`commander.py:3042`).
**Candidati**: `warn_stalled_evacuation` (tenere) · `report_stalled_evacuation`
(«report» è la parola delle NOTES, notes:26-29, e prefigura il canale
`_server/<nome>` che sostituirà il log) · `flag_evacuation_stall`.
**Verdetto: —**

### N8 — `regeneration_failed_at` · `commander.py:596`
**Semantica**: il momento monotonico in cui un rimpiazzo non è riuscito a
registrarsi. Finché è più giovane di `RECYCLE_RETRY_SECONDS` fa due cose:
`worker_for` rifiuta i **nuovi** ingressi con 503 (`commander.py:2118-2120`) e
`recycle_candidate` non sceglie nessuno (`commander.py:2996-2998`). Si azzera al
primo REGISTER riuscito (`commander.py:1132-1134`).
**Candidati**: `regeneration_failed_at` (tenere: dice soggetto + evento +
istante) · `spawn_failed_at` · `pool_sterile_since`.
**Nota**: il pannello di finalize aveva coniato `recycle_failed_at` come campo
**di riga** (NOTES notes:169-171); il codice ha fatto un attributo di
commander, che è la cosa giusta (la condizione è del pool, non di un worker) —
va ratificata la differenza, non solo il nome.
**Verdetto: —**

### N9 — roster `evacuating_since` · `commander.py:1006` (documentato a 989-992)
**Semantica**: istante monotonico in cui il riciclo ha messo la riga in
`evacuating` (scritto a `commander.py:3154`); serve solo a distinguere
un'evacuazione stallata (`commander.py:3083-3084`).
**Candidati**: `evacuating_since` (tenere) · `evacuation_opened_at` ·
`condemned_at` (allinea al vocabolario del BRIEF, `condemned_workers` —
brief:269).
**Verdetto: —**

### N10 — roster `evacuation_warned_at` · `commander.py:1007` (documentato a 992)
**Semantica**: istante dell'ultimo WARNING di stallo, per il throttle
(`commander.py:3086-3089`).
**Candidati**: `evacuation_warned_at` (tenere) · `stall_reported_at` ·
`last_stall_warning`.
**Verdetto: —**

---

## Lente 2, specie 1 — Difese per scenari impossibili

Regola di casa: **rimuovere, o sostituire con un errore rumoroso — mai gestione
silenziosa**. Ogni scheda nomina la guardia con precisione perché la fase 3
possa toglierla e vedere quali test cadono.

### D1 — `recycle_worker`: la guardia sul worker in-process
**Guardia**: `commander.py:3130-3131` — `if self.worker is not None and name ==
self.worker.name: raise ValueError(...)`.
**Chi può raggiungerla**: nessun chiamante di produzione. L'unico chiamante è
`recycle_pass` (`commander.py:3021`), che passa l'esito di
`recycle_candidate()`, il quale salta già il worker in-process
(`commander.py:3001-3002`). Cementata da un test che chiama il metodo
direttamente (`tests/test_spa_move.py:2467`).
**Proposta**: è già un errore rumoroso, quindi la regola di casa è
soddisfatta; la domanda è se la coppia di controlli (uno nel selettore, uno nel
metodo) valga due posti da mantenere. Opzione: tenere la `ValueError` come
contratto pubblico del metodo e togliere lo skip nel selettore (un candidato
non riciclabile non arriva mai a essere scelto perché il metodo lo rifiuta) —
oppure il contrario.
**Verdetto: —**

### D2 — `recycle_worker`: la guardia sullo stato non-`active`
**Guardia**: `commander.py:3132-3133` — `if entry["status"] != "active": raise
ValueError(...)`.
**Chi può raggiungerla**: nessun chiamante di produzione. `recycle_candidate`
itera su `active_workers` (`commander.py:3000`) e non c'è punto di attesa fra la
scelta (`commander.py:3018`) e il controllo (`commander.py:3132`): sono nella
stessa coroutine senza `await`. Raggiungibile solo per chiamata diretta.
**Proposta**: come D1 — errore rumoroso già conforme; da decidere se il
contratto del metodo pubblico giustifica il controllo.
**Verdetto: —**

### D3 — `recycle_worker`: la guardia sul worker inesistente
**Guardia**: `commander.py:3127-3129` — `entry = self.worker_roster.get(name)`
seguita da `if entry is None: raise KeyError(...)`.
**Chi può raggiungerla**: nessuno in produzione (il nome viene dal roster). La
sepoltura di una riga avviene `TOMBSTONE_SECONDS` (3600s,
`commander.py:363`) dopo la morte, quindi la riga non può sparire fra scelta e
uso.
**Proposta**: sostituire `.get(name)` + `raise KeyError` con l'indicizzazione
diretta `self.worker_roster[name]` — il `KeyError` è lo stesso errore rumoroso,
scritto in una riga invece di tre. Lo stesso pattern è già usato altrove
(`commander.py:3176`, `commander.py:2953`).
**Verdetto: —**

### D4 — `warn_stalled_evacuation`: il timbro assente
**Guardia**: `commander.py:3084` — `if since is None or now - since <
CONNECTION_MAX_AGE: return`, dove `since = entry["evacuating_since"]`.
**Chi può raggiungerla**: il ramo `since is None` nessuno. Il metodo è chiamato
solo su righe con `status == "evacuating"` (`commander.py:3036-3042`), e lo stato
e il timbro sono scritti nelle due righe consecutive `commander.py:3153-3154`,
senza `await` fra loro. Non esiste altro scrittore di `evacuating`.
**Proposta**: togliere il ramo `since is None`, lasciando il solo confronto
temporale; se lo si vuole mantenere come contratto, farlo diventare un errore
rumoroso (una riga `evacuating` senza timbro è un difetto, non un caso).
**Verdetto: —**

### D5 — `worker_time_to_limit`: il default `or []` sulla serie
**Guardia**: `evaluator.py:318` — `list(series or [])[-1]["floor"]`.
**Chi può raggiungerla**: nessuno. Tre righe sopra
(`evaluator.py:314-316`) la velocità è già `not None`, e la velocità è `None`
per costruzione quando la serie è vuota o più corta di `_FLOOR_FIT_MINIMUM`
(`evaluator.py:288`). Inoltre il default non difende nulla: su lista vuota
`[-1]` alza `IndexError` comunque.
**Proposta**: togliere `or []` — `list(series)[-1]["floor"]`.
**Verdetto: —**

### D6 — `install_in_custody`: il controllo di tipo sulla risposta
**Guardia**: `commander.py:2591` — `if isinstance(answer, dict) and
answer.get("joined"):`.
**Chi può raggiungerla**: `answer` viene solo da `hand_user_to`
(`commander.py:2580`), che restituisce `unwrap_reply` di `/op/add_user`; il
worker risponde sempre con un dict — `return {**self.wire_entry(entry),
"joined": joined}` (`worker.py:2350`). Il ramo non-dict è irraggiungibile.
**Proposta**: `if answer.get("joined"):` — e se si vuole il rumore, un
`KeyError` naturale su una risposta di forma sbagliata.
**Verdetto: —**

### D7 — `worker_floor_velocity`: il ritorno su velocità nulla della serie intera
**Guardia**: `evaluator.py:292-293` — `if velocity is None: return None`.
**Chi può raggiungerla**: solo una serie di ≥6 campioni in cui **tutti** i `ts`
sono identici (`floor_slope` torna `None` solo se nessuna coppia è separata nel
tempo, `evaluator.py:272-274`). I campioni sono aggiunti uno per finestra
chiusa, con `time.time()` (`commander.py:1900`): probabilità infima.
**Proposta**: caso da valutare con la regola fondamentale (probabilità × esito):
oggi finisce in «nessuna perdita misurabile», che è silenzioso ma innocuo.
Tenere o rendere rumoroso è una scelta del titolare — non un difetto.
**Verdetto: —**

### D8 — Guardie verificate NECESSARIE (nessuna proposta di rimozione)
Registrate perché la fase 3 non le tocchi per simmetria con le precedenti:

- `commander.py:3138` — `if self.worker_roster[replacement]["status"] != "dead":
  self.retire_worker(replacement)`. **Necessaria**: `wait_worker_ready` alza
  `TimeoutError` anche quando la riga è già `dead` (`commander.py:3177-3178`), e
  `retire_worker` su una riga `dead` la rimetterebbe a `draining` con un SIGTERM
  (`commander.py:1083-1084`), resuscitando una lapide.
- `commander.py:3148-3152` — `if entry["status"] != "active"` **dopo**
  l'attesa del rimpiazzo. **Necessaria**: fra `commander.py:3136` e
  `commander.py:3148` c'è un `await`, e `channel_lost` può timbrare la riga
  `dead` in quella finestra (`commander.py:1157-1159`).
- `commander.py:3060-3061` e `commander.py:3069` — i due ricontrolli di
  `status == "evacuating"` dentro e alla fine di `evacuation_pass`.
  **Necessari**: `move_user` è un `await` (`commander.py:3067`).
- `commander.py:3064` — `entry["users"].get(user, {}).get("pending")`. **Il
  default `{}` è raggiungibile**: `drain_order` fotografa i nomi
  (`commander.py:3059`) e un `await move_user` dopo può far sparire la mezza
  riga.
- `commander.py:2265-2266` — `if self.user_worker_map.get(user) != worker:
  return` in `evacuate_user`. **Raggiungibile**: `move_user` torna `False` anche
  quando l'utente è stato spazzato mid-move (`commander.py:2477-2499`).
- `commander.py:2967-2968` — il fallback `admitting or candidates` in
  `pick_compaction_target`. **Raggiungibile**: tutti i candidati oltre il gate.

**Verdetto: —** (registrate come non-voci, se il titolare concorda)

---

## Lente 2, specie 3 — Indirezione senza significato

### I1 — I tre `trigger_*` gemelli
**Cosa sono**: `trigger_rebalance` (`commander.py:2687-2696`),
`trigger_recycle` (`commander.py:2698-2707`), `trigger_compaction`
(`commander.py:2709-2718`): tre metodi di 9 righe identici a meno del nome del
flag e della coroutine — guardia sul proprio flag, alza il flag, lancia la
passata, riabbassa il flag se il lancio esplode.
**Chi li chiama**: solo `pool_beat` (`commander.py:2660`, `2662`, `2664`), che
ha **già** letto tutti e tre i flag due righe sopra (`commander.py:2656`) e
ritorna se uno è alzato. La guardia interna di ciascuno è quindi morta sul
percorso di produzione; è viva solo per i test che li chiamano due volte di
seguito (`tests/test_spa_move.py:1830-1831`, `1865-1866`).
**Scritto oggi dalla storia ratificata**: la storia dice «una forza per volta,
un flag». Con lo stato di piano-in-volo del BRIEF (F2) i tre metodi
collasserebbero in uno: `spawn_pool_pass` più l'assegnazione dello stato. Senza
arrivare al piano, un solo metodo parametrico — «alza questo flag, lancia questa
passata» — sono ~8 righe invece di 27.
**Proposta**: unificare i tre in un metodo che riceve nome del flag e coroutine,
oppure eliminarli e alzare il flag dentro `pool_beat` (i tre `*_pass` già lo
riabbassano nel proprio `finally`: `commander.py:2769`, `3023`, `2921`).
**Verdetto: —**

### I2 — Il ritiro-a-vuoto scritto in due posti
**Cosa sono**: `advance_evacuations` (`commander.py:3038-3041`) e la coda di
`evacuation_pass` (`commander.py:3069-3071`) fanno la stessa cosa con la stessa
riga di log — «Evacuation of %s complete: retired» — su condizioni scritte in
modo diverso (`not entry["users"]` contro `not self.users_on(worker)`, che è la
stessa lettura passando da un set: `commander.py:1793-1795`).
**Chi le raggiunge**: la prima ogni battito, la seconda solo alla fine della
passata di apertura.
**Proposta**: un solo `retire_if_empty(worker)` chiamato dai due punti, oppure
togliere il ritiro dalla passata di apertura e lasciarlo al battito (che passa
comunque subito dopo) — la seconda scelta accorcia, ma ritarda il ritiro di un
intervallo di sonda.
**Verdetto: —**

### I3 — `evacuation_pass` e `drain_worker`, cicli gemelli
**Cosa sono**: `drain_worker` (`commander.py:2923-2945`) e `evacuation_pass`
(`commander.py:3044-3071`) iterano entrambi `drain_order(worker)`, saltano chi
non è più sulla mappa, chiedono `pick_compaction_target` e chiamano `move_user`.
Le differenze reali sono tre: l'evacuazione **salta** chi ha chiamate pendenti
invece di attenderne il quiesce (`commander.py:3064-3065`), ricontrolla lo stato
a ogni giro (`commander.py:3060-3061`), e ritira il worker in coda; il drenaggio
invece torna un `bool` che il chiamante usa per decidere il ritiro
(`commander.py:2911-2916`).
**Proposta**: un solo ciclo con una politica sugli occupati («attendi» /
«salta»), o la constatazione che le tre differenze sono concetti distinti e i
due metodi restano separati. È la domanda «quante righe scritte oggi»: la
storia ratificata (BRIEF Q5, brief:186-193) descrive **una** procedura di
svuotamento con due tempi, non due procedure.
**Verdetto: —**

### I4 — `worker_threshold`
**Cosa è**: `commander.py:2666-2672`, 7 righe di cui 5 di docstring, che
tornano `reception_threshold` se il worker è l'accoglienza, altrimenti `1.0`.
**Chi lo chiama**: `rebalance_excess` (`commander.py:2682`) e
`pick_rebalance_target` (`commander.py:2785`).
**Proposta**: **tenere** — due chiamanti e un concetto vero (l'asimmetria
dell'accoglienza), che senza il metodo andrebbe ripetuto in entrambi.
Registrato per completezza della caccia, non come voce da snellire.
**Verdetto: —**

### I5 — I due `wait_*_ready`
**Cosa sono**: `wait_workers_ready(count)` (`commander.py:795-808`) e
`wait_worker_ready(name)` (`commander.py:3159-3183`): due attese a polling con
lo stesso schema (deadline sul loop, `sleep(0.02)`, `TimeoutError`), su predicati
diversi.
**Proposta**: il concetto è distinto (N2) e va tenuto; il corpo è duplicato e
potrebbe passare da un solo `wait_until(predicate, timeout)`. Dipende da quanto
il titolare vuole di infrastruttura generica in questo modulo.
**Verdetto: —**

---

## Lente 2, specie 4 — Castelli di pezze

Domanda per ciascuno: **scritto oggi dalla storia ratificata, quante righe
sarebbe?**

### C1 — L'evacuazione, tre porte per un solo comportamento
**Le pezze**: il comportamento «svuota il worker condannato» è entrato dal
codice in tre punti indipendenti, ognuno con la sua storia:
1. la passata di apertura, dentro `recycle_worker` (`commander.py:3156` →
   `evacuation_pass`, 28 righe);
2. l'auto-consegna al chiudersi di una chiamata (`close_request`
   `commander.py:2240-2241` → `evacuate_user`, 32 righe);
3. la contabilità per battito (`pool_beat` `commander.py:2658` →
   `advance_evacuations` 19 righe → `warn_stalled_evacuation` 23 righe).
A questi si aggiungono i due campi di riga (`commander.py:1006-1007`) e il
paragrafo di docstring di riga che li spiega (`commander.py:989-992`).
**Cosa dice la storia ratificata** (BRIEF Q5, brief:186-193): gli utenti con
`pending` vuoto si spostano subito e vanno PRIMI; per gli altri, «in the
existing `close_request` finally, one added check — pending emptied AND worker
condemned → trigger that user's move». Due tempi, non tre porte: il terzo
(contabilità + report) è cresciuto dal panel di wf#8, non dal BRIEF.
**Stima a riscrittura**: i due tempi del BRIEF sono ~35 righe in tutto
(passata sugli idle + il controllo aggiunto in `close_request` + il ritiro a
vuoto). Oggi il totale del gruppo è ~102 righe di corpo più i campi. Il delta
sta quasi tutto nel report di stallo (D4, N7) e nella duplicazione I2/I3.
**Proposta**: decidere se il report di stallo è una voce di prodotto (allora
resta, e va sul canale `_server/<nome>` quando esisterà, NOTES notes:79) o una
pezza da panel; poi unificare I2 e I3.
**Verdetto: —**

### C2 — La serie dei pavimenti e la correzione di accelerazione
**Le pezze**: la serie vive su tre pezzi che non vengono da una sola decisione:
il contatore `floor_readings` che campiona una finestra su `METRICS_WINDOW`
(`commander.py:1895-1900`), la profondità 72 contro il 48 del BRIEF
(`commander.py:334`, vedi F5), il minimo di fit 6 contro 3
(`evaluator.py:91`), e — **non chiesta da nessuna autorità** — la correzione di
accelerazione in `worker_floor_velocity` (`evaluator.py:294-298`): lo stesso fit
sulla metà recente, e vince il maggiore.
**Chi ha postulato la correzione**: nessuna delle tre autorità la nomina. Il
BRIEF §7 battezza `worker_floor_velocity` come «bytes/hour, Theil–Sen»
(brief:266), senza seconda passata; la ragione è solo nella docstring
(`evaluator.py:280-284`), che per la regola ratificata («design e review partono
dalle decisioni ratificate») non è un record di decisione.
**Stima a riscrittura**: la storia ratificata è «Theil-Sen sulla serie, T =
(limite − ultimo pavimento) / velocità, ∞ se piatta o in discesa»: ~15 righe
totali fra `floor_slope` e i due lettori. Oggi sono ~45 righe
(`evaluator.py:258-319`) più la costante privata.
**Proposta**: portare la correzione di accelerazione al walkthrough come voce a
sé — o si ratifica (ed entra nel BRIEF) o si toglie; e nello stesso passaggio
decidere i due valori di F5.
**Verdetto: —**

### C3 — La rigenerazione fallita e la costante che fa tre lavori
**Le pezze**: `RECYCLE_RETRY_SECONDS` (300s, dichiarata **PROVISIONAL** a
`commander.py:403`) governa tre cose diverse con lo stesso numero:
1. la finestra del 503 ai nuovi ingressi (`commander.py:2119`);
2. il gate che impedisce di ri-scegliere un candidato al riciclo
   (`commander.py:2997`);
3. il throttle del WARNING di stallo dell'evacuazione (`commander.py:3087`) —
   che non ha nulla a che vedere con la rigenerazione.
Il terzo uso è quello che tradisce l'accrescimento: la docstring lo dichiara
(«Throttled to one report per `RECYCLE_RETRY_SECONDS`», `commander.py:3076`) ma
il nome della costante parla di riprovare un riciclo, non di quante volte
loggare.
Sul flanco, la soglia di stallo è `CONNECTION_MAX_AGE` (`commander.py:3084`),
importata da `worker.py` (`commander.py:292`): una terza costante di un altro
modulo usata come orologio dell'evacuazione.
**Chi ha postulato**: nessuna autorità nomina `RECYCLE_RETRY_SECONDS`; è del
pannello di finalize di wf#8 (NOTES notes:169-171), esplicitamente
**PROVISIONAL**.
**Stima a riscrittura**: la storia ratificata (NOTES notes:16-21) chiede: 503 ai
nuovi ingressi, residenti serviti, azzeramento al primo REGISTER, sonde pacate.
Sono l'attributo, il timbro, il controllo in `worker_for` e il gate in
`recycle_candidate` — ~12 righe, con **una** costante. Il throttle del report è
un secondo concetto e vuole un secondo numero (o nessuno, se il report va su un
canale invece che nel log).
**Proposta**: separare le costanti per lavoro (e battezzarle: vedi F6 sul fatto
che `RECYCLE_RETRY_SECONDS` non è nemmeno in `__all__`), oppure ratificare il
riuso dichiarandolo nel BRIEF.
**Verdetto: —**

---

## Igiene

### H2 — La docstring dello scambio (voce dell'issue #17, risolta)
**Cosa dice l'issue**: «The exchange docstring in commander.py (~1279) says the
commander discards an in-flight user's datachanges: it now ships them (the
worker discards). Align.»
**Cosa c'è davvero** (verificato 2026-08-13): a quell'àncora sta
`exchange_destinations` (`commander.py:1265`), la cui docstring
(`commander.py:1266-1273`) parla di **indirizzi irrisolvibili** — «An address
the surface cannot resolve — an unknown page, a target already swept — is
dropped with a debug log: a change is a signal and there is no retry queue» — e
il codice fa esattamente questo (`commander.py:1288-1292`). Non parla dell'utente
in trasferimento.
Il testo che parla dell'utente in volo sta in due altri posti, e **nessuno dei
due dice che il commander scarta**:
- `sweep_worker` (`commander.py:1783-1786`): «This reaches a user mid-move too —
  the map names the source until the switch — and the move machinery is built
  for exactly that window»;
- la docstring di modulo (`commander.py:180-181`): «the move's own `moving` hold
  parks whatever arrives for that user».
**Rilievo**: la frase che l'issue vuole correggere **non esiste** nell'albero
attuale. Le tre docstring candidate sono coerenti col codice. Due letture
possibili: (a) il testo è già stato allineato da un lavoro precedente e la voce
dell'issue è superata; (b) l'issue si riferiva a un quarto testo, in un file che
questa fase non legge (la zona `spa-world`, fase 4 — `worker.py` è dove il
"worker scarta" dovrebbe essere documentato).
**Proposta**: chiudere la voce come **superata** se la fase 4 non trova nulla in
`worker.py`; altrimenti la scheda si sposta là.
**Verdetto: —**

---

## Conteggio

33 schede: 6 di fedeltà (F1-F6) · 10 di battesimo (N1-N10) · 7 di specie 1
(D1-D7) più D8, che registra 6 guardie verificate NECESSARIE perché la fase 3
non le tocchi · 5 di specie 3 (I1-I5) · 3 di specie 4 (C1-C3) · 1 di igiene
(H2). **33 voci, 33 in attesa di verdetto.**

Le schede di specie 1 che la fase 3 deve provare con lo strip: D1, D2, D3, D4,
D5, D6 (D7 è una scheda di probabilità, non di raggiungibilità; D8 è l'elenco
delle guardie da NON toccare).
