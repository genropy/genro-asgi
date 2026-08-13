# 00 — Le autorità: estrazione fedele

**Workflow**: wf#17 design audit · **Fase**: 1 · **Data**: 2026-08-13
**Stato**: materiale da walkthrough — nessun verdetto è dato qui.

Questo documento non giudica: **estrae**. Ogni affermazione porta le parole
testuali dell'autorità e la sua àncora. Le tre autorità sono:

| Sigla | Autorità | Come è stata letta |
|-------|----------|--------------------|
| **BRIEF** | `temp/wf8_recycling_design_brief.md` (2026-08-11, tutte le sezioni approvate) | file locale, àncora = `brief:<riga>` |
| **NOTES** | `.phased/done/8-process-recycling/notes.md` sul ramo `wf/8-process-recycling` | `git show wf/8-process-recycling:.phased/done/8-process-recycling/notes.md`, àncora = `notes:<riga>` |
| **EBOOK** | `docs/html/presentazione_2_stato_orchestrazione.html`, `docs/html/architettura_blocchi.html` | prosa estratta dall'HTML, mai dall'epub; àncora = titolo di sezione |

Zone di applicazione (tag usato in tutto l'audit):
`recycling-code` (commander.py, evaluator.py) · `tests` · `spa-world`
(worker + satelliti: worker.py, worker_entry.py, register.py,
register_registry.py, subscription_index.py, global_store.py, environ.py,
`__init__.py`).

---

## 1. Punti di fedeltà (lente 1)

I sei punti enumerati dall'issue #17. Per ciascuno: cosa dice l'autorità, con
le sue parole, e cosa è già noto dalla pianificazione. **Nessuna verdetto**: il
confronto col codice è la fase 2.

### F1 — Il task `planner` con `decision_interval` (300s) contro la terza forza del XOR
**Zona**: `recycling-code`

BRIEF, Q3a (brief:100-112), ratificato 2026-08-11 come **revisione dichiarata**
di wf#5 f8:

> «Pool-shape decisions (rebalance, recycling, compaction) leave the probe
> return and move to their own global periodic task, interval per-group
> config, default 5 minutes (the window duration). […] Probes stay at 5s for
> HEALTH only (mute worker → kill, stuck handover → kill). This revises the
> wf#5 f8 decision "the probe return IS the pool's heartbeat" — to be recorded
> as a declared revision in the plan. New kwarg (name to baptise):
> `decision_interval` · `beat_interval` · `pool_beat_interval`.»

BRIEF §7 battesimo (brief:271-272):

> «Plan machinery: `planner` (the periodic task, sibling of `caretaker`) ·
> roster field `"floors"` (next to `"occupancy"`).»

BRIEF §6 schizzo di fase (brief:245-247):

> «The decision tick: pool decisions leave the probe return (declared revision
> of wf#5 f8) for a periodic task […] `compacting`/`rebalancing` flags collapse
> into plan-in-flight.»

NOTES (notes:97-99) mette il punto esplicitamente fra quelli **da riconciliare
all'audit**:

> «Still to reconcile at the audit: the planner task with decision_interval
> (the brief SUPERSEDED the beat XOR with an ordered plan […])»

**Fatto noto dalla pianificazione (verificato 2026-08-13)**: `planner` e
`decision_interval` hanno **zero occorrenze** in `src/genro_asgi/` — assenze da
documentare, non da riscoprire. Ciò che vive oggi è il battito con le tre forze
a bandierina (`commander.py:590` «The beat's three forces, one flag each»).

### F2 — Il modello PLAN: una lettura → redistribuzione → sostituzioni dal peggiore → compattazione
**Zona**: `recycling-code`

BRIEF, Q3b (brief:114-136), ratificato 2026-08-11, **supersede la precedenza XOR**:

> «At each decision tick, if the previous plan has finished, the commander
> reads the WHOLE pool once — over-threshold workers, sick workers
> (time-to-limit under the horizon), spare headroom — and builds an ordered
> PLAN of steps from that single reading, then executes it sequentially. The
> plan as a whole is the one operation in flight; a tick landing mid-plan does
> nothing. Ratified step order:
>
>     rebalance (never onto condemned workers) → replacements (worst first,
>     possibly several, sequential) → compaction (last: only then is the
>     real headroom known)»

E la conseguenza meccanica (brief:134-136):

> «The XOR + per-force precedence proposal above is superseded; the
> `compacting`/`rebalancing` flags collapse into the single plan-in-flight
> state (mechanics at plan time).»

Ragione dichiarata per cui la latenza in minuti è accettabile (brief:105-109):
la soglia di ammissione è 0.8 **per disegno**, «the 20% margin absorbs a
minutes-scale wait».

NOTES (notes:99-101) conferma il punto come aperto:

> «the brief SUPERSEDED the beat XOR with an ordered plan: read once →
> redistribution → substitutions worst-first, possibly several → compaction»

### F3 — `designated_reception` per l'accoglienza condannata
**Zona**: `recycling-code`

BRIEF, Q4-bis (brief:151-166), ratificato 2026-08-11 come **revisione dichiarata**
del «positional, no flag and no election» di wf#5:

> «The one worker the abort-and-retry protection cannot recycle is the
> reception: guests keep landing on it, the drain never empties, and the most
> exposed worker would be the only unreplaceable one. Ratified: when the plan
> condemns THE RECEPTION, a fresh worker is spawned and the reception ROLE is
> assigned to it — a declared revision of the wf#5 "positional, no flag and no
> election" decision (a designation pointer on the commander, positional
> fallback when the designated one dies). The ex-reception keeps its existing
> sticky users (guests already aboard stay), only NEW arrivals go to the fresh
> reception; it then drains and retires through the standard replacement step
> — never abandoned with users aboard.»

Con un rifiuto esplicito (brief:163-166):

> «Evidence-triggered ONLY (time-to-limit condemns it): a periodic "every N
> hours" reception rotation was proposed and REJECTED as clockwork through the
> back door (the issue's rejected ceiling)»

BRIEF §7 battesimo (brief:269-270):

> «Commander state: `condemned_workers` (marked to die, until empty — distinct
> from the `draining` status, which fires with SIGTERM) ·
> `designated_reception` (pointer, None = positional rule).»

Ancore verificate dal BRIEF stesso (brief:176-179): «the reception is
positional, first active in spawn order (commander.py:586)».

**Fatto noto dalla pianificazione (verificato 2026-08-13)**:
`designated_reception` ha **zero occorrenze** in `src/genro_asgi/`; anche
`condemned_workers` ha zero occorrenze (il vocabolario che è arrivato al codice
è quello dell'evacuazione: `evacuating_since`, `evacuate_user`).

NOTES (notes:75) porta inoltre un vincolo collegato, deferito dal titolare:

> «GUESTS ARE RELOCATED TOO during an evacuation, if not expired, and their
> forced destination is the NEW reception (positional routing must stay true)
> […] PENDING: the worker has no guest-inventory op today»

### F4 — Spawn a libro mastro (`capacity_headroom`)
**Zona**: `recycling-code`

BRIEF, Q4 (brief:138-150), ratificato 2026-08-11:

> «The "spawn the replacement immediately" of the issue becomes ledger-gated:
> at plan build, `capacity_headroom()` says whether the pool can absorb the
> sick worker's users — if not, `scale(target + 1)` FIRST through the standard
> supervisor path (the fresh worker, being empty and least loaded, attracts the
> drained users naturally — the issue's original routing); if the room is
> there, no new process at all. Then drain (existing `drain_worker`) and
> `retire()`. Capacity never dips, no double moves, zero new machinery.»

Contro-decisione da tenere presente: NOTES (notes:11-13) ratifica in
walkthrough un **ordine diverso** sul flag:

> «THE SICK WORKER IS FLAGGED ONLY AFTER ITS SUCCESSOR REGISTERED: a
> replacement that never comes leaves it untouched, by construction — no
> rollback exists anywhere.»

I due testi non dicono la stessa cosa: il BRIEF ammette il caso «se lo spazio
c'è, nessun processo nuovo», le NOTES parlano di successore registrato come
precondizione. La riconciliazione è materiale da walkthrough.

**Fatto noto (2026-08-13)**: `capacity_headroom` ha 2 occorrenze in
`src/genro_asgi/`.

### F5 — `floor_series_depth` 48 (implementato 72); punti minimi di fit 3 (implementato 6, privato)
**Zona**: `recycling-code`

BRIEF, Q6 (brief:208-223), ratificato 2026-08-11:

> «Three new per-group kwargs on the commander (policy family of #5), never in
> the sensor, plain config like the existing ones:
> - Decision tick interval — default 5 minutes (the window duration).
> - Comfort horizon — default 12 hours (the issue's example): condemn when
>   time-to-limit drops under it.
> - Series depth K — default 48 points (one per 5-min window ≈ 4 hours of
>   evidence).
>
> Minimum 3 points before judging = MODULE CONSTANT, not a kwarg (a
> statistical-sanity floor, not an operational choice).»

BRIEF, Q2 (brief:97-98):

> «Minimum series length before judging (a 2-point fit is noise): proposal
> K_min = 3; below it T = ∞.»

BRIEF §7 battesimo (brief:262-267):

> «Kwargs: `decision_interval` (seconds between pool decisions, 300) ·
> `recycle_horizon_hours` (condemn when time-to-limit drops under it, 12) ·
> `floor_series_depth` (memory-floor points kept per worker, 48). Evaluator:
> `worker_floors` (the series […]) · `worker_floor_velocity` (bytes/hour,
> Theil–Sen) · `worker_time_to_limit` (hours, ∞ on flat/falling/no-limit).»

NOTES (notes:102-103) registra lo scarto:

> «floor_series_depth 48 (implemented: 72), fit minimum 3 points (implemented:
> 6, private constant).»

**Fatti noti (2026-08-13)**: `_FLOOR_FIT_MINIMUM = 6` a `evaluator.py:91`
(privato); `floor_series_depth` esiste come kwarg (`commander.py:464`) — il
confronto sul valore di default è fase 2.

### F6 — I nomi coniati durante la run e mai ratificati esplicitamente
**Zona**: `recycling-code`

BRIEF §2 di battesimo (brief:260-261) definisce il mandato con cui i nomi sono
stati scelti:

> «## 7. Baptism ✅ 2026-08-11 (owner delegated: "reasonable names for a reader
> who knows nothing")»

NOTES (notes:81-84) elenca i simboli coniati **dalla riscrittura, da ratificare**:

> «New symbols coined by the rewrite, to ratify: `advance_evacuations`,
> `evacuation_pass`, `evacuate_user` (the call-close carry),
> `warn_stalled_evacuation`, `regeneration_failed_at`, roster fields
> `evacuating_since` / `evacuation_warned_at`.»

NOTES (notes:109-114) elenca il **libro dei nomi della run**:

> «Naming ledger for the owner (new public symbols coined mid-run, all
> documented in the phases' own notes): `floor_slope(samples)` (Phase 2, the
> pure Theil-Sen fit the tests compare against), `wait_worker_ready(name)`
> (Phase 3 — the plan cited a `wait_workers_ready([name], ...)` signature that
> does not exist; the real one takes a count), `drain_order(worker)` (Phase 3,
> the idle-first tiering the order test asserts).»

E infine, dal panel di finalize (notes:169-171):

> «New symbols to ratify: RECYCLE_RETRY_SECONDS (300s PROVISIONAL),
> abandon_recycle, roster field recycle_failed_at.»

NOTES (notes:127-128) registra come i nomi siano rimasti in piedi:

> «names ledger unanswered = names stand.»

L'elenco operativo dei dieci nomi dell'issue #17 è la sezione 2.

---

## 2. Elenco di battesimo (i dieci nomi dell'issue)

Un nome per riga: dove sta (verificato 2026-08-13, àncora nel codice attuale) e
cosa ne dicono le autorità. **La semantica implementata e i candidati di
rinomina sono lavoro della fase 2**; qui c'è solo l'estrazione.

| # | Nome | Àncora (2026-08-13) | Cosa dicono le autorità |
|---|------|---------------------|-------------------------|
| 1 | `floor_slope(samples)` | `src/genro_asgi/spa/evaluator.py:258` | NOTES notes:110-112: «the pure Theil-Sen fit the tests compare against» — coniato in fase 2 della run, mai ratificato. Il BRIEF §7 non lo nomina: battezza solo `worker_floor_velocity` (brief:266). |
| 2 | `wait_worker_ready(name)` | `src/genro_asgi/spa/commander.py:3159` | NOTES notes:112-114: coniato perché «the plan cited a `wait_workers_ready([name], ...)` signature that does not exist; the real one takes a count». Nessuna autorità precedente lo nomina. Il panel di finalize lo tocca di nuovo (notes:167-168): «wait_worker_ready aborts at once on a dead/buried replacement». |
| 3 | `drain_order(worker)` | `src/genro_asgi/spa/commander.py:2947` | NOTES notes:113-114: «the idle-first tiering the order test asserts». Il BRIEF lo prefigura senza nome, in Q5 (brief:186-188): «users with empty `pending` move at once […] They go FIRST». |
| 4 | `advance_evacuations()` | `src/genro_asgi/spa/commander.py:3025` | NOTES notes:81-84: coniato dalla riscrittura, **da ratificare**. Semantica dichiarata in NOTES notes:56-57: «The beat's advance only retires the emptied and reports the stalled — it holds no flag». |
| 5 | `evacuation_pass(worker)` | `src/genro_asgi/spa/commander.py:3044` | NOTES notes:81-84: coniato dalla riscrittura, **da ratificare**. Corrisponde al punto 1 di Q5 del BRIEF (brief:186-188), la passata di apertura. |
| 6 | `evacuate_user(user, worker)` | `src/genro_asgi/spa/commander.py:2243` | NOTES notes:82: «(the call-close carry)». BRIEF Q5 punto 2 (brief:189-193): «in the existing `close_request` finally, one added check — pending emptied AND worker condemned → trigger that user's move». NOTES notes:53-55: «an active user is carried the instant his last call closes (close_request → evacuate_user)». |
| 7 | `warn_stalled_evacuation(worker)` | `src/genro_asgi/spa/commander.py:3073` | NOTES notes:83: coniato, da ratificare. Fondamento in NOTES notes:26-29: «a call that never closes while the user keeps pinging is the one genuine anomaly: reported (channel above), worker keeps serving it, a human decides». Il canale `_server/<nome>` è esso stesso **deferito** (notes:79: «the name is the owner's to baptise»). |
| 8 | `regeneration_failed_at` | `src/genro_asgi/spa/commander.py:596` (attributo), usato a 1132, 2118, 2996, 3140 | NOTES notes:83: coniato, da ratificare. Semantica in NOTES notes:16-21: «A REPLACEMENT THAT NEVER COMES IS A POOL HEALTH CONDITION […] it declares itself with a 503 TO THE NEW ENTRIES (residents keep being served), the condition clears at the first successful REGISTER, probes are paced by RECYCLE_RETRY_SECONDS». |
| 9 | roster `evacuating_since` | `src/genro_asgi/spa/commander.py:1006` (riga roster), documentato a 989 | NOTES notes:84: coniato, da ratificare. Docstring attuale (commander.py:989): «stamps the moment a recycling flags this worker». Nel BRIEF il concetto è `condemned_workers` (brief:269), stato del commander, non campo di riga. |
| 10 | roster `evacuation_warned_at` | `src/genro_asgi/spa/commander.py:1007` (riga roster), documentato a 992 | NOTES notes:84: coniato, da ratificare. Docstring attuale (commander.py:992): «throttles that report». |

Nomi collegati, coniati dopo il panel di finalize e mai ratificati
(NOTES notes:169-171) — non fanno parte dei dieci dell'issue ma appartengono
alla stessa famiglia e la fase 2 li incontrerà: `RECYCLE_RETRY_SECONDS`
(300s **PROVISIONAL**), `abandon_recycle`, campo roster `recycle_failed_at`.

---

## 3. Metodo (lente 2: essenzialità)

### Le tre domande dell'onere della prova
Ratificate nell'audit di essenzialità 2a (`temp/audit_essenzialita_2a_2026-08-01.md`)
e richiamate dall'issue #17:

1. **Chi lo ha postulato?** — quale autorità chiede questo pezzo. Se nessuna,
   è accrescimento.
2. **Cosa si rompe senza?** — con analisi dei chiamanti, non con un'opinione.
3. **C'è una strada più corta?** — «scritto oggi dalla storia ratificata,
   quante righe sarebbe?»

### Le quattro specie da cacciare (issue #17, lente 2)

| Specie | Definizione (parole dell'issue) | Fase che la caccia |
|--------|--------------------------------|--------------------|
| **1 — Difese per scenari impossibili** | «guards/fallbacks whose triggering condition no caller can produce. Verdict per finding: remove, or replace with a loud error (house rule: impossible cases explode, never handled in silence)» | Fase 2 (codice), verifica in fase 3 |
| **2 — I test che le cementano** | «a test asserting behaviour for an unreachable state makes its defense unremovable. The unit of removal is the PAIR (branch + test): strip the code, see which tests fall, and for each ask "does this scenario exist in the real product?"» | Fase 3 |
| **3 — Indirezione senza significato** | «one-line forwarding methods, layers that add a name but no concept, single-caller helpers» | Fasi 2 e 4 |
| **4 — Castelli di pezze contro la strada diretta** | «where behaviour is accretion (fix over fix, wf#8's five panel/fix spirals are the prime suspect: evacuations, floor series, replacements) […] "written today from the ratified story, how many lines would this be?"» | Fase 2 |

### La regola fondamentale che governa ogni proposta di snellimento
NOTES (notes:43-46), dettata dal titolare il 2026-08-12:

> «FUNDAMENTAL RULE (dictated, now in session memory too): never machinery for
> every possible case — weigh the probability (operation frequency x window
> width); if minuscule, ACCEPT the risk provided it ends in a LOUD ERROR, never
> silent corruption.»

Esempio dato dal titolare stesso (notes:64-66):

> «THE RESIDENT-JOIN RACE IS ACCEPTED (the owner's own example of the rule): no
> barrier — a delivery toward a worker that stopped serving fails loudly in
> hand_user_to, the client retries and lands right.»

### Confine invalicabile della run
Niente muore per difetto: ogni voce dei registri è una **proposta** con la
casella di verdetto vuota. La run si ferma alle schede.

---

## 4. Inventario delle affermazioni dell'ebook

Ogni affermazione verificabile che l'ebook fa sul mondo spa, con la sezione da
cui viene e la zona a cui si applica. La verifica è delle fasi 2 e 4.

### 4.1 Da «2 — Lo stato e l'orchestrazione»

| # | Affermazione (parole dell'ebook) | Sezione | Zona |
|---|----------------------------------|---------|------|
| E1 | «lo stato vivo si organizza su tre livelli annidati: l'utente possiede le sue connessioni, ogni connessione possiede le sue pagine, ogni pagina possiede il proprio albero di dati» | *La conseguenza* | spa-world |
| E2 | «il file di test più esercitato dell'intero progetto è quello che verifica lo spostamento: 119 casi» | *La trappola* / *Roadmap* | tests |
| E3 | «un solo scrittore per ogni fatto. Il processo possiede la verità delle sue pagine; il supervisore possiede la verità di chi-sta-dove. Nessuno scrive mai dentro il registro di un altro livello» | *Chi possiede quale verità* | spa-world |
| E4 | «Durante uno spostamento c'è un istante in cui la sessione è stata staccata dall'origine e non è ancora installata a destinazione. Se una richiesta arriva proprio allora, deve attendere, non fallire — e se l'installazione non riesce, l'utente deve restare dov'era» | *Il momento in cui l'utente non è da nessuna parte* | recycling-code / spa-world |
| E5 | «Serve una fase di quiete: si alza una barriera, si aspetta che le chiamate vive finiscano […] Con un tempo massimo» | *Le chiamate in volo* | spa-world |
| E6 | «prima l'utente, poi le connessioni, poi le pagine; e i collettori di modifiche vanno attaccati dopo che i dati sono stati reidratati» | *L'ordine della rinascita* | spa-world |
| E7 | «Va distinto un ritiro voluto da un crollo, rilanciato con un nome nuovo perché nessun messaggio in ritardo venga scambiato per il nuovo arrivato, e liberato tutto ciò che teneva — compresi i permessi di scrittura che aveva in mano» | *La morte di un processo* | spa-world |
| E8 | «la memoria che un processo dichiara non è quella che sta davvero usando» (misura onesta) | *Sapere quando intervenire* | spa-world |
| E9 | «In sviluppo tutto questo gira in un solo processo: il worker vive dentro il supervisore, attaccato allo stesso canale, che in quel caso è una coppia di code in memoria invece di un socket — ma codifica ogni messaggio esattamente allo stesso modo» | *Il piano SPA* | spa-world |
| E10 | «La consegna è a richiesta, non spinta: se una pagina tace, i suoi aggiornamenti l'aspettano nel collettore invece di perdersi» | *Lo stato vivo e la sua consegna* | spa-world |
| E11 | «Chi ha originato il cambiamento serve prima i propri, poi il resto viaggia: una modifica su una tabella che nessuno guarda non costa un solo invio» | *Lo stato vivo e la sua consegna* | spa-world |
| E12 | «Un valore memorizzato in una pagina porta il segno della tabella da cui viene; quando quella tabella cambia, il valore viene invalidato con una scrittura vera» | *Lo stato vivo e la sua consegna* | spa-world |
| E13 | «Un albero comune a tutti i processi, con un solo scrittore e una replica locale per ciascuno […] Le modifiche in lettura-e-scrittura passano da una concessione ordinata, tutto-o-niente, che viene rilasciata da sé se chi la teneva muore» | *Lo stato vivo e la sua consegna* | spa-world |
| E14 | «La mappa si aggiorna per ultima: finché l'installazione non è confermata, la persona continua a essere servita dove si trova, e se la destinazione muore le si offre un altro posto» | *Il governo dei processi* | recycling-code / spa-world |
| E15 | «Si osserva la saturazione per componente, non un carico medio: un processo oltre soglia su una sola risorsa cede utenti […] Chi va via viene scelto in proporzione a quanto ha consumato di recente» | *Il governo dei processi* | recycling-code |
| E16 | «Il sistema tiene memoria di come cresce la memoria di ogni processo e ne sostituisce uno prima che raggiunga il tetto, portando i suoi utenti su un processo fresco» | *Il governo dei processi* | recycling-code |
| E17 | «Quando il carico cala, il pool si restringe: si drena il processo meno carico e lo si ritira. Un processo che tiene ancora qualcosa non viene mai ritirato» | *Il governo dei processi* | recycling-code |
| E18 | «Una sonda periodica chiede a ogni processo i suoi numeri: la risposta porta i dati e la prova che il processo è ancora vivo […] un processo muto viene abbattuto e rilanciato» | *Il governo dei processi* | recycling-code |
| E19 | «Andando giù, il pool raccoglie ogni utente e lo scrive su file; risalendo, li ripiazza prima che qualcosa possa essere instradato» | *Il governo dei processi* | spa-world |
| E20 | «Il processo sa sintetizzare l'ambiente standard di un'applicazione WSGI e invocarla al proprio interno, su un pool di thread dedicato e separato da quello delle operazioni di servizio» | *Il ponte con l'esistente* | spa-world |
| E21 | «Una chiamata sola compone la popolazione viva: per ogni processo i suoi utenti, le sue connessioni, le sue pagine […] Un processo irraggiungibile non fa cadere la lettura: compare con il proprio stato di irraggiungibilità» | *Il ponte con l'esistente* | spa-world |
| E22 | «i registri contengono dati serializzabili per costruzione, mai oggetti vivi come verità» | *Lo stato di lavoro attraversa le versioni* | spa-world |
| E23 | «il pavimento di memoria con la stima di quando toccherà il limite, che è ciò su cui si fonda il ricambio programmato» | *Il pannello · I processi* | recycling-code |
| E24 | Roadmap: «Ricambio dei processi prima del limite di memoria — **operativo** — misura onesta della memoria, serie storica per processo» | *Roadmap* | recycling-code |
| E25 | Roadmap: «Metriche del pool in formato Prometheus — **in implementazione** — le letture esistono già […] manca la ripubblicazione nel formato standard» | *Roadmap* | recycling-code |
| E26 | Roadmap: «Gruppi e versioni conviventi — **in implementazione** — la colonna del gruppo è già presente in ogni registro» | *Roadmap* | spa-world |

### 4.2 Da «Architettura a blocchi»

| # | Affermazione | Sezione | Zona |
|---|--------------|---------|------|
| B1 | Conteggi di riga e copertura per modulo: `commander.py` 1209 righe 95%, `worker.py` 782 righe 95%, `register_registry.py` 146 · 100%, `evaluator.py` 124 · 100%, `global_store.py` 75 · 100%, `worker_entry.py` 69 · 72%, `register.py` 66 · 100%, `environ.py` 60 · 100%, `subscription_index.py` 44 · 100% | *11 · Piano SPA — orchestrazione* | spa-world + recycling-code |
| B2 | «Chiavi e posizioni sopra, contenuti sotto: i registri di superficie del commander sono dizionari piatti, deliberatamente non la macchina Register del worker» — e «otto registri piatti» | *11 · Piano SPA* | spa-world |
| B3 | «La mappa si scrive alla decisione. Un utente vive dove ha fatto login; il worker al login non spedisce nulla, annuncia soltanto» | *Zoom livello 2* | spa-world |
| B4 | «Il worker di una pagina si deriva risalendo pagina → connessione → utente → worker: nessun duplicato che possa divergere» | *Zoom livello 2* | spa-world |
| B5 | «Il ruolo «single» è configurazione, non una sottoclasse: `local_worker=True` costruisce un worker in questo stesso processo e lo attacca all'hub tramite LocalChannel» | *10* | spa-world |
| B6 | «Riciclo dei processi su tempo-al-limite — Consolidato — issue #8 · serie di pavimenti di memoria per worker · 95%» | *Stato delle capacità* | recycling-code |
| B7 | «Gruppi di worker — **Solo progettato** — esiste solo l'etichetta: un kwarg `group` di default "default" ricopiato in ogni riga del roster (`commander.py:445`, 990) e riletto solo dal log di sepoltura e dal monitor […] nessun test passa mai un valore diverso» | *Stato delle capacità* | spa-world |
| B8 | «Soglie di occupazione come configurazione — **Attivo con riserve** — costanti PROVISIONAL in `evaluator.py:95` e `worker.py:366`, in attesa della configurazione per gruppo» | *Stato delle capacità* | recycling-code |
| B9 | «Sensore di occupazione e valutatore — Consolidato — issue #4 · `test_spa_evaluator.py` (47) · 100%»; «Politiche del pool […] issue #5 · `test_spa_commander.py` (60) · 95%»; «Spostamento di un utente tra worker […] `test_spa_move.py` — 119 casi» | *Stato delle capacità* | tests |
| B10 | «Lo sweep delle scadenze disarmato. Non è codice incompleto: è codice che aspetta un'informazione» | *note finali* | spa-world |

**Nota per la fase 4**: le affermazioni B1 e B7-B9 sono numeriche e portano
àncore `file:riga` — quelle àncore vanno risolte contro l'albero attuale, e uno
scarto sui conteggi (già visibile: `commander.py` è oggi 3183 righe, `worker.py`
2350) è una scheda di disaccordo, non una correzione silenziosa.

---

## 5. Igiene già nota, da portare a scheda

Due voci registrate dall'issue #17 come «hygiene riding along». **Nessuna viene
corretta in questa run**: diventano schede.

### H1 — `LocalPool.settled` in `tests/test_spa_move.py`
L'issue dice: «`LocalPool.settled` in tests/test_spa_move.py still reads the
abolished None convention — dead helper, a trap for the next test».

Rilievo di fase 1 (2026-08-13): **nessun simbolo `LocalPool.settled` esiste**
nell'albero attuale. Quello che c'è è la funzione modulare `settled_at` a
`tests/test_spa_move.py:78`, viva e usata (≥ 9 chiamate), che legge
`commander.user_worker_map.get(user) == worker and not commander.is_held(user)`.
La classe `LocalPool` è a `tests/test_spa_move.py:149`. La fase 3 stabilisce se
la voce dell'issue si riferisce a un residuo già rimosso, a un altro helper, o a
una convenzione ancora presente — e la scheda dice quale delle tre.

### H2 — La docstring dello scambio in `commander.py`
L'issue dice: «The exchange docstring in commander.py (~1279) says the commander
discards an in-flight user's datachanges: it now ships them (the worker
discards). Align.»

Àncore di fase 1 (2026-08-13): `exchange_destinations` è a
`commander.py:1265`, la sua docstring occupa 1266-1273 e oggi parla di indirizzi
irrisolvibili («is dropped with a debug log: a change is a signal and there is no
retry queue»), non di utenti in trasferimento. Il testo che parla dell'utente in
volo sta altrove: `commander.py:1783` (`sweep_worker`: «This reaches a user
mid-move too — the map names the source until the switch») e la docstring di
modulo a `commander.py:180-190` («the move's own `moving` hold parks whatever
arrives for that user»). La fase 2 stabilisce quale testo l'issue intendesse e
scrive la scheda su quello.

---

## 6. Cosa questo documento NON fa

- Non dà verdetti: le colonne di verdetto dei registri (fase 5) restano vuote.
- Non confronta il codice con le autorità: è il lavoro delle fasi 2, 3 e 4.
- Non tocca una riga di sorgente o di test: l'intera run è di sola lettura,
  esperimenti di strip della fase 3 esclusi (transienti, sempre ripristinati).
