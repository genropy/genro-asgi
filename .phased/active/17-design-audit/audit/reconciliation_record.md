# Registro 1 — Riconciliazione: codice, brief, notes, libro

**Workflow**: wf#17 design audit · **Fase**: 5 · **Data**: 2026-08-13
**Fonti**: `audit/00_authorities.md` (le tre autorità),
`audit/zone_recycling_code.md` (fase 2), `audit/zone_tests.md` (fase 3),
`audit/zone_spa_world.md` (fase 4). Nessuna riga di sorgente è stata letta di
nuovo qui: questo registro **non aggiunge rilievi**, li ordina.

**Cosa è questo documento**: l'ordine del giorno del walkthrough sulla
*fedeltà*. Una voce per riga di discussione: cosa dice l'autorità, cosa fa il
codice, l'àncora, le opzioni, e una casella **Verdetto: —** che questa run non
riempie mai. Le opzioni non sono raccomandazioni: sono le due o tre strade che
le fasi 2-4 hanno trovato praticabili.

Il registro dello **snellimento** è l'altro file (`audit/slimming_ledger.md`).
Le voci di battesimo stanno qui perché un nome è fedeltà a un'autorità (il
mandato di battesimo del BRIEF §7), non un taglio.

---

## Sezione 1 — I sei punti di fedeltà

### R1 ← F1 · Il task `planner` con `decision_interval` contro il battito a tre forze
**L'autorità dice** (BRIEF Q3a, brief:100-112, ratificato 2026-08-11 come
revisione dichiarata di wf#5 f8): «Pool-shape decisions (rebalance, recycling,
compaction) leave the probe return and move to their own global periodic task,
interval per-group config, default 5 minutes […] Probes stay at 5s for HEALTH
only». BRIEF §7 (brief:271-272) battezza `planner`, «the periodic task, sibling
of `caretaker`».

**Il codice fa**: le decisioni di forma vivono ancora dentro il ritorno della
sonda — `probe_worker` chiama `pool_beat()` alla riga successiva
(`commander.py:969-970`) e la docstring dichiara la decisione superata: «the
probe return IS the pool's heartbeat» (`commander.py:933`). `planner` e
`decision_interval`: zero occorrenze in `src/` e `tests/`.

**Delta**: **assente** — il BRIEF ha superato wf#5 f8, il codice ha
implementato wf#5 f8.

**Opzioni**: (a) implementare il `planner` come task periodico e ridurre la
sonda alla sola salute; (b) registrare la revisione al contrario — il battito
sulla sonda resta e il BRIEF Q3a viene emendato a verbale.

**Legato a**: R2 (la stessa decisione, vista dal lato del piano), voce L5 del
ledger (i tre `trigger_*`, che il piano farebbe collassare).

**Verdetto (2026-08-13, intervista col titolare): il codice si adegua — «il
piano ogni X minuti, assolutamente; non ha senso una mossa per volta».** Il
planner nasce come task periodico (intervallo per gruppo, default da BRIEF
Q3a), la sonda torna alla sola salute a 5s; le emergenze vere (un morto)
restano sul riflesso rapido. Il gate a peso di R4 corre dentro la costruzione
del piano, sulla lettura unica.

### R2 ← F2 · Il modello PLAN: una lettura → redistribuzione → sostituzioni dal peggiore → compattazione
**L'autorità dice** (BRIEF Q3b, brief:114-136): «the commander reads the WHOLE
pool once […] and builds an ordered PLAN of steps from that single reading, then
executes it sequentially. The plan as a whole is the one operation in flight; a
tick landing mid-plan does nothing. Ratified step order: rebalance → replacements
(worst first, possibly several, sequential) → compaction». E: «the
`compacting`/`rebalancing` flags collapse into the single plan-in-flight state».

**Il codice fa**: nessun oggetto piano. `pool_beat`
(`commander.py:2656-2664`) sceglie **una** forza per battito in XOR; ogni forza
rilegge il pool da sé (`commander.py:2748`, `3018`, `2904-2910`); i tre flag
restano tre attributi distinti (`commander.py:597-599`); la sostituzione è una
per passata, non «possibly several» (`commander.py:3011-3021`, con
`recycle_candidate` che rifiuta se un'evacuazione è aperta,
`commander.py:2994-2995`).

**Delta**: **derivato** — l'ordine di precedenza è quello del BRIEF
(`commander.py:2636-2642`), la meccanica è la XOR che il BRIEF ha superato.

**Opzioni**: (a) costruire il piano (una lettura, lista di passi, uno stato
`plan-in-flight` che sostituisce i tre flag); (b) emendare Q3b registrando la
XOR con precedenza come meccanica scelta, e togliere dal BRIEF la frase sui
flag collassati.

**Legato a**: R1; ledger L5 (i tre `trigger_*`).

**Verdetto (2026-08-13, intervista col titolare): il codice si adegua — si
costruisce il PLAN come da BRIEF Q3b.** Una lettura dell'intero parco, lista
ordinata di passi (riequilibrio → sostituzioni dal peggiore, anche più d'una,
in sequenza → compattazione), un solo stato piano-in-volo che sostituisce i
tre flag; un tick che atterra a piano aperto non fa nulla. I tre `trigger_*`
cadono con lui (ledger L5).

### R3 ← F3 · `designated_reception` per l'accoglienza condannata
**L'autorità dice** (BRIEF Q4-bis, brief:151-166): «when the plan condemns THE
RECEPTION, a fresh worker is spawned and the reception ROLE is assigned to it —
a declared revision of the wf#5 "positional, no flag and no election" decision
(a designation pointer on the commander, positional fallback when the designated
one dies)». BRIEF §7 battezza `designated_reception` e `condemned_workers`.

**Il codice fa**: l'accoglienza è rimasta posizionale — `reception` è
`active_workers[0]` (`commander.py:629-636`), con la docstring che cita la
decisione superata. Il ruolo **si sposta comunque**, come effetto collaterale
del flag: lo stato `evacuating` (`commander.py:3153`) toglie il worker da
`active_workers` (`commander.py:613-617`). Ma il rimpiazzo fresco si registra
prima del flag (`commander.py:3134-3136`), quindi è l'**ultimo** attivo: la
nuova accoglienza è il secondo worker più vecchio, non il fresco che il BRIEF
designa. `designated_reception` e `condemned_workers`: zero occorrenze.

**Delta**: **assente** come simbolo, **divergente** come comportamento.

**Opzioni**: (a) implementare il puntatore con fallback posizionale,
assegnandolo al rimpiazzo; (b) registrare che lo spostamento posizionale basta
ed emendare Q4-bis.

**Sotto-voce ancora PENDING** (NOTES notes:75, deferita dal titolare in wf#8):
«GUESTS ARE RELOCATED TOO during an evacuation […] their forced destination is
the NEW reception». Oggi gli ospiti non sono rilocati: `rebalance_weights`
dichiara che un ospite «is on no map and never moves»
(`commander.py:2801-2805`) e `evacuation_pass` salta chi non è sulla mappa
(`commander.py:3062-3063`). Resta PENDING: il worker non ha un'op di inventario
degli ospiti.

**Verdetto (2026-08-13, intervista col titolare): designazione esplicita, con
statuto speciale.** Quando si condanna l'accoglienza il rimpiazzo fresco
nasce **sempre, subito, senza gate a peso** — unica eccezione alla regola di
R4: qui non è capienza, è continuità del ruolo — e il ruolo gli viene
designato immediatamente (puntatore sul commander, fallback posizionale se il
designato muore, come da BRIEF Q4-bis). Travaso in quest'ordine: prima **gli
ospiti** (la sotto-voce PENDING si chiude: sì, si rilocano, destinazione
forzata la nuova accoglienza; serve l'op di inventario ospiti sul worker),
poi gli utenti del vecchio portiere **fino alla capienza concordata** del
fresco; l'eccedenza si colloca sugli altri con la regola best-fit di R4.

### R4 ← F4 · Spawn a libro mastro (`capacity_headroom`)
**Le due autorità si contraddicono** — è il primo fatto della voce.
BRIEF Q4 (brief:138-150): «at plan build, `capacity_headroom()` says whether the
pool can absorb the sick worker's users — if not, `scale(target + 1)` FIRST […];
if the room is there, no new process at all». NOTES notes:11-13, ratificata in
walkthrough: «THE SICK WORKER IS FLAGGED ONLY AFTER ITS SUCCESSOR REGISTERED: a
replacement that never comes leaves it untouched, by construction».

**Il codice fa**: segue le NOTES alla lettera e ignora il libro mastro.
`recycle_worker` chiama `spawn_worker()` incondizionatamente
(`commander.py:3134`), attende (`commander.py:3136`), flagga dopo
(`commander.py:3153`), e la docstring cita la contro-decisione in maiuscolo
(`commander.py:3111-3113`). `capacity_headroom` (`commander.py:2872`) ha **un
solo lettore**, la compattazione (`commander.py:2908`). Il TARGET non è toccato
dal riciclo (`commander.py:3107-3109`): il pool si allarga di fatto di un
worker per la durata dell'evacuazione, fuori da `scale`.

**Delta**: **divergente dal BRIEF, conforme alle NOTES**. Il ramo «se lo spazio
c'è, nessun processo nuovo» non esiste.

**Opzioni**: (a) aggiungere il gate del libro mastro prima dello spawn — e
decidere cosa fa il riciclo quando lo spazio c'è (evacuare senza rimpiazzo, che
è il ramo mai scritto); (b) ratificare le NOTES come autorità prevalente ed
emendare Q4.

**Nota di metodo**: questa è l'unica voce del registro in cui il verdetto
decide anche **quale autorità prevale**, non solo cosa fa il codice.

**Verdetto (2026-08-13, intervista col titolare): prevale il BRIEF, raffinato
— gate a peso, con margine; e le due autorità smettono di contraddirsi.** Al
momento del piano si calcola il peso degli utenti da togliere e il peso
ricevibile dagli altri processi **dello stesso gruppo**: se lo reggono **con
ampiezza** (margine, non incastro esatto — i riceventi non devono finire a
ridosso della saturazione, o il ricambio innesca altri ricambi a domino),
nessun processo nuovo; altrimenti nasce il sostituto, e per quel ramo la
garanzia delle NOTES resta intatta: prima vivo e registrato, poi si condanna.
Le due autorità rispondevano a domande diverse — il BRIEF decide *se*
spawnare, le NOTES *l'ordine* quando si spawna. In entrambi i casi il
collocamento è a **best-fit sotto il tetto di saturazione**: ogni utente va
sul processo **più pieno che può ancora accoglierlo senza saturare**, mai sul
più vuoto (esempio del titolare: capienza 100, saturazione 80 — l'utente da
10 va su chi ha 40 liberi, non sul fresco con 100 liberi). Consolidare, non
spalmare: il fresco resta il più scarico possibile e il parco resta
compattabile. La regola è una sola
per ogni condanna, inclusa la destinazione marcata morente da
un'installazione fallita (R17). «Peso» e «ampiezza» si definiscono sulla
sensoristica di occupazione già ratificata (saturazione per componente) alla
run di fix.

### R5 ← F5 · `floor_series_depth` 48 vs 72; minimo di fit 3 vs 6
**L'autorità dice** (BRIEF Q6, brief:208-223): «Series depth K — default 48
points (one per 5-min window ≈ 4 hours of evidence)» e «Minimum 3 points before
judging = MODULE CONSTANT, not a kwarg». BRIEF Q2 (brief:97-98): «K_min = 3;
below it T = ∞». NOTES notes:102-103 registrava già lo scarto.

**Il codice fa**: `FLOOR_SERIES_DEPTH = 72` (`commander.py:334`), motivato da
una finestra di prova diversa da quella del BRIEF — «72 of them span ~6 hours»
(`commander.py:332-334`) contro le 4 ore del BRIEF. La forma è quella chiesta:
kwarg per gruppo (`commander.py:464`, letto a `530`, `maxlen` a `1004`). Il
minimo è `_FLOOR_FIT_MINIMUM = 6` (`evaluator.py:91`), costante di modulo
**privata** e non in `__all__` (`evaluator.py:81`). Le altre due kwarg di Q6
hanno i valori del BRIEF (`recycle_horizon_hours=12.0`, `commander.py:395`,
`465`); la terza — il tick — non esiste (R1).

**Delta**: **divergente sui valori** (72 vs 48, 6 vs 3), **conforme sulla
forma**. Aggiunta non chiesta: la privatezza della costante.

**Opzioni**: (a) allineare ai valori del BRIEF (48 e 3); (b) ratificare 72 e 6
emendando Q6 e Q2 con le ragioni dichiarate nelle docstring (finestra a 6 ore,
robustezza del fit); (c) mista — allineare la profondità della serie, tenere 6
come pavimento statistico. Sotto-domanda in ogni caso: `_FLOOR_FIT_MINIMUM`
entra in `__all__`?

**Legato a**: ledger L2 (la correzione di accelerazione vive sulla stessa
serie: i due numeri e la correzione si decidono nello stesso passaggio).

**Verdetto (2026-08-13, intervista col titolare): la questione si dissolve —
il grilletto del ricambio cambia natura, e la previsione scende da giudice a
strumento.** Lo scopo dichiarato dal titolare: la memoria che un processo
tiene impegnata (X) oltre quella davvero usata (Y, il pavimento) è spreco che
torna al sistema operativo solo ruotando il processo. Il ricambio decide
quindi su **misure del momento, non su curve**, con tre grilletti
configurabili per gruppo: (1) **necessità** — il pavimento si avvicina al
limite del gruppo: sostituzione prioritaria; (2) **convenienza** — lo spreco
X−Y supera una soglia (assoluta o in rapporto all'impegnata): candidato a
rotazione, il piano prende dal più sprecone quando c'è ampiezza; (3)
**vuoto** — un processo rimasto senza utenti (tipicamente ore notturne) si
spegne senza rimpiazzo, rispettando un minimo di parco (il portiere resta
sempre) ed eventuale attesa di grazia; e la compattazione è anche attiva —
**parte sempre dal processo più vuoto e cerca di togliergli gli ultimi
utenti** (destinazione a best-fit come da R4), così da liberarlo e spegnerlo.
**Addendum (stessa intervista) — i rifiuti come segnale**: il conteggio dei
503 d'ingresso in una finestra di tempo è un allarme di **capacità del
pool**, non di salute di un worker: dove il contesto di deploy ha la
gerarchia multi-macchina (parte 3 del libro), il commander scala fuori
creando/chiedendo un **sub-commander**; dove non c'è gerarchia, nessuna
meccanica — il segnale resta visibile nella fotografia (R19) e la decisione
è umana. Gli **errori del singolo worker** sono invece un grilletto: troppi
in una finestra di tempo (richieste fallite, operazioni rifiutate, risposte
che non tornano) → marcato morente, percorso di rimozione standard — seconda
voce della *necessità*, accanto alla memoria e coerente con l'installazione
fallita (R17). Soglie e finestra: run di fix. Il «tetto a orologeria» resta
rifiutato: la frequenza di rotazione attesa (~4-5 ore) è l'effetto dello
spreco che si accumula, mai una scadenza di calendario. La serie dei
pavimenti, la tendenza e il «mancano X» restano come **strumento di
osservazione** nella fotografia del monitor (R19) e campanello d'anticipo
della necessità; profondità, minimo di fit, correzione d'accelerazione e
visibilità della costante diventano dettagli dello strumento, da fissare alla
run di fix senza ratifica solenne. Valori di default delle tre soglie: run di
fix.

### R6 ← F6 · I nomi coniati durante la run e mai ratificati
**L'autorità dice**: il mandato di battesimo era «reasonable names for a reader
who knows nothing» (BRIEF §7, brief:260-261); NOTES notes:81-84 e notes:109-114
elencano i simboli **da ratificare**; NOTES notes:127-128: «names ledger
unanswered = names stand».

**Il codice fa**: i dieci nomi esistono e sono in uso — sono le voci R7..R16 di
questo registro. I **tre nomi del pannello di finalize** (NOTES notes:169-171)
hanno esito diverso: `RECYCLE_RETRY_SECONDS` esiste (`commander.py:403`) ma non
è in `__all__` (`commander.py:304-321` elenca `RECYCLE_HORIZON_HOURS` e non
lei), mentre i test la importano (`tests/test_spa_move.py:58`);
`abandon_recycle` e il campo roster `recycle_failed_at` hanno zero occorrenze —
il concetto è arrivato come attributo di commander `regeneration_failed_at`
(`commander.py:596`).

**Delta**: **conforme** sui dieci, **divergente** sui tre del pannello (uno non
esportato, due mai nati con quel nome).

**Opzioni**: (a) battesimo voce per voce (R7..R16); (b) decidere se
`RECYCLE_RETRY_SECONDS` entra in `__all__` — oggi è pubblica di fatto e non
dichiarata; (c) ratificare che `regeneration_failed_at` (attributo di pool)
**sostituisce** `recycle_failed_at` (campo di riga): la fase 2 osserva che la
condizione è del pool, non di un worker, quindi la differenza da ratificare non
è solo il nome ma la sede.

**Legato a**: ledger L4 (`RECYCLE_RETRY_SECONDS` che fa tre lavori con lo
stesso numero).

**Verdetto (2026-08-13, intervista col titolare): chiusa per rimando.** I
dieci nomi sono battezzati voce per voce (R7..R16); dei tre nomi del pannello
di finalize non sopravvive nulla: `RECYCLE_RETRY_SECONDS` muore con L4, e
`abandon_recycle`/`recycle_failed_at` cadono col concetto stesso di
condizione persistente (R14 — punto 3 delle NOTES superseduto a verbale).
**Regola di vocabolario (stessa intervista): una parola sola — «removal» —
per tutta la storia dello svuotamento di un condannato**: lo stato di riga,
la passata, l'ordine di uscita (`drain_order` → famiglia removal), il
trasferimento del singolo utente (`evacuate_user` → famiglia removal), in
fila con `removal_started_at` (R15). I battesimi puntuali avvengono alla run
di fix sui corpi riscritti, dentro questo vocabolario. **Collisione sciolta (stessa intervista)**: l'esistente `remove_user`
(commander) significa «dimentica dalla superficie», non trasloco — diventa
**`drop_user`**, il vocabolario del legacy verificato sul repo
(siteregister.py:595, con la famiglia coerente `drop_page`,
`drop_connection`). Due parole, due concetti: **removal** = trasloco fuori da
un condannato, **drop** = oblio dalla superficie. `floor_slope` non è della
famiglia e si tiene.

---

## Sezione 2 — Battesimo: i dieci nomi

Formato: semantica reale in una frase, chi chiama, candidati. Il battesimo è
del titolare; «tenere» è un verdetto come un altro. Le àncore sono verificate
al 2026-08-13.

### R7 ← N1 · `floor_slope(samples)` · `evaluator.py:258`
**Semantica**: la pendenza Theil-Sen (mediana delle pendenze a coppie) di una
lista di campioni `{ts, floor}`, in **byte all'ora**; `None` quando nessuna
coppia è separata nel tempo. Funzione pura: non legge nessun worker.
**Chi chiama**: `worker_floor_velocity` due volte (`evaluator.py:291` sulla
serie intera, `evaluator.py:296` sulla metà recente) e un test
(`tests/test_spa_evaluator.py:491`).
**Candidati**: `floor_slope` (tenere — dice soggetto + grandezza, ma non l'unità
né la robustezza) · `floor_climb_rate` · `floor_trend_per_hour`.
**Nota**: il BRIEF §7 battezza solo `worker_floor_velocity` (brief:266); questo
è il gradino sotto, e `slope` è l'unica parola del gruppo che non porta l'unità.
**Verdetto: —**

### R8 ← N2 · `wait_worker_ready(name)` · `commander.py:3159`
**Semantica**: attende che **quel** worker passi ad `active`, polling a 20ms e
`READY_TIMEOUT`; alza `TimeoutError` subito se la riga è già `dead`.
**Chi chiama**: `recycle_worker` (`commander.py:3136`) e un test
(`tests/test_spa_move.py:2557`).
**Il problema**: il gemello `wait_workers_ready(count)` (`commander.py:795`)
conta i worker; la sola differenza fra i due nomi è il singolare, e si legge
male ad alta voce.
**Candidati**: `wait_for_worker` · `await_worker_registered` · tenere
`wait_worker_ready` accettando la vicinanza al plurale.
**Legato a**: ledger L21 (i corpi delle due attese sono duplicati; il concetto
invece è distinto e resta).
**Verdetto (2026-08-13, intervista col titolare): battezzati entrambi i
gemelli.** Il singolare diventa **`wait_for_worker`** (attesa del proprio
rimpiazzo); il plurale diventa **`wait_pool_ready`** (cancello di prontezza
del parco — la cosa che diventa pronta è il pool, non il commander che
aspetta). La *s* ambigua sparisce.

### R9 ← N3 · `drain_order(worker)` · `commander.py:2947`
**Semantica**: gli utenti della riga ordinati in due scaglioni alfabetici —
prima chi non ha chiamate in `pending`, poi gli altri.
**Chi chiama**: `drain_worker` (`commander.py:2936`) e `evacuation_pass`
(`commander.py:3059`) — non è più solo del drenaggio.
**Candidati**: `drain_order` (tenere — l'evacuazione *è* un drenaggio) ·
`departure_order` · `idle_first_users`.
**Verdetto: —**

### R10 ← N4 · `advance_evacuations()` · `commander.py:3025`
**Semantica**: **non muove nessuno**. Scorre le righe `evacuating`, ritira
quelle rimaste vuote, e per le altre chiama il report di stallo. Contabilità
sincrona, per battito.
**Chi chiama**: `pool_beat` (`commander.py:2658`) e un test
(`tests/test_spa_move.py:2714`).
**Il problema**: `advance` promette movimento; il metodo chiude i libri di
evacuazioni già finite. È la trappola dell'omonimia già vista in wf#4.
**Candidati**: `close_finished_evacuations` · `settle_evacuations` ·
`review_evacuations`.
**Verdetto: —**

### R11 ← N5 · `evacuation_pass(worker)` · `commander.py:3044`
**Semantica**: la passata di **apertura** — muove ora solo gli utenti senza
chiamate pendenti, salta i mid-call senza attenderli, ritira il worker se resta
vuoto.
**Chi chiama**: solo `recycle_worker` (`commander.py:3156`).
**Il problema**: gli altri `*_pass` (`rebalance_pass`, `compact_pass`,
`recycle_pass`) sono passate **di forza**, prese da `pool_beat` e guardate da un
flag; questa sta dentro `recycle_worker` e non ha flag proprio — la simmetria del
nome promette una simmetria di meccanica che non c'è.
**Candidati**: `evacuation_pass` (tenere — «pass» è il vocabolario in uso) ·
`evacuate_the_idle` · `open_evacuation`.
**Verdetto: —**

### R12 ← N6 · `evacuate_user(user, worker)` · `commander.py:2243`
**Semantica**: porta via **un** utente appena liberatosi da un worker in
evacuazione; se non riesce lo **dimentica dalla superficie** (`remove_user`,
`commander.py:2273`) con un ERROR, così la chiamata successiva è un KeyError
rumoroso e il client rifà login.
**Chi chiama**: solo `close_request` (`commander.py:2241`), come task distaccato.
**Il problema**: «evacuare un utente» suggerisce che l'utente esca dal sistema;
esce dal **worker**.
**Candidati**: `evacuate_user` (tenere) · `carry_user_out` · `move_freed_user`.
**Verdetto: —**

### R13 ← N7 · `warn_stalled_evacuation(worker)` · `commander.py:3073`
**Semantica**: emette un WARNING quando un'evacuazione è aperta da più di
`CONNECTION_MAX_AGE` e non è finita, con throttle a `RECYCLE_RETRY_SECONDS` per
worker.
**Chi chiama**: solo `advance_evacuations` (`commander.py:3042`).
**Candidati**: `warn_stalled_evacuation` (tenere) · `report_stalled_evacuation`
(«report» è la parola delle NOTES, notes:26-29, e prefigura il canale
`_server/<nome>` che sostituirà il log) · `flag_evacuation_stall`.
**Legato a**: ledger L1 (se il report di stallo non è una voce di prodotto, il
nome non serve affatto) e L4 (il throttle riusa la costante del riciclo).
**Verdetto (2026-08-13, intervista col titolare): il metodo cade — niente da
battezzare.** Il WARNING di stallo è sostituito dalla scadenza che agisce
(L1): allo scadere, migrazione forzata — la richiesta lenta muore, lo stato
dell'utente si conserva. Il nome della nuova azione si battezza alla run di
fix.

### R14 ← N8 · `regeneration_failed_at` · `commander.py:596`
**Semantica**: l'istante monotonico in cui un rimpiazzo non è riuscito a
registrarsi. Finché è più giovane di `RECYCLE_RETRY_SECONDS` fa due cose:
`worker_for` rifiuta i **nuovi** ingressi con 503 (`commander.py:2118-2120`) e
`recycle_candidate` non sceglie nessuno (`commander.py:2996-2998`). Si azzera al
primo REGISTER riuscito (`commander.py:1132-1134`).
**Candidati**: `regeneration_failed_at` (tenere — soggetto + evento + istante) ·
`spawn_failed_at` · `pool_sterile_since`.
**Da ratificare oltre al nome**: la **sede**. Il pannello di finalize aveva
coniato `recycle_failed_at` come campo di riga (NOTES notes:169-171); il codice
ha fatto un attributo di commander, perché la condizione è del pool. Vedi R6
opzione (c).
**Verdetto (2026-08-13, intervista col titolare): l'attributo cade — il
titolare SUPERSEDE a verbale il punto 3 delle NOTES.** La rigenerazione
fallita non è più uno stato che dura: **il 503 è una risposta, non una
condizione** — solo la richiesta che ha trovato il pool incapace di
accoglierla lo riceve; la successiva ci riprova da capo. Il freno alle nuove
condanne lo fornisce gratis la cadenza del planner (R1): un passo di piano
fallito si ritenta alla passata successiva, che rilegge il mondo. Niente
stato, niente battesimo, niente sede.

### R15 ← N9 · roster `evacuating_since` · `commander.py:1006` (documentato a 989-992)
**Semantica**: istante monotonico in cui il riciclo ha messo la riga in
`evacuating` (scritto a `commander.py:3154`); serve **solo** a distinguere
un'evacuazione stallata (`commander.py:3083-3084`).
**Candidati**: `evacuating_since` (tenere) · `evacuation_opened_at` ·
`condemned_at` (allinea al vocabolario del BRIEF, `condemned_workers`,
brief:269 — vedi R3).
**Verdetto (2026-08-13, intervista col titolare): battezzato
`removal_started_at`.** Concetto del titolare («la rimozione è iniziata il»),
vestito nella convenzione della riga di roster (`spawned_at`, `died_at`): il
ciclo di vita si legge in tre campi — nascita, inizio rimozione, morte. Il
campo resta il motore della scadenza di sgombero (L1) e la sorgente del
«in rimozione da quando» della fotografia (R19).

### R16 ← N10 · roster `evacuation_warned_at` · `commander.py:1007` (documentato a 992)
**Semantica**: istante dell'ultimo WARNING di stallo, per il throttle
(`commander.py:3086-3089`).
**Candidati**: `evacuation_warned_at` (tenere) · `stall_reported_at` ·
`last_stall_warning`.
**Verdetto (2026-08-13, intervista col titolare): il campo cade** col WARNING
di stallo (L1): il freno anti-raffica non ha più nulla da frenare.

---

## Sezione 3 — Disaccordi col libro

Le opzioni qui sono sempre le stesse due, come deciso in pianificazione:
**(a) il codice si adegua** · **(b) il titolare emenda il libro a verbale**.
Nessuna terza strada, e nulla muore per difetto.

Le 18 affermazioni `spa-world` risultate **vere alla lettera** stanno in
`audit/zone_spa_world.md` §A con la loro àncora, e non sono voci di registro:
non c'è nulla da decidere su di esse.

### R17 ← E4 · «se l'installazione non riesce, l'utente deve restare dov'era»
**Il libro dice** (*Il momento in cui l'utente non è da nessuna parte*): la
richiesta che arriva durante lo spostamento «deve attendere, non fallire — e se
l'installazione non riesce, l'utente deve restare dov'era, non sparire».
**Il codice fa**: prima clausola vera — la barriera per-utente
(`commander.py:579`) è alzata prima di tutto (`commander.py:2459`) e ogni
forward vi si parcheggia (`commander.py:2087`, `2617-2624`). Seconda clausola
**divergente**: il punto di non ritorno è lo sfratto, dove la sorgente si
spoglia mentre risponde (`worker.py:2251`), quindi «restare dov'era» non è più
uno stato raggiungibile. Ciò che il codice garantisce è *un'altra stanza*:
`install_in_custody` (`commander.py:2567`) ritenta su `salvage_target`
(`commander.py:2605-2610`, sorgente inclusa) e alza un errore esplicito se il
pool è vuoto (`commander.py:2603`). Un caso di sparizione reale esiste: utente
spazzato mentre il pacco era in custodia → fetta scartata con warning
(`commander.py:2481-2498`). Prima dello sfratto il libro è rispettato alla
lettera (`commander.py:2462-2467`, `2469-2474`).
**Opzioni**: (a) servirebbe una copia trattenuta alla sorgente fino alla
conferma — un rollback che oggi non esiste in nessun punto del disegno;
(b) emendare la seconda clausola nella garanzia vera: «la fetta non si perde
mai in silenzio — atterra da qualche parte, o muore rumorosamente».
**Verdetto (2026-08-13, intervista col titolare): il codice si adegua —
consegna riordinata.** Flag → copia (la sorgente trattiene la sua) →
installazione → conferma → solo allora cancellazione e caduta del flag:
nessuna finestra in cui l'utente non è da nessuna parte, e la frase del libro
diventa vera alla lettera. Prezzo accettato a verbale: i dati esistono in due
posti per la durata del trasferimento (il flag impedisce ogni divergenza).
Fallimento d'installazione: **nessun ripiego immediato su un'altra
destinazione** — la catena `salvage_target` si rimuove; l'utente resta alla
sorgente, integro; la destinazione fallita diventa **morente** ed entra nel
percorso di ricambio standard, col rimpiazzo fresco creato in automatico (la
politica di gate sullo spawn è la questione R4). Errore rumoroso a ogni
fallimento; il riprovare è quello naturale delle passate periodiche. Sparisce
il caso «utente spazzato mentre il pacco era in custodia»: la custodia come
limbo non esiste più.

### R18 ← E14 · «la persona continua a essere servita dove si trova»
**Il libro dice** (*Il governo dei processi*): «La mappa si aggiorna per ultima:
finché l'installazione non è confermata, la persona continua a essere servita
dove si trova, e se la destinazione muore le si offre un altro posto.»
**Il codice fa**: prima e terza clausola confermate (`commander.py:2500`,
dichiarato a `222-224`; `commander.py:2605-2610`, dichiarato a `226-228`). La
clausola centrale è **imprecisa**: durante la finestra la chiamata è
*parcheggiata* sulla barriera (`commander.py:2087`, `2617-2624`) e riparte alla
sua caduta (`release_move`, `commander.py:2612-2615`). La mappa continua a
nominare la sorgente — ed è per questo che nulla è instradato male — ma il
servizio è sospeso, non continuo.
**Il fatto notevole**: **è il libro a contraddire se stesso**, non il codice a
divergere. E4 dice «deve attendere», E14 dice «continua a essere servita»: la
stessa finestra descritta in due modi incompatibili.
**Opzioni**: (a) **nessun codice da cambiare**; (b) allineare la frase a quella
di E4 («la richiesta attende, e quando la barriera cade trova la persona al
posto giusto»).
**Verdetto (2026-08-13, intervista col titolare): nessun codice — si allinea
la frase del libro, resa precisa e meno assoluta.** Il servizio durante la
finestra è sospeso, non continuo: è la sospensione stessa a garantire che le
due copie non divergano (ratificato dallo schema del titolare in R17). La
frase nuova precisa la scala: la richiesta attende — nella quasi totalità dei
casi una manciata di millisecondi, impercettibile — e quando il flag cade
trova la persona al posto giusto. Da applicare alla prossima rigenerazione
del libro, insieme alle correzioni numeriche di R22/R23.

### R19 ← E21 · «per ogni processo lo stato nel ciclo di vita, quando è nato e, se è morto, quando e come»
**Il libro dice** (*Il ponte con l'esistente*): una chiamata sola compone la
popolazione viva — utenti, connessioni, pagine, consumi — «e per ogni processo
lo stato nel ciclo di vita, quando è nato e, se è morto, quando e come. Un
processo irraggiungibile non fa cadere la lettura».
**Il codice fa**: `population()` (`commander.py:1976-2006`) è davvero una
chiamata sola (fan-out concorrente, `commander.py:1986`) e porta utenti,
connessioni, pagine (`2002-2004`) con il consumo cumulativo fuso all'arrivo
(`1993-2000`); l'irraggiungibilità compare come `row["error"] = "unreachable"`
(`commander.py:1991`) senza far cadere la lettura (`1970-1972`). **Le clausole
sul ciclo di vita non sono servite da nessuna parte**: la riga porta `id`,
`group`, poi `error` oppure `users`/`connections`/`pages` — mai `status`,
`spawned_at`, `died_at`, `death`, che esistono nella riga di roster
(`commander.py:995-1000`) e sono letti solo internamente e dal log di sepoltura
(`commander.py:890-896`). `metrics_view` (`commander.py:1936-1955`) non li porta
neppure. E `population()` cammina solo `active_workers`
(`commander.py:1985`): un processo morto non ha nemmeno una riga in cui stare.
Nessun consumatore fuori dai test (`tests/test_spa_monitor.py:271`, `289`,
`298`, `306`).
**Delta**: **parzialmente assente** — due clausole su quattro senza
implementazione. È il buco più grosso della sezione.
**Opzioni**: (a) la riga di `population()` porta anche
`status`/`spawned_at`/`died_at`/`death` e la lista include le tombe finché la
sepoltura non le rimuove; (b) togliere dal libro le due clausole, che
descrivono il monitor legacy e non questo.
**Verdetto (2026-08-13, intervista col titolare): il codice si adegua —
fotografia a due strati.** Uno strato del commander (lo stato del momento del
pool: per ogni processo stato attivo/morente/morto, nascita, per i morenti
da-quando e utenti residui, per i morti quando-e-come finché la sepoltura non
rimuove la riga; più lo stato del pool — passata in volo, quarantena da
rigenerazione fallita) e una fotografia per ogni worker (il suo interno,
com'è già oggi; per i morti parla solo la riga del commander). Un worker muto
non fa cadere la lettura, e lo stato accanto distingue «muto perché morente»
da «muto perché malato». **Il dettaglio dei campi è rimandato al design della
run di fix** — il titolare ha nominato esempi da valutare lì: le tabelle
sottoscritte, le chiamate fatte da un certo utente.

### R20 ← E22 · «i registri contengono dati serializzabili per costruzione»
**Il libro dice** (*Lo stato di lavoro attraversa le versioni*): «i registri
contengono dati serializzabili per costruzione, mai oggetti vivi come verità».
**Il codice fa**: la sostanza tiene dove conta — ciò che viaggia è
serializzabile e ciò che è vivo viene **ricostruito** a destinazione, non
spedito (`MOVE_REBUILT_FIELDS`, `worker.py:341-343`; `LIVE_ROW_FIELDS`,
`worker.py:333-337`, usato da `wire_entry`, `1127-1140`; lo store viaggia come
Bag dentro il pickle, `worker.py:2244-2252`). Ma **le righe dei registri
contengono oggetti vivi**: riga di pagina con `store`, `collector`, `user_view`
(`register_registry.py:308-324`, dichiarati «vivi» a `85-96`) — e il
`collector` *è* la verità di ciò che una pagina deve ancora ricevere, aggirata
drenandola in valori al momento del pacco (`worker.py:2219-2227`); riga di
roster con `process` e `caretaker` (`commander.py:29-31`, creati a `976`), che
non viene mai serializzata (il dump scrive le fette utente,
`commander.py:701-731`).
**Delta**: **derivato** — la regola vale per ciò che attraversa le versioni, non
per le righe dei registri, che ospitano oggetti vivi per disegno.
**Opzioni**: (a) **nessun codice**: l'alternativa sarebbe togliere gli oggetti
vivi dalle righe, cioè il disegno opposto a quello ratificato; (b) il libro
precisa il soggetto: «ciò che viaggia è serializzabile per costruzione; gli
oggetti vivi restano nel processo e vengono ricostruiti a destinazione, mai
spediti».
**Verdetto (2026-08-13, intervista col titolare): il libro sbaglia — i
registri ospitano oggetti vivi, per disegno.** Nessun codice da cambiare. La
frase si riscrive col soggetto giusto: niente di vivo attraversa mai il
confine tra processi o tra versioni — viaggia solo materia inerte, e il vivo
si ricostruisce a destinazione. Da applicare alla prossima rigenerazione del
libro.

### R21 ← E26 · «la colonna del gruppo è già presente in ogni registro»
**Il libro dice** (Roadmap, *Gruppi e versioni conviventi — in
implementazione*): «la colonna del gruppo è già presente in ogni registro».
**Il codice fa**: la colonna esiste in **un** registro, la riga di roster
(`commander.py:997`, dal kwarg `445`, campo `513`). Gli altri sette registri
piatti non hanno colonne — sono mappe chiave→chiave o chiave→set
(`commander.py:554-568`). Il gruppo di un utente è **derivato** dalla riga del
suo worker (`commander.py:48-49`). Nei registri del worker
(`register_registry.py:133-140`) la parola `group` non compare.
**Contraddizione interna al libro**: B7 lo dice giusto («ricopiato in ogni riga
del *roster*»), E26 dice «in ogni registro».
**Opzioni**: (a) **nessun codice** — il gruppo derivato è il disegno voluto;
(b) allineare E26 al testo di B7.
**Verdetto (2026-08-13, intervista col titolare): nessun codice — il gruppo
derivato dal roster è il disegno voluto.** La frase generalizzante di E26 si
allinea al testo corretto di B7 alla prossima rigenerazione del libro. I
gruppi come funzione vera restano lavoro di roadmap, non di questa
riconciliazione.

### R22 ← B1 · I conteggi per modulo: nove esatti, uno derivato di +3
**Il libro dice** (*11 · Piano SPA — orchestrazione*), colonna **Stmt**, totale
di blocco «2.580 stmt · 95%» (`docs/html/architettura_blocchi.html:603`, riga di
`commander.py` a `610`, ripetuto in prosa a `671`).
**Il codice dà** (misurato 2026-08-13, `pytest --cov=src/genro_asgi/spa`): nove
moduli su dieci coincidono **alla cifra**; `commander.py` è 1212 stmt contro
1209 (+3), totale di blocco 2.583 contro 2.580.
**Rilievo di metodo da conservare**: la nota di fase 1
(`00_authorities.md:360-363`) prevedeva uno scarto grosso perché `commander.py`
«è oggi 3183 righe». **Quello scarto non esiste**: la colonna del libro è
`Stmt`, non righe fisiche. La previsione era sbagliata sulla natura del numero,
non sul numero.
**Delta**: **conforme con deriva di 3 statement su 2.583** (0,1%).
**Opzioni**: (a) nessun codice; (b) i due numeri si aggiornano alla prossima
rigenerazione del libro — l'ebook si genera da misura, quindi questa è un
promemoria di rigenerazione, non una correzione a mano.
**Verdetto (2026-08-13, intervista col titolare): nessun codice — promemoria
di rigenerazione.** Il libro si rigenera dopo la run di fix (il codice sarà
comunque cambiato); i numeri si riallineano da soli in quella sede.

### R23 ← B7 · «nessun test passa mai un valore diverso» (e l'àncora 990)
**Il libro dice** (*Stato delle capacità*): «Gruppi di worker — Solo progettato
— esiste solo l'etichetta: un kwarg `group` di default "default" ricopiato in
ogni riga del roster (`commander.py:445`, 990) e riletto solo dal log di
sepoltura e dal monitor. L'instradamento è cieco al gruppo […] e nessun test
passa mai un valore diverso».
**Il codice fa**: la sostanza tiene interamente — kwarg a `commander.py:445`
(default `DEFAULT_GROUP`, `323-324`, dichiarato PROVISIONAL), copia nella riga
a **`commander.py:997`** (il libro dice 990: àncora derivata di 7 righe),
riletta in due soli punti (`commander.py:890`, `894` e `1989`), `decide_worker`
(`commander.py:2127`) non nomina il gruppo. **L'ultima clausola è letteralmente
falsa oggi**: un test passa `group="site-group"`
(`tests/test_spa_application.py:57`) — ma asserisce solo che il kwarg viene
sbucciato e inoltrato (`tests/test_spa_application.py:61-69`): nessun
comportamento cambia col valore.
**Delta**: **conforme nella sostanza**, due precisazioni (àncora 990 → 997;
«nessun test passa mai un valore diverso» → «un test passa un valore diverso e
asserisce solo che viene inoltrato»).
**Opzioni**: (a) nessun codice; (b) correggere àncora e clausola alla prossima
rigenerazione.
**Verdetto (2026-08-13, intervista col titolare): nessun codice — àncora e
clausola si correggono alla prossima rigenerazione del libro**, insieme a
R18, R20, R21 e R22.

---

## Sezione 4 — Igiene

### R24 ← H2 · La docstring dello scambio: la frase non esiste
**Cosa chiedeva l'issue #17**: «The exchange docstring in commander.py (~1279)
says the commander discards an in-flight user's datachanges: it now ships them
(the worker discards). Align.»

**Cosa hanno trovato le fasi 2 e 4** (verificato 2026-08-13): a quell'àncora
sta `exchange_destinations` (`commander.py:1265`), la cui docstring
(`1266-1273`) parla di **indirizzi irrisolvibili** — «An address the surface
cannot resolve […] is dropped with a debug log: a change is a signal and there
is no retry queue» — e il codice fa esattamente questo (`1288-1292`). I due
testi che parlano dell'utente in volo non dicono che il commander scarta:
`sweep_worker` (`commander.py:1783-1786`) e la docstring di modulo
(`commander.py:180-181`, «the move's own `moving` hold parks whatever arrives
for that user»). La fase 2 aveva lasciato aperta la seconda lettura — «l'issue
si riferiva a un quarto testo in `worker.py`, dove il *worker scarta* dovrebbe
essere documentato». **La fase 4 ha letto `worker.py` per intero e non lo ha
trovato**; una verifica diretta in fase 5 conferma che l'unico «discarded» di
`worker.py` vicino al tema è di un altro soggetto: `install_page`/`add_user`
dichiarano che *il blob* di un residente è scartato perché la copia viva è la
verità (`worker.py:2326-2328`), che è l'install-che-unisce, non un datachange in
volo.

**Delta**: la frase che l'issue vuole correggere **non esiste** nell'albero.
Tutte le docstring candidate sono coerenti col proprio codice.

**Opzioni**: (a) chiudere la voce come **superata** — il testo è stato allineato
da un lavoro precedente all'issue; (b) se il titolare ricorda un quinto testo,
la scheda si riapre nominandolo.

**Verdetto (2026-08-13, intervista col titolare): SUPERATA.** La frase da
correggere non esiste nell'albero (cercata in tre fasi indipendenti; tutte le
docstring candidate sono coerenti col proprio codice) — era con ogni
probabilità il ricordo di una versione precedente, già sistemata prima
dell'issue. Si riapre solo nominando il testo esatto.

---

## Sezione 5 — Affermazioni dell'ebook mai portate a scheda

Rilievo di consolidamento, non un rilievo nuovo: l'inventario di fase 1 ha
tagliato 36 affermazioni, di cui 25 con tag `spa-world`. La fase 4 le ha
verificate **tutte e 25** (18 confermate, 7 a scheda: R17-R23). Le altre **11**
portano i tag `recycling-code` e `tests`, che il piano assegnava alle fasi 2 e
3 — ma quelle due fasi hanno lavorato per punti di fedeltà e per esperimenti di
strip, e nessuna di esse cita un identificatore `E`/`B` (verificato in fase 5
con una ricerca sui due file). **Restano dunque non verificate**:

| # | Affermazione (sintesi) | Zona | Dove andrebbe verificata |
|---|------------------------|------|--------------------------|
| E2 | «il file di test più esercitato è quello dello spostamento: 119 casi» | tests | conteggio su `tests/test_spa_move.py` (la fase 3 ne ha misurati 121 test / 249 casi sui quattro file — il numero del libro non è stato confrontato) |
| E15 | saturazione per componente, non carico medio; chi va via è scelto in proporzione al consumo recente | recycling-code | `evaluator.py` + `rebalance_weights` |
| E16 | memoria di come cresce la memoria; sostituzione prima del tetto | recycling-code | è il tema di R5 e del ledger L2, ma la frase del libro non è stata confrontata |
| E17 | quando il carico cala il pool si restringe; un processo che tiene qualcosa non è mai ritirato | recycling-code | `compact_pass`, `pick_compaction_target` |
| E18 | sonda periodica: i numeri e la prova di vita; un processo muto è abbattuto e rilanciato | recycling-code | `probe_worker`, `caretaker` — collegata a R1 |
| E23 | il pavimento di memoria con la stima del limite è ciò su cui si fonda il ricambio | recycling-code | `evaluator.py:258-319` — collegata a R5, L2 |
| E24 | Roadmap: «Ricambio prima del limite — **operativo**» | recycling-code | la parola «operativo» va pesata contro R1-R4 |
| E25 | Roadmap: «Metriche Prometheus — in implementazione, le letture esistono» | recycling-code | `metrics_view` |
| B6 | «Riciclo su tempo-al-limite — Consolidato — issue #8 · 95%» | recycling-code | come E24 |
| B8 | «Soglie di occupazione come configurazione — Attivo con riserve — costanti PROVISIONAL in `evaluator.py:95` e `worker.py:366`» | recycling-code | due àncore numeriche da risolvere |
| B9 | conteggi dei test per capacità (47 / 60 / 119 casi) | tests | come E2 |

**Perché è qui e non nel ledger**: sono verifiche mancanti, non proposte. Due
di esse (E24, B6) chiedono di pesare la parola «operativo»/«Consolidato»
contro i quattro delta di fedeltà R1-R4, che è materiale da walkthrough e non
da esecuzione. **Opzioni**: (a) il titolare le dichiara fuori perimetro (il
libro sul riciclo si rigenererà dopo la run di fix); (b) diventano il perimetro
di una fase di verifica successiva.

**Verdetto (2026-08-13, intervista col titolare): triage completato in
intervista, nessuna resta cieca.**
- **Chiuse ora, verificate con misure fresche (4)**: E2 (il file dello
  spostamento è tuttora il più esercitato: 121 casi misurati vs 119), B9
  (51/60/121 vs 47/60/119 — commander esatto), B8 (le costanti PROVISIONAL
  esistono, àncore slittate di 1-2 righe; la «configurazione per gruppo»
  attesa è quella decisa oggi in R5), E25 (esatta alla lettera:
  `metrics_view` a commander.py:1919, nessuna traccia di formato Prometheus).
- **Superate dalle decisioni di oggi (4)**: E16, E23, E24, B6 — descrivono il
  ricambio fondato sulla previsione del tempo-al-limite, che R5 ha declassato
  a strumento: quei capitoli si riscrivono alla rigenerazione, non si
  verificano.
- **In coda alla run di fix (3)**: E15, E17, E18 — la sostanza regge anche nel
  disegno nuovo, ma le zone (riequilibrio, compattazione, sonda) vengono
  riscritte dal piano: la verifica alla lettera si fa sul codice nuovo, nella
  stessa passata che rigenera il libro.
**Regola di rigenerazione (dettata dal titolare)**: nella prosa i numeri
volatili si scrivono arrotondati — «oltre 120 test», mai «119 casi» — e le
cifre esatte vivono solo nelle tabelle di stato, rimisurate a ogni
rigenerazione.

---

## Conteggio

**24 voci, 24 in attesa di verdetto**: 6 di fedeltà (R1-R6) · 10 di battesimo
(R7-R16) · 7 di disaccordo col libro (R17-R23) · 1 di igiene (R24). Più una
sezione 5 di verifiche mancanti (11 affermazioni), che è una sola decisione di
perimetro.

## Scartate

Nessuna scheda delle fasi 2-4 è stata scartata da **questo** registro: tutte le
schede di fedeltà, battesimo e disaccordo col libro sono diventate voci
R1..R24. Le schede scartate della lente 2 (guardie necessarie, «tenere»
motivati, voci senza referente) sono elencate con la loro motivazione nella
sezione «Scartate» di `audit/slimming_ledger.md`, che è l'unico posto in cui
questa run dichiara un abbandono.

**24 voci, 24 in attesa di verdetto · 0 scartate in questo registro.**
