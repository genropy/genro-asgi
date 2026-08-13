# Registro 2 — Il libro mastro dello snellimento

**Workflow**: wf#17 design audit · **Fase**: 5 · **Data**: 2026-08-13
**Fonti**: `audit/zone_recycling_code.md` (schede D, I, C), `audit/zone_tests.md`
(esperimenti T-D, rassegna TS), `audit/zone_spa_world.md` (schede SD, SI),
`audit/00_authorities.md` (§3, il metodo). Nessun sorgente riletto qui: questo
registro **non aggiunge rilievi**, li fonde e li ordina.

**Cosa è questo documento**: l'ordine del giorno del walkthrough sullo
*snellimento*. Ogni voce porta **una proposta concreta** — togli X e il suo test
T, fondi Y in Z, riscrivi W in ~N righe — con l'àncora, le tre risposte
all'onere della prova (chi l'ha postulato · cosa si rompe senza · c'è una strada
più corta) e una casella **Verdetto: —** che questa run non riempie mai.

**Ordinamento**: per leva, la semplificazione più grossa prima. Le voci L14-L20
sono le più piccole del registro e stanno in fondo non perché contino meno, ma
perché ciascuna vale poche righe.

**Regola di casa su ogni voce di specie 1**: si **rimuove**, oppure si
sostituisce con un **errore rumoroso** — mai gestione silenziosa. **Regola
fondamentale** (NOTES notes:43-46, dettata dal titolare): mai meccanica per ogni
caso possibile; se la probabilità è infima si accetta il rischio purché finisca
in errore rumoroso, mai in corruzione silenziosa.

**Nulla muore per difetto**: nessuna voce è eseguita da questa run.

**Prova sperimentale disponibile**: sette difese sono state tolte per davvero in
fase 3 e la suite spa rieseguita senza `-x` (249 casi). Dove una voce porta
«test caduti: nessuno», è misurato, non argomentato.

---

## L1 ← C1 (+ N4, N7, D4) · L'evacuazione: tre porte per un solo comportamento
**Leva stimata**: ~102 righe di corpo → ~35. La voce più grossa del registro.

**Le pezze**: «svuota il worker condannato» è entrato da tre punti indipendenti,
ognuno con la sua storia — (1) la passata di apertura dentro `recycle_worker`
(`commander.py:3156` → `evacuation_pass`, 28 righe); (2) l'auto-consegna al
chiudersi di una chiamata (`close_request`, `commander.py:2240-2241` →
`evacuate_user`, 32 righe); (3) la contabilità per battito (`pool_beat`,
`commander.py:2658` → `advance_evacuations` 19 righe → `warn_stalled_evacuation`
23 righe). Più i due campi di riga (`commander.py:1006-1007`) e il paragrafo di
docstring che li spiega (`commander.py:989-992`).

**Chi l'ha postulato**: il BRIEF Q5 (brief:186-193) postula **due** tempi — gli
utenti con `pending` vuoto si spostano subito e vanno PRIMI; per gli altri «in
the existing `close_request` finally, one added check — pending emptied AND
worker condemned → trigger that user's move». **La terza porta (contabilità +
report di stallo) non viene dal BRIEF**: è cresciuta dal pannello di wf#8.

**Cosa si rompe senza la terza porta**: si perde il ritiro del worker rimasto
vuoto senza che nessuno chiuda una chiamata (oggi lo fa `advance_evacuations`,
`commander.py:3038-3041`) e si perde il WARNING di stallo. Il primo è
recuperabile (vedi L7); il secondo è una decisione di prodotto.

**C'è una strada più corta**: i due tempi del BRIEF sono ~35 righe in tutto
(passata sugli idle + il controllo in `close_request` + il ritiro a vuoto). Il
delta sta quasi tutto nel report di stallo e nella duplicazione L3/L7.

**Proposta**: decidere **prima** se il report di stallo è una voce di prodotto —
se sì resta, e andrà sul canale `_server/<nome>` quando esisterà (NOTES
notes:79), se no cadono con lui `warn_stalled_evacuation` (R13), il campo
`evacuation_warned_at` (R16), il ramo di L18 e il throttle di L4. Poi fondere
L3 e L7. **La decisione su questa voce ne muove altre cinque**: è la prima da
prendere al walkthrough.

**Verdetto (2026-08-13, intervista col titolare): scadenza che agisce, non
avviso che si lamenta.** Lo sgombero ha una scadenza: la riga porta già
l'istante d'inizio (campo ratificato — ha finalmente un consumatore vero); la
contabilità di battito, oltre a ritirare i vuoti, fa rispettare la scadenza.
Allo scadere, **migrazione forzata, non uccisione del processo**: la
richiesta lenta che bloccava il trasloco viene abbattuta (muore lei sola, con
errore rumoroso verso il chiamante), lo stato dell'utente si conserva e
viaggia con la consegna riordinata di R17; svuotato, il processo si ritira
per la via normale. Il WARNING di stallo cade con tutto il corredo:
`warn_stalled_evacuation` (R13), `evacuation_warned_at` (R16), la guardia di
L18, il terzo lavoro di `RECYCLE_RETRY_SECONDS` (L4) e l'orologio in prestito
`CONNECTION_MAX_AGE`; la scadenza prende una costante propria, battezzata
alla run di fix. La visibilità dello stallo passa alla fotografia del monitor
(R19: «in sgombero da quando, quanti utenti restano»). Le due porte del BRIEF
restano il nucleo; la forma finale (fusione L3/L7) si decide nelle voci di
forma.

## L2 ← C2 · La correzione di accelerazione sulla serie dei pavimenti
**Leva stimata**: ~45 righe → ~15.

**Le pezze**: la serie vive su quattro pezzi che non vengono da una sola
decisione — il contatore `floor_readings` che campiona una finestra su
`METRICS_WINDOW` (`commander.py:1895-1900`), la profondità 72 contro il 48 del
BRIEF (`commander.py:334`), il minimo di fit 6 contro 3 (`evaluator.py:91`), e —
**non chiesta da nessuna autorità** — la correzione di accelerazione in
`worker_floor_velocity` (`evaluator.py:294-298`): lo stesso fit rifatto sulla
metà recente, e vince il maggiore.

**Chi l'ha postulato**: **nessuno**. Il BRIEF §7 (brief:266) battezza
`worker_floor_velocity` come «bytes/hour, Theil–Sen», senza seconda passata; le
NOTES non la nominano; la sola ragione scritta è la docstring
(`evaluator.py:280-284`), che per la regola ratificata («design e review partono
dalle decisioni ratificate») non è un record di decisione.

**Cosa si rompe senza**: il tempo-al-limite diventa più lento a reagire a una
perdita che accelera — è precisamente ciò che la correzione compra, e va pesato,
non dedotto. Nessun test cade per la sola rimozione della seconda passata: il
test che tocca il ramo `None` della prima è quello di L20.

**C'è una strada più corta**: la storia ratificata è «Theil-Sen sulla serie,
T = (limite − ultimo pavimento) / velocità, ∞ se piatta o in discesa» — ~15
righe fra `floor_slope` e i suoi due lettori, contro ~45 oggi
(`evaluator.py:258-319`) più la costante privata.

**Proposta**: portare la correzione al walkthrough come voce a sé — **o si
ratifica ed entra nel BRIEF, o si toglie** — e nello stesso passaggio decidere i
due valori di R5 (48 vs 72, 3 vs 6) e la privatezza di `_FLOOR_FIT_MINIMUM`.
Sono la stessa serie: deciderli separatamente costa due walkthrough.

**Verdetto (2026-08-13, intervista col titolare): la voce si declassa con la
macchina che la ospita.** Il grilletto del ricambio diventa a misure del
momento (R5: necessità / convenienza / vuoto) e la previsione a curve resta
solo come strumento di osservazione del monitor: la correzione
d'accelerazione non decide più la vita di nessun processo. Se resti o cada è
un dettaglio dello strumento, da decidere alla run di fix insieme a
profondità e minimo — non più materia di ratifica.

## L3 ← I3 · `evacuation_pass` e `drain_worker`, cicli gemelli
**Leva stimata**: due cicli (23 + 28 righe) → uno.

**I due pezzi**: `drain_worker` (`commander.py:2923-2945`) e `evacuation_pass`
(`commander.py:3044-3071`) iterano entrambi `drain_order(worker)`, saltano chi
non è più sulla mappa, chiedono `pick_compaction_target`, chiamano `move_user`.

**Le differenze reali sono tre**: l'evacuazione **salta** chi ha chiamate
pendenti invece di attenderne il quiesce (`commander.py:3064-3065`), ricontrolla
lo stato a ogni giro (`commander.py:3060-3061`), e ritira il worker in coda; il
drenaggio torna un `bool` che il chiamante usa per decidere il ritiro
(`commander.py:2911-2916`).

**Chi l'ha postulato**: il BRIEF Q5 (brief:186-193) descrive **una** procedura di
svuotamento con due tempi, non due procedure.

**Cosa si rompe senza**: nulla di funzionale, se la politica sugli occupati
(«attendi» / «salta») diventa un parametro. Il rischio è di appiattire tre
concetti distinti in un solo metodo con tre `if`: è la domanda da porre al
walkthrough, non un fatto.

**Proposta**: un solo ciclo con politica sugli occupati, **oppure** la
constatazione motivata che le tre differenze sono concetti distinti e i due
metodi restano separati. Da decidere **dopo** L1, che può cambiare il numero di
chiamanti.

**Verdetto: —**

## L4 ← C3 · `RECYCLE_RETRY_SECONDS`: una costante, tre lavori
**Leva stimata**: ~12 righe con una costante contro il gruppo attuale, e un
numero PROVISIONAL che smette di governare cose scollegate.

**Il pezzo**: `RECYCLE_RETRY_SECONDS` (300s, dichiarata **PROVISIONAL** a
`commander.py:403`) governa tre cose diverse con lo stesso numero — (1) la
finestra del 503 ai nuovi ingressi (`commander.py:2119`); (2) il gate che
impedisce di ri-scegliere un candidato al riciclo (`commander.py:2997`); (3) il
throttle del WARNING di stallo dell'evacuazione (`commander.py:3087`), che non ha
nulla a che vedere con la rigenerazione. Sul fianco, la soglia di stallo è
`CONNECTION_MAX_AGE` (`commander.py:3084`), importata da `worker.py`
(`commander.py:292`): una terza costante di un altro modulo usata come orologio
dell'evacuazione.

**Chi l'ha postulato**: **nessuna autorità** nomina `RECYCLE_RETRY_SECONDS`; è
del pannello di finalize di wf#8 (NOTES notes:169-171), esplicitamente
**PROVISIONAL**. Il terzo uso è quello che tradisce l'accrescimento: la docstring
lo dichiara (`commander.py:3076`) ma il nome parla di riprovare un riciclo, non
di quante volte loggare.

**Cosa si rompe senza**: niente, se ogni lavoro prende il proprio numero. Il
throttle è il candidato naturale a sparire del tutto se il report va su un
canale invece che nel log (vedi L1).

**C'è una strada più corta**: la storia ratificata (NOTES notes:16-21) chiede
503 ai nuovi ingressi, residenti serviti, azzeramento al primo REGISTER, sonde
pacate: l'attributo, il timbro, il controllo in `worker_for` e il gate in
`recycle_candidate` — ~12 righe con **una** costante.

**Proposta**: separare le costanti per lavoro e battezzarle (R6 opzione b:
`RECYCLE_RETRY_SECONDS` non è nemmeno in `__all__`), **oppure** ratificare il
riuso dichiarandolo nel BRIEF.

**Verdetto: —**

## L5 ← I1 · I tre `trigger_*` gemelli
**Leva stimata**: 27 righe → ~8, o zero.

**Il pezzo**: `trigger_rebalance` (`commander.py:2687-2696`), `trigger_recycle`
(`commander.py:2698-2707`), `trigger_compaction` (`commander.py:2709-2718`):
tre metodi di 9 righe identici a meno del nome del flag e della coroutine —
guardia sul proprio flag, alza il flag, lancia la passata, riabbassa il flag se
il lancio esplode.

**Chi l'ha postulato**: nessuna autorità. La storia ratificata dice «una forza
per volta, un flag».

**Cosa si rompe senza**: le tre guardie interne sono **morte sul percorso di
produzione** — `pool_beat` (`commander.py:2660`, `2662`, `2664`) ha già letto
tutti e tre i flag due righe sopra (`commander.py:2656`) e ritorna se uno è
alzato. Sono vive solo per i test che chiamano il trigger due volte di seguito
(`tests/test_spa_move.py:1830-1831`, `1865-1866`): quei due test vanno riscritti
o cadono con la voce.

**C'è una strada più corta**: con lo stato di piano-in-volo del BRIEF (R2) i tre
metodi collassano in uno. Senza arrivare al piano, un solo metodo parametrico
(«alza questo flag, lancia questa passata») sono ~8 righe invece di 27; oppure
zero, alzando il flag dentro `pool_beat` — i tre `*_pass` già lo riabbassano nel
proprio `finally` (`commander.py:2769`, `3023`, `2921`).

**Proposta**: unificare in un metodo parametrico, **oppure** eliminarli alzando
il flag in `pool_beat`. Da decidere **dopo** R1/R2: se il piano si fa, la voce
si risolve da sé.

**Verdetto (2026-08-13, intervista col titolare): si risolve con R1/R2 — i
tre `trigger_*` cadono col piano.** Lo stato piano-in-volo sostituisce i tre
flag e non c'è più nulla da innescare uno per uno; i due test che chiamano i
trigger due volte di seguito si riscrivono sul piano.

## L6 ← SD4 · I due `except Exception` sui batch discendenti
**Leva stimata**: −4 righe e una duplicazione, a comportamento invariato.

**Il pezzo**: `apply_datachange_in` (`worker.py:1339-1342`) e `apply_dbevents_in`
(`worker.py:1716-1719`) avvolgono l'intero batch in un `except Exception` con
`logger.exception`. **Nessuno dei due gestori è eseguito dalla suite**
(`worker.py:1341-1342`, `1718-1719`, colonna `Missing` di coverage misurata in
fase 4).

**Chi l'ha postulato**: nessuna autorità; le due docstring non li motivano —
dicono perché il lavoro è fuori dal loop, non perché l'errore va inghiottito.

**Cosa si rompe senza**: l'eccezione morirebbe nel task creato da
`spawn_service` (`worker.py:704-713`) — un task il cui errore non viene mai
recuperato, cioè un warning di asyncio invece di un log. È la ragione
strutturale per cui la via CALL ha `guarded_service`: le due vie EVENT non hanno
un equivalente, e questi due `except` ne fanno le veci.

**C'è una strada più corta**: sì — **una** guardia in `spawn_service` al posto
di due `except` identici in due punti, che è anche il modo in cui la via CALL è
già fatta.

**Proposta**: spostare la guardia in `spawn_service` (una sola, per tutte le vie
discendenti) e togliere i due `try/except`. Nessun comportamento cambia.

**Verdetto: —**

## L7 ← I2 · Il ritiro-a-vuoto scritto in due posti
**Leva stimata**: una riga di log e una condizione in meno, in un punto invece
di due.

**Il pezzo**: `advance_evacuations` (`commander.py:3038-3041`) e la coda di
`evacuation_pass` (`commander.py:3069-3071`) fanno la stessa cosa con la stessa
riga di log — «Evacuation of %s complete: retired» — su condizioni scritte in
modo diverso: `not entry["users"]` contro `not self.users_on(worker)`, che è la
stessa lettura passando da un set (`commander.py:1793-1795`).

**Chi l'ha postulato**: nessuna autorità; è la conseguenza delle tre porte di L1.

**Cosa si rompe senza**: togliendo il ritiro dalla passata di apertura, il
ritiro slitta al battito successivo — cioè di un intervallo di sonda. Togliendolo
dal battito, un worker svuotato dal solo `close_request` non verrebbe mai
ritirato: **quel ramo va tenuto**.

**C'è una strada più corta**: un solo `retire_if_empty(worker)` chiamato dai due
punti; o il solo ritiro dal battito, accettando il ritardo.

**Proposta**: `retire_if_empty(worker)` unico, **oppure** ritiro solo dal
battito. Dipendente da L1 e L3.

**Verdetto: —**

## L8 ← SD2 · La REPLY perduta senza rumore
**Leva stimata**: −3 righe, e un silenzio che diventa un log.

**Il pezzo**: `WorkerChannelClient.send_frame` (`worker.py:456-464`) inghiotte
`BrokenPipeError`/`ConnectionResetError` con un log di debug e **restituisce
l'id come se avesse spedito** (`worker.py:461-464`, righe non eseguite dalla
suite).

**Chi l'ha postulato**: nessuna autorità. La classe esiste perché
`channel/client.py` è ratificato intoccabile e una REPLY riusa l'id della CALL
(`worker.py:446-454`).

**Cosa si rompe senza**: niente — l'eccezione risalirebbe a `guarded_service`
(`worker.py:715-725`), che la registra con `logger.exception`, cioè esattamente
il comportamento rumoroso che la regola di casa chiede, **già presente e già
motivato** («a REPLY the dropped channel refused, past `answer_call`'s own catch
— is logged here»).

**C'è una strada più corta**: sì, tre righe in meno. Il `raise ConnectionError`
di `worker.py:458-459` resta: è il caso «non connesso», diverso.

**Proposta**: rimuovere il `try/except` di `worker.py:460-464` e lasciar salire
l'errore fino alla guardia che già esiste.

**Verdetto: —**

## L9 ← SI1 · `Outbox.ping_now`: nessun lettore in produzione
**Leva stimata**: una proprietà e una riga di test.

**Il pezzo**: la proprietà `ping_now` (`worker.py:440-443`), «True when there is
something to drain».

**Chi l'ha postulato**: nessuna autorità.

**Cosa si rompe senza**: niente in `src/` — **nessun chiamante**. L'unico lettore
è `tests/test_spa_worker.py:190`. Il contatore vero (`pending()`,
`worker.py:435-438`) ha invece un lettore reale, `occupancy_report`
(`worker.py:1019`).

**C'è una strada più corta**: `pending() > 0`, che è ciò che la proprietà fa.

**Proposta**: rimuovere la **coppia** — proprietà + la riga di test che la
asserisce. È il caso più puro di indirezione senza significato del registro: un
nome che non aggiunge niente e che nessun produttore consulta.

**Verdetto: —**

## L10 ← SI3 · Il kwarg `channel` del costruttore del worker
**Leva stimata**: un kwarg pubblico e due righe.

**Il pezzo**: `UserStickyWorker.__init__` accetta `channel` (`worker.py:479`,
documentato a `490`) e lo aggancia in coda (`worker.py:553-554`). La riga 554
**non è mai eseguita** dalla suite.

**Chi l'ha postulato**: nessuna autorità, e — al contrario dei tre inoltri di
`RegisterRegistry` (vedi Scartate, SI2) — **nessuna docstring lo dichiara seam**:
è nato come comodità.

**Cosa si rompe senza**: niente. Entrambe le vie reali di costruzione passano da
`attach_channel` — il processo figlio (`worker_entry.py:118-119`) e il worker
in-process (`commander.py:1060-1061`) — e `attach_channel`
(`worker.py:624-628`) fa esattamente il lavoro.

**Proposta**: rimuovere il kwarg e le sue due righe, **oppure** dichiararlo seam
di estensione come i tre di `RegisterRegistry` (ma allora la docstring deve
dirlo).

**Verdetto: —**

## L11 ← SD1 · I tre idiomi diversi per lo stesso salto tacito
**Leva stimata**: tre varianti → una; nessuna riga guadagnata, molta
leggibilità.

**Il pezzo**: nei tre camminamenti di `monitor_state` ogni riga letta è
ricontrollata e saltata se sparita — `worker.py:941-943` (utenti),
`worker.py:965-966` (connessioni), `worker.py:981-983` (pagine) — con tre
scritture diverse. Il quarto controllo (`worker.py:947-949`) è di natura
**diversa**: è un arco pendente (`connections` che nomina una connessione già
demolita), non una riga mancante, e va giudicato a parte.

**Chi l'ha postulato**: nessuna autorità esterna; la docstring
(`worker.py:893-899`) motiva il disegno — fotografia senza `dispatch_lock`, «a
row swept while it is taken is simply not in it».

**Cosa si rompe senza**: le due `continue` di utenti e pagine
(`worker.py:943`, `983`) **non sono mai eseguite** dalla suite; quella delle
connessioni (`worker.py:966`) sì. Togliere la tolleranza del tutto richiederebbe
il `dispatch_lock` per la fotografia, e il costo è dichiarato: il lock è tenuto
da passate lunghe (un pacco di move, un batch discendente intero) e la
fotografia è un poll.

**C'è una strada più corta**: sì, ma non è togliere — è **uniformare**: un solo
idioma per i tre camminamenti (quello delle connessioni, l'unico esercitato).

**Proposta**: uniformare i tre salti a un idioma, e decidere se il salto resta
silenzioso o produce una riga di debug. La fase 3 ha dimostrato, su un caso
gemello (L18), che il silenzio non prova niente.

**Verdetto: —**

## L12 ← SD3 · `grant_global_lock`: due mezze difese in una condizione
**Leva stimata**: mezza condizione.

**Il pezzo**: `grant_global_lock` (`worker.py:1814-1827`) scarta la concessione
quando `future is None or future.done()` (`worker.py:1822`); il ramo di scarto
(`worker.py:1823-1826`) non è mai eseguito.

**Chi l'ha postulato**: nessuna autorità; la docstring dichiara il caso («the
acquire was cancelled»).

**Cosa si rompe senza**: il ramo `is None` è **raggiungibile per costruzione** —
`acquire_global_lock` cancella la propria voce nel `finally`
(`worker.py:1788-1789`), quindi una concessione che arriva dopo una cancellazione
trova la mappa vuota, e il silenzio è giusto (il commander rilascerà da sé alla
morte del canale). Il secondo ramo, `future.done()`, richiede una voce ancora
registrata con un futuro già risolto: non esiste finestra in cui accada, perché
l'unico `set_result` è qui e la voce muore subito dopo.

**Proposta**: tenere `is None`, togliere `or future.done()` — oppure trasformare
quel solo caso in errore rumoroso. Due mezze difese in una condizione sola sono
ciò che rende impossibile dire quale delle due serve.

**Verdetto: —**

## L13 ← SD5 · `cpu_fraction`: il confronto d'orologio e la metà impossibile
**Leva stimata**: mezza condizione, più una decisione sul silenzio.

**Il pezzo**: `cpu_fraction` (`worker.py:1028-1043`) esce con `None` se
`previous_ts is None or previous_used is None or now <= previous_ts`
(`worker.py:1041`).

**Chi l'ha postulato**: nessuna autorità; la docstring motiva solo il primo caso
(«None on the first call»).

**Cosa si rompe senza**: `previous_used is None` è **impossibile per
costruzione** — i due campi sono assegnati insieme (`worker.py:1040`), quindi la
seconda metà della congiunzione non può essere vera senza la prima. `now <
previous_ts` è impossibile (`time.monotonic()` non torna indietro), ma
`now == previous_ts` è **possibile** su due sonde nello stesso tick, e senza la
difesa sarebbe una `ZeroDivisionError`: scenario improbabile che finisce in
errore rumoroso — ammesso dalla regola fondamentale, ma non è la scelta fatta
qui.

**Proposta**: togliere `previous_used is None` (impossibile), e decidere se
`now <= previous_ts` resta un `None` silenzioso o diventa un errore. Il valore in
gioco è una frazione di CPU che il valutatore legge: un `None` in più è già un
caso previsto a monte.

**Verdetto: —**

## L14 ← D3 + T-D3 · `recycle_worker`: la guardia sul worker inesistente
**Leva stimata**: 3 righe → 1, stesso errore.

**Il pezzo**: `commander.py:3127-3129` — `entry = self.worker_roster.get(name)`
seguita da `if entry is None: raise KeyError(...)`.

**Chi l'ha postulato**: nessuna autorità.

**Cosa si rompe senza**: **niente — misurato**. Esperimento di fase 3: le tre
righe sostituite da `entry = self.worker_roster[name]`, **249/249 test spa
passati, nessun test caduto**. In produzione il nome viene dal roster e la
sepoltura di una riga avviene `TOMBSTONE_SECONDS` (3600s, `commander.py:363`)
dopo la morte: la riga non può sparire fra scelta e uso. Nessun test chiama
`recycle_worker` con un nome ignoto. Cambia solo il messaggio — da «no such
worker to recycle: 'X'» a un `KeyError` nudo — e nessuna asserzione lo legge.

**C'è una strada più corta**: l'indicizzazione diretta, pattern già in uso nel
modulo (`commander.py:3176`, `2953`).

**Proposta**: `self.worker_roster[name]`. **Nessun test da toccare.**

**Verdetto: —**

## L15 ← D2 + T-D2 · `recycle_worker`: la guardia sullo stato non-`active`
**Leva stimata**: 2 righe. **La voce a costo zero del registro.**

**Il pezzo**: `commander.py:3132-3133` — `if entry["status"] != "active": raise
ValueError(...)`.

**Chi l'ha postulato**: nessuna autorità.

**Cosa si rompe senza**: **niente — misurato**. Esperimento di fase 3: guardia
tolta, **249/249 passati, nessun test caduto**. Doppia conferma: fra la scelta
(`commander.py:3018`) e il controllo (`commander.py:3132`) non c'è `await` — sono
nella stessa coroutine — e `recycle_candidate` itera su `active_workers`
(`commander.py:3000`). Gli otto chiamanti di test
(`tests/test_spa_move.py:2184`, `2207`, `2233`, `2467`, `2503`, `2517`, `2543`,
`2677`) passano tutti un worker `active` o il worker in-process.

**Proposta**: rimozione secca delle due righe. **Nessun test da rimuovere.**

**Verdetto: —**

## L16 ← D5 + T-D5 · `worker_time_to_limit`: il default `or []`
**Leva stimata**: 5 caratteri, e una falsa promessa in meno.

**Il pezzo**: `evaluator.py:318` — `list(series or [])[-1]["floor"]`.

**Chi l'ha postulato**: nessuna autorità.

**Cosa si rompe senza**: **niente — misurato**. Esperimento di fase 3:
`list(series)[-1]["floor"]`, **249/249 passati**. Il ramo è irraggiungibile: tre
righe sopra (`evaluator.py:314-316`) la velocità è già `not None`, e la velocità
è `None` per costruzione quando la serie è vuota o più corta di
`_FLOOR_FIT_MINIMUM` (`evaluator.py:288`). E il default **non difende nulla**: su
lista vuota `[-1]` alza `IndexError` comunque. Otto chiamanti nella suite
(`tests/test_spa_evaluator.py:472`, `479`, `481`, `490`, `505`, `512`, `523`;
`tests/test_spa_move.py:2357`) e nessuno arriva alla riga con una serie falsa; il
test del monitor senza serie (`tests/test_spa_monitor.py:248-254`) si ferma allo
stesso gate.

**Proposta**: togliere `or []`. **Nessun test da toccare.**

**Verdetto: —**

## L17 ← D6 + T-D6 · `install_in_custody`: il controllo di tipo sulla risposta
**Leva stimata**: mezza condizione.

**Il pezzo**: `commander.py:2591` — `if isinstance(answer, dict) and
answer.get("joined"):`.

**Chi l'ha postulato**: nessuna autorità.

**Cosa si rompe senza**: **niente — misurato**. Esperimento di fase 3:
`if answer.get("joined"):`, **249/249 passati**. `answer` viene solo da
`hand_user_to` (`commander.py:2580`), che restituisce `unwrap_reply` di
`/op/add_user`, e il worker risponde **sempre** con un dict — `return
{**self.wire_entry(entry), "joined": joined}` (`worker.py:2350`). L'unico test
che passa da `install_in_custody` (`tests/test_spa_move.py:672`) riceve un dict
vero.

**Proposta**: togliere `isinstance(answer, dict) and`. Una risposta di forma
sbagliata alzerebbe un `AttributeError` naturale, che è il rumore che la regola
di casa chiede. **Nessun test da rimuovere.**

**Verdetto: —**

## L18 ← D4 + T-D4 · `warn_stalled_evacuation`: il timbro assente
**Leva stimata**: mezza condizione — e la voce che ha insegnato il metodo.

**Il pezzo**: `commander.py:3084` — `if since is None or now - since <
CONNECTION_MAX_AGE: return`, dove `since = entry["evacuating_since"]`.

**Chi l'ha postulato**: nessuna autorità.

**Cosa si rompe senza**: **niente — misurato, e misurato in modo rumoroso**. La
fase 3 non ha tolto il ramo (un `return` rimosso non prova nulla: la suite passa
comunque): l'ha **trasformato in `AssertionError`**, così che qualunque test lo
percorresse esplodesse. **249/249 passati: il ramo non è mai percorso.** Il
metodo è chiamato solo su righe `evacuating` (`commander.py:3036-3042`), e stato
e timbro sono scritti in due righe consecutive senza `await`
(`commander.py:3153-3154`); non esiste altro scrittore di `evacuating`. L'unico
test che esercita il metodo per intero, `test_a_stalled_evacuation_is_reported`
(`tests/test_spa_move.py:2703-2715`), **scrive il timbro esplicitamente**
(`tests/test_spa_move.py:2713`): cementa il confronto temporale, non il ramo
`None`.

**Proposta**: togliere `since is None or` (una riga `evacuating` senza timbro non
esiste), **oppure** renderlo errore rumoroso — che è ciò che l'esperimento ha
temporaneamente fatto senza rompere nulla. **Nessun test da rimuovere.**
Dipendente da L1: se il report di stallo cade, la voce cade con lui.

**Verdetto (2026-08-13, intervista col titolare): cade con L1.** Il metodo
che conteneva la guardia sparisce con l'intero corredo del WARNING; il
controllo di scadenza che lo sostituisce legge il timestamp scritto in coppia
con lo stato, senza guardia sul `None` (una riga in sgombero senza timbro non
esiste).

## L19 ← D1 + T-D1 · `recycle_worker`: la guardia sul worker in-process
**Leva stimata**: due righe in un posto o nell'altro — **mai in entrambi**.

**Il pezzo**: due controlli per lo stesso fatto — `commander.py:3130-3131` (`if
self.worker is not None and name == self.worker.name: raise ValueError`) e lo
skip nel selettore, `commander.py:3001-3002`.

**Chi l'ha postulato**: nessuna autorità. È già un errore rumoroso, quindi la
regola di casa è soddisfatta: la domanda è se il fatto valga **due** posti da
mantenere.

**Cosa si rompe senza**: **un test, e solo metà — misurato**. Esperimento di fase
3: tolta la `ValueError`, cade
`tests/test_spa_move.py::test_the_in_process_worker_is_never_recycled`
(`tests/test_spa_move.py:2455-2467`), e ne cade **la seconda metà**: il test è
per metà cammino reale (il selettore salta, asserito a
`tests/test_spa_move.py:2465`) e per metà contratto del metodo pubblico (il
rifiuto diretto, `2466-2467`). In produzione l'unico chiamante è `recycle_pass`
(`commander.py:3021`), che passa l'esito di `recycle_candidate()`, il quale salta
già il worker in-process.

**Proposta, con il suo prezzo esplicito**: (a) tenere la `ValueError` come
contratto pubblico e togliere lo skip nel selettore → cade l'asserzione
`recycle_candidate() == "W:w-2"`; (b) tenere lo skip e togliere la `ValueError` →
cadono le due righe `tests/test_spa_move.py:2466-2467`. **Le due opzioni costano
ciascuna metà dello stesso test, mai entrambe.**

**Verdetto: —**

## L20 ← D7 + T-D7 (+ TS3) · `worker_floor_velocity`: velocità nulla sulla serie intera
**Leva stimata**: nessuna riga. **Questa voce non ha un'opzione «rimuovi».**

**Il pezzo**: `evaluator.py:292-293` — `if velocity is None: return None`.

**Chi l'ha postulato**: nessuna autorità.

**Cosa si rompe senza**: la fase 3 ha sostituito il `return` con un
`AssertionError` e **un test è esploso**:
`test_floor_velocity_is_none_when_no_pair_is_separated_in_time`
(`tests/test_spa_evaluator.py:515-523`), che scrive **otto campioni con lo stesso
identico `ts`** (`tests/test_spa_evaluator.py:518-521`: `now = time.time()` letto
una volta e riusato). In produzione i campioni sono aggiunti uno per finestra
chiusa, con una `time.time()` per campione (`commander.py:1900`): otto letture
identiche a distanza di una finestra l'una dall'altra. **Natura del test**: è un
test *della funzione*, non *dello scenario* — asserisce un'invariante matematica
di `floor_slope`, non un evento del prodotto. È l'unico test dei quattro file la
cui premessa non è costruibile dal prodotto (rilievo TS3).

**Perché non c'è l'opzione «togli il ramo»**: senza il `return None`,
`max(velocity, accelerated)` a `evaluator.py:298` confronterebbe `None` con un
`float` e alzerebbe `TypeError` — errore rumoroso, ma tre righe più in là della
causa. **Il fix di questa voce non è eseguibile come rimozione.**

**Proposta**: **tenere** (e la voce esce dal ledger), **oppure** rendere il ramo
rumoroso qui — e allora la coppia da riscrivere è `evaluator.py:292-293` + quel
test, che diventa un `pytest.raises`. Da decidere insieme a L2: se la correzione
di accelerazione cade, `max(...)` sparisce e con lui il vincolo.

**Verdetto (2026-08-13, intervista col titolare): segue la sorte di L2 alla
run di fix.** Con la previsione declassata a strumento di osservazione, il
ramo e il suo test non sono più materia di walkthrough: si sistemano insieme
alla forma finale dello strumento.

## L21 ← I5 · I due `wait_*_ready`: concetti distinti, corpi duplicati
**Leva stimata**: un corpo di attesa invece di due.

**Il pezzo**: `wait_workers_ready(count)` (`commander.py:795-808`) e
`wait_worker_ready(name)` (`commander.py:3159-3183`): due attese a polling con lo
stesso schema — deadline sul loop, `sleep(0.02)`, `TimeoutError` — su predicati
diversi.

**Chi l'ha postulato**: nessuna autorità. Il **concetto** è distinto e resta
(R8): uno conta i worker, l'altro attende il proprio rimpiazzo.

**Cosa si rompe senza**: niente, se il corpo comune diventa
`wait_until(predicate, timeout)`. La guardia `commander.py:3177-3178` (che alza
subito su una riga già `dead`) deve sopravvivere: è **cementata** da
`test_the_wait_aborts_at_once_on_a_replacement_already_dead`
(`tests/test_spa_move.py:2549-2558`), che ne misura anche il tempo (< 1.0s contro
i 30s di `READY_TIMEOUT`), ed è la premessa di una delle guardie necessarie
(vedi Scartate, D8).

**Proposta**: estrarre `wait_until(predicate, timeout)` e tenere i due nomi come
involucri, **oppure** lasciare i due corpi. Dipende da quanta infrastruttura
generica il titolare vuole in questo modulo.

**Verdetto: —**

---

## Conteggio

**21 voci, 21 in attesa di verdetto.** Fondono 29 schede delle fasi 2-4:
7 difese specie-1 con i loro 7 esperimenti di strip (D1-D7 + T-D1..T-D7,
diventate L14-L20), 4 indirezioni del commander (I1, I2, I3, I5), 3 castelli di
pezze (C1-C3), 5 difese del mondo spa (SD1-SD5), 2 indirezioni del mondo spa
(SI1, SI3), più il rilievo di rassegna TS3, che confluisce in L20.

**Esito quantitativo della lente 2**: su sette difese specie-1 misurate,
**cinque sono completamente incementate** — L14, L15, L16, L17, L18: nessun test
cade — e due hanno un test ciascuna (L19, L20), in entrambi i casi un test che
costruisce a mano uno scenario che il prodotto non produce.

**Ordine di decisione suggerito** (dipendenze, non priorità): L1 prima di tutto
(muove L3, L7, L18, L4 e le voci di battesimo R13/R16); L2 insieme a R5 e prima
di L20; R1/R2 prima di L5.

---

## Scartate

Le otto schede delle fasi 2-4 che **non** diventano voci di registro, ognuna con
la sua motivazione. Questo è l'unico posto in cui questa run dichiara un
abbandono: nessuna scheda è caduta in silenzio.

| Scheda | Dove | Perché è scartata |
|--------|------|-------------------|
| **D8** (`zone_recycling_code.md`) | 6 guardie di `commander.py`: `3138`, `3148-3152`, `3060-3061` e `3069`, `3064`, `2265-2266`, `2967-2968` | **Verificate NECESSARIE** con analisi dei chiamanti: ciascuna sta a valle di un `await` reale (`commander.py:3136`→`3148`, `move_user` a `3067`) o di un default davvero raggiungibile (`3064`, dopo che `drain_order` ha fotografato i nomi; `2265-2266`, perché `move_user` torna `False` anche per un utente spazzato mid-move; `2967-2968`, quando tutti i candidati sono oltre il gate). La scheda esiste per **impedire** che la simmetria con L14-L20 le porti via. |
| **Sezione B** (`zone_tests.md`) | le stesse 6 guardie, lato test | Registra che gli esperimenti di strip **non sono stati fatti** su di esse per decisione di fase 2: toglierle non produce «quali test cadono», produce una gara persa. Nessuna di esse è stata toccata. |
| **I4** — `worker_threshold` | `commander.py:2666-2672` | **Tenere**: due chiamanti (`rebalance_excess` `commander.py:2682`, `pick_rebalance_target` `2785`) e un concetto vero — l'asimmetria dell'accoglienza — che senza il metodo andrebbe ripetuto in entrambi. Registrata per completezza della caccia. |
| **SI2** — i tre inoltri di `RegisterRegistry` | `register_registry.py:157-168`, `170-177`, `436-438` | **Nessuna rimozione proposta**: la docstring del modulo li dichiara **seam di estensione** («The extension seam», `register_registry.py:48-54`), API per un consumatore che non vive in questo repo (genropy-asgi). Nessun chiamante in `src/` è la conseguenza attesa del disegno, non un sintomo. Se il titolare confermasse la seam, la voce muore qui — e questa riga è la sua motivazione. |
| **SI4** — `holds_target` | `worker.py:1306-1308` | **Tenere**: due chiamanti (`worker.py:1282` nello switch, `1348` nel batch discendente) e un nome che dice il concetto («questo worker tiene il destinatario?») nei due soli punti che decidono su di esso. Registrata perché il caso risulti **guardato e archiviato**, non dimenticato. |
| **TS1** — i test di contratto sugli errori rumorosi del fold | `tests/test_spa_commander.py:393-398`, `401-404`, `407-410` | **Non sono specie 2**: sono la faccia-test della regola di casa — il ramo che cementano non è una difesa da togliere, è l'**assenza** di difesa resa visibile. Se domani qualcuno aggiungesse un `.get(..., set())` di comodo, questi tre test cadrebbero: è il loro mestiere. |
| **TS2** — i test «unknown worker / unknown user» degli osservatori | `tests/test_spa_evaluator.py:341`, `416`; `tests/test_spa_commander.py:926`, `690` | Il ramo difeso è **raggiungibile per davvero**: sono osservatori interrogati da superfici esterne (`metrics_view`, `monitor_state`) su nomi che possono spegnersi fra la fotografia e la lettura — finestra documentata da `tests/test_spa_monitor.py:130`. Registrati per chiudere la rassegna in modo esplicito: non è vero che ogni ramo `None` sia una difesa da togliere. |
| **Sezione C** — `LocalPool.settled` (voce dell'issue #17) | `tests/test_spa_move.py` | **La voce non ha un referente nell'albero.** `LocalPool` (`tests/test_spa_move.py:149-189`) non ha `settled`; il vivo `settled_at` (`78-87`) ha **16 chiamanti** e non è codice morto; la convenzione `None` non è abolita — `new_roster_row` la ammette ancora nella firma (`commander.py:976`) e il commander la legge a `1089`, `1136`, `863`. Terza conferma indipendente (fasi 1, 3, 5). Si riapre in un colpo solo se il titolare ricorda quale simbolo aveva in mente. |

**Totale schede rendicontate**: 29 nelle 21 voci di questo registro + 8 qui
scartate = 37 della lente 2 e dell'igiene di specie 1. Le altre 24 schede delle
fasi 2-4 (fedeltà, battesimo, disaccordi col libro, igiene H2) sono voci
R1..R24 di `audit/reconciliation_record.md`. **Nessuna scheda resta fuori dai due
registri.**
