# Zona 3 — Il mondo spa contro l'ebook

**Workflow**: wf#17 design audit · **Fase**: 4 · **Data**: 2026-08-13
**Zona**: `spa-world` — `worker.py` (2350 righe), `worker_entry.py` (142),
`register.py` (159), `register_registry.py` (511), `subscription_index.py`
(118), `global_store.py` (266), `environ.py` (178), `__init__.py` (40), letti
per intero. `commander.py` è citato in sola lettura dove una affermazione
dell'ebook lo tocca (nessuna riga di sorgente è stata modificata in nessun
file).
**Autorità**: l'inventario delle affermazioni dell'ebook in
`audit/00_authorities.md` §4, tag `spa-world`.

**Stato**: schede da walkthrough. Ogni scheda porta almeno un `file:riga`. Le
schede di conferma non hanno verdetto da dare (il codice e il libro dicono la
stessa cosa); le schede di **disaccordo** e le proposte di lente 2 portano la
casella **Verdetto: —** che questa run non riempie mai.

Sigle: **E/B** affermazioni dell'ebook (le sigle di 00_authorities) ·
**SD** difesa per scenario impossibile in questa zona (specie 1) ·
**SI** indirezione senza significato in questa zona (specie 3).

Per ogni disaccordo le opzioni sono sempre le stesse due, come deciso in
pianificazione: **(a) il codice si adegua** · **(b) il titolare emenda il libro
a verbale**. Nient'altro è ammesso e nulla muore per difetto.

---

## Lente 1 — L'ebook contro il codice

### A. Affermazioni confermate

Diciotto affermazioni `spa-world` risultano vere alla lettera, ciascuna con
la sua àncora nel codice attuale.

| # | Affermazione (sintesi) | Conferma nel codice |
|---|------------------------|---------------------|
| **E1** | tre livelli annidati: l'utente possiede le connessioni, la connessione le pagine, la pagina il proprio albero di dati | `register_registry.py:36-46` («page → connection → user», archi discendenti nei set `connections`/`pages`, archi ascendenti nella chiave del padre); la pagina nasce col proprio `store` a `register_registry.py:308-324` |
| **E3** | un solo scrittore per fatto: il processo possiede la verità delle sue pagine, il supervisore quella di chi-sta-dove | `worker.py:20-25` («Contents live here and nowhere else: the commander keeps keys and locations only»); `commander.py:25-27`, `commander.py:50-52` (`user_worker_map` «is the ONLY structure that says WHERE a user is») |
| **E5** | fase di quiete: si alza una barriera, si aspettano le chiamate vive, e solo allora si fa il pacco — con un tempo massimo | ordine esatto in `move_user`: barriera `commander.py:2459`, quiete `commander.py:2461`, pacco `commander.py:2468`; il budget è `MOVE_QUIESCE_TIMEOUT = 10.0` (`commander.py:413`), letto da `quiesce_user` (`commander.py:2515-2519`) |
| **E6** | ordine della rinascita: prima l'utente, poi le connessioni, poi le pagine; collettori attaccati DOPO la reidratazione | `add_user` in quell'ordine: utente `worker.py:2340-2342`, connessioni `2343-2344`, pagine `2345-2346`; il perché è dichiarato in `install_page` (`worker.py:2282-2285`) e la reidratazione precede l'attacco perché il Bag arriva già ricostruito dal blob (`worker.py:2333`) |
| **E7** | va distinto un ritiro voluto da un crollo, rilanciato con un nome nuovo perché nessun messaggio in ritardo sia scambiato per il nuovo arrivato, e liberato tutto ciò che teneva — compresi i permessi di scrittura | `channel_lost` (`commander.py:1140-1176`): ritiro voluto solo se lo stato è `draining` (`commander.py:1156-1159`), altrimenti crollo con rilancio; il nome nuovo è un uuid mai riusato (`next_worker_name`, `commander.py:972-974`, regola dichiarata a `commander.py:123-126`); i «permessi di scrittura» sono la concessione dello store globale, rilasciata alla morte (`commander.py:1161-1165`), e gli utenti sono spazzati in entrambe le morti (`commander.py:1167`, `1174`) |
| **E8** | la memoria che un processo dichiara non è quella che sta usando (misura onesta) | `reusable_bytes()` (`worker.py:1104-1121`) legge `mallinfo2().fordblks`; il trim precede la lettura di RSS per costruzione (`worker.py:1013` in `occupancy_report`, motivato a `worker.py:1008-1011`) |
| **E9** | in sviluppo il worker vive dentro il supervisore, sullo stesso canale — una coppia di code invece di un socket, ma codifica ogni messaggio allo stesso modo | `attach_local_worker` (`commander.py:1047-1069`): riga di roster con `process=None`, `LocalChannel`, stesso REGISTER, `await self.worker.start()`; la codifica è verificata alla fonte: ogni busta passa da `Frame.encode()` (`channel/local.py:19-20`, `channel/local.py:109`) su due `asyncio.Queue` (`channel/local.py:149-150`) |
| **E10** | consegna a richiesta, non spinta: se una pagina tace, gli aggiornamenti l'aspettano nel collettore | `worker.py:138-145` (contratto), `wire_delivery` (`worker.py:1189-1215`) innestata sulla REPLY solo per una CALL con `page_id` (`worker.py:843-844`) |
| **E11** | chi ha originato serve prima i propri, poi il resto viaggia; una tabella che nessuno guarda non costa un invio | `notifyDbEvents` (`worker.py:1561-1566`): fan-out locale prima, ascesa dopo; l'esclusione dell'origine è del commander (`commander.py:96-105`); zero sottoscrittori = un lookup che manca (`subscription_index.py:20-22`, `worker.py:1591-1599`) |
| **E12** | un valore in cache porta il segno della tabella; quando la tabella cambia il valore è invalidato con una scrittura vera | osservatore per pagina `worker.py:1627-1641`, indice `record_cached_path` (`worker.py:1658-1669`), invalidazione con scrittura reale `page["store"][path] = None` a `worker.py:1709` |
| **E13** | albero comune con un solo scrittore e una replica locale; letture-e-scritture per concessione ordinata, tutto-o-niente, rilasciata da sé se chi la teneva muore | replica `worker.py:580-588`, master e unico scrittore `commander.py:107-117`, FIFO `global_store.py:167-185`, tutto-o-niente `global_store.py:38-42` + `worker.py:1792-1804`, rilascio alla morte del canale `commander.py:1161-1165` |
| **E19** | andando giù il pool raccoglie ogni utente e lo scrive su file; risalendo li ripiazza prima che qualcosa possa essere instradato | `write_dump` è la PRIMA cosa dello `stop` (`commander.py:659`, motivata a `commander.py:669-670`); `restore_dump` è l'ULTIMA cosa dello `start` (`commander.py:656`, motivata a `commander.py:650-651`) e rinomina il file `_loaded` (`commander.py:759`) |
| **E20** | il processo sintetizza l'ambiente WSGI e invoca l'applicazione al proprio interno, su un pool di thread dedicato e separato da quello delle operazioni | `WsgiSeam` (`environ.py:59-108`, `environ.py:156-178`); il secondo pool è `http_pool` (`worker.py:508`, commento 506-507) e `serve_http` gira su quello (`worker.py:790`) |
| **B2** | i registri di superficie del commander sono dizionari piatti, deliberatamente non la macchina Register del worker — **otto** registri | dichiarato a `commander.py:25-27` e verificato uno per uno: `worker_roster` 554, `user_worker_map` 555, `forward_counters` 558, `user_consumption` 559, `connection_user` 562, `user_connections` 563, `connection_pages` 567, `page_connection` 568 — otto esatti |
| **B3** | la mappa si scrive alla decisione; il worker al login non spedisce nulla, annuncia soltanto | `worker.py:1950-1955` («The login never ships … the slice stays HERE»), `commander.py:170-177` («THE MAP IS WRITTEN AT THE DECISION (the founding contract)») |
| **B4** | il worker di una pagina si deriva risalendo pagina → connessione → utente → worker: nessun duplicato che possa divergere | `page_worker` (`commander.py:1712-1726`), tre lookup e `None` a ogni salto mancante; la regola generale a `commander.py:75-82` |
| **B5** | il ruolo «single» è configurazione, non una sottoclasse: `local_worker=True` costruisce un worker in questo processo e lo attacca via LocalChannel | kwarg `commander.py:453`, campo `commander.py:522`, ramo di avvio `commander.py:653-654`, costruzione `commander.py:1047-1069`; nessuna sottoclasse esiste |
| **B10** | lo sweep delle scadenze è disarmato — non codice incompleto, codice che aspetta un'informazione | `sweep_interval=None` per difetto (`worker.py:491-493`), il task nasce solo se armato (`worker.py:634-635`), la ragione è dichiarata in `sweep_loop` (`worker.py:2160-2165`) |

Nota su **E1**: l'ebook dice «ogni pagina possiede il proprio albero di dati» e
il codice ne ha **due** per pagina — lo `store` proprio e la finestra
`user_view` sullo store dell'utente (`register_registry.py:85-96`). È un
arricchimento, non un disaccordo: la scheda lo registra perché la fase 5 non
lo scopra come mancanza.

### B. Disaccordi — schede

#### E4 — «se l'installazione non riesce, l'utente deve restare dov'era, non sparire»
**Il libro dice** (sezione *Il momento in cui l'utente non è da nessuna parte*):
«Durante uno spostamento c'è un istante in cui la sessione è stata staccata
dall'origine e non è ancora installata a destinazione. Se una richiesta arriva
proprio allora, deve attendere, non fallire — e se l'installazione non riesce,
l'utente deve restare dov'era, non sparire.»

**Il codice fa**: la prima metà è vera. La barriera per-utente (`self.moving`,
`commander.py:579`) è alzata prima di qualunque altra cosa
(`commander.py:2459`) e ogni forward di quell'utente vi si parcheggia
(`await_move`, `commander.py:2617-2624`; il forward la interroga a
`commander.py:2087`): la richiesta attende, non fallisce.

La seconda metà **non è quella che il codice garantisce**. Il punto di non
ritorno è lo sfratto: la sorgente si spoglia mentre risponde
(`encode_user` → `registry.drop_user`, `worker.py:2251`), quindi «restare
dov'era» non esiste più come stato raggiungibile. Ciò che il codice fa dopo lo
sfratto è **offrire un'altra stanza**: `install_in_custody`
(`commander.py:2567`) ritenta su `salvage_target` (`commander.py:2605-2610`, la
sorgente inclusa) e, se il pool è vuoto, alza un errore esplicito
(`commander.py:2603`). E c'è un caso in cui l'utente **sparisce davvero**:
se lo sweep lo ha toccato mentre il pacco era in custodia (la sorgente è
morta), la fetta viene scartata dove è atterrata, con un warning
(`commander.py:2481-2498`) — dichiaratamente «exactly as dead as if no move
had been in flight».

Prima dello sfratto, invece, il libro è rispettato alla lettera: quiete non
riuscita (`commander.py:2462-2467`) e sfratto fallito
(`commander.py:2469-2474`) lasciano l'utente esattamente dov'era.

**Delta**: la prima clausola conforme, la seconda **divergente** — la garanzia
implementata è «la fetta non si perde mai in silenzio: atterra da qualche
parte, o muore rumorosamente», non «l'utente resta dov'era».

**Opzioni**: (a) il codice si adegua — servirebbe una copia trattenuta alla
sorgente fino alla conferma dell'install (rollback, che oggi non esiste in
nessun punto del disegno); (b) il libro si emenda a verbale, sostituendo la
seconda clausola con la garanzia vera (nessuna perdita silenziosa: rialloco, o
errore esplicito).

**Verdetto: —**

#### E14 — «la persona continua a essere servita dove si trova»
**Il libro dice** (sezione *Il governo dei processi*): «La mappa si aggiorna per
ultima: finché l'installazione non è confermata, la persona continua a essere
servita dove si trova, e se la destinazione muore le si offre un altro posto.»

**Il codice fa**: prima e terza clausola confermate — la mappa si scrive dopo
l'install (`commander.py:2500`, dichiarato a `commander.py:222-224`) e la morte
della destinazione manda la fetta su un altro worker
(`commander.py:2605-2610`, dichiarato a `commander.py:226-228`). La clausola
centrale è **imprecisa**: durante la finestra la persona non è *servita* dove si
trova — la sua chiamata è **parcheggiata** sulla barriera
(`commander.py:2087`, `commander.py:2617-2624`) e riparte solo quando la
barriera cade (`release_move`, `commander.py:2612-2615`). È vero che la mappa
continua a nominare la sorgente, e questa è la ragione per cui nulla viene
instradato male; ma il servizio è sospeso, non continuo.

**Delta**: **derivato** — la frase descrive lo stato della mappa e usa il verbo
del servizio, che è ciò che E4 racconta correttamente dall'altro lato
(«deve attendere»). Le due affermazioni dell'ebook descrivono la stessa
finestra in due modi non compatibili tra loro.

**Opzioni**: (a) nessun codice da cambiare, il disaccordo è interno al libro;
(b) allineare la frase a quella di E4 («la richiesta attende, e quando la
barriera cade trova la persona al posto giusto»).

**Verdetto: —**

#### E21 — «per ogni processo lo stato nel ciclo di vita, quando è nato e, se è morto, quando e come»
**Il libro dice** (sezione *Il ponte con l'esistente*): «Una chiamata sola
compone la popolazione viva: per ogni processo i suoi utenti, le sue
connessioni, le sue pagine, con i consumi cumulativi di ciascuno; e per ogni
processo lo stato nel ciclo di vita, quando è nato e, se è morto, quando e
come. Un processo irraggiungibile non fa cadere la lettura: compare con il
proprio stato di irraggiungibilità.»

**Il codice fa**: `population()` (`commander.py:1976-2006`) è davvero **una
chiamata sola** — un fan-out concorrente di `monitor_state` su tutti gli attivi
(`commander.py:1986`) — e porta utenti, connessioni, pagine
(`commander.py:2002-2004`) con il consumo cumulativo fuso all'arrivo
(`commander.py:1993-2000`); l'irraggiungibilità compare come
`row["error"] = "unreachable"` (`commander.py:1991`) senza far cadere la
lettura (`fetch_monitor_state` cattura tutto, `commander.py:1970-1972`). Le
clausole sul ciclo di vita **non sono servite da nessuna parte**: la riga
prodotta porta `id`, `group`, e poi `error` oppure
`users`/`connections`/`pages` — mai `status`, `spawned_at`, `died_at`,
`death`. Quei quattro campi esistono nella riga di roster
(`commander.py:995-1000`) e sono letti solo internamente e dal log di
sepoltura (`commander.py:890-896`); l'altra proiezione del monitor,
`metrics_view` (`commander.py:1936-1955`), porta occupazione, componenti,
storia, tassi, pavimento, tempo-al-limite e il libro mastro dei forward —
nessuno stato di ciclo di vita. Verificato anche che `population()` non ha
consumatori fuori dai test (`tests/test_spa_monitor.py:271`, `289`, `298`,
`306`): nessuna terza superficie li aggiunge.

**Delta**: **parzialmente assente** — due clausole su quattro non hanno
implementazione. Inoltre `population()` cammina solo `active_workers`
(`commander.py:1985`), quindi un processo morto non compare affatto: «se è
morto, quando e come» non ha nemmeno una riga in cui stare.

**Opzioni**: (a) il codice si adegua — la riga di `population()` porta anche
`status`/`spawned_at`/`died_at`/`death` e la lista include le tombe finché la
sepoltura non le rimuove; (b) il libro si emenda togliendo le due clausole,
che descrivono il monitor legacy e non questo.

**Verdetto: —**

#### E22 — «i registri contengono dati serializzabili per costruzione, mai oggetti vivi come verità»
**Il libro dice** (sezione *Lo stato di lavoro attraversa le versioni*): «Ciò che
rende praticabile tutto questo è un vincolo posto all'origine: i registri
contengono dati serializzabili per costruzione, mai oggetti vivi come verità.
Un oggetto vivo non si può spedire e non si può versionare.»

**Il codice fa**: la sostanza tiene dove conta — ciò che viaggia è
serializzabile e ciò che è vivo viene **ricostruito** a destinazione, non
spedito: `MOVE_REBUILT_FIELDS` esclude dal pacco i due collettori e la lista
`dbevents` (`worker.py:341-343`), `LIVE_ROW_FIELDS` esclude gli oggetti vivi da
ogni risposta di op (`worker.py:333-337`, usato da `wire_entry`
`worker.py:1127-1140`), e lo store viaggia come Bag dentro il pickle
(`worker.py:2244-2252`).

Ma **le righe dei registri contengono oggetti vivi**, e in due punti quegli
oggetti sono la verità di qualcuno:

- riga di pagina: `store` (Bag), `collector` e `user_view`
  (`register_registry.py:308-324`) — il libro stesso li chiama «vivi»
  (`register_registry.py:85-96`), e il `collector` è la verità di ciò che una
  pagina deve ancora ricevere: se non viene ricostruito, il pendente si perde.
  Il pacco lo aggira drenandolo in valori (`worker.py:2219-2227`), che è
  esattamente il modo in cui la regola viene rispettata **a valle**, non
  all'origine.
- riga di roster del commander: `process` (un `subprocess.Popen`) e
  `caretaker` (un `asyncio.Task`) — dichiarati nella docstring
  (`commander.py:29-31`) e creati a `commander.py:976`. Il roster non viene mai
  serializzato (il dump scrive le fette utente, `commander.py:701-731`), quindi
  la regola non è violata nella pratica; ma l'affermazione «i registri
  contengono dati serializzabili per costruzione» letta alla lettera è falsa
  per questo registro.

**Delta**: **derivato** — la regola vale per ciò che attraversa le versioni
(le fette), non per le righe dei registri, che ospitano oggetti vivi per
disegno.

**Opzioni**: (a) nessun codice da cambiare (l'alternativa sarebbe togliere gli
oggetti vivi dalle righe, che è il disegno opposto a quello ratificato);
(b) il libro precisa il soggetto: «ciò che viaggia è serializzabile per
costruzione; gli oggetti vivi restano nel processo e vengono ricostruiti a
destinazione, mai spediti».

**Verdetto: —**

#### E26 — «la colonna del gruppo è già presente in ogni registro»
**Il libro dice** (Roadmap): «Gruppi e versioni conviventi — *in
implementazione* — la colonna del gruppo è già presente in ogni registro».

**Il codice fa**: la colonna esiste in **un** registro, la riga di roster
(`"group": self.group`, `commander.py:997`), scritta dal kwarg del commander
(`commander.py:445`, campo a `commander.py:513`). Gli altri sette registri
piatti non hanno colonne: sono mappe chiave→chiave o chiave→set
(`commander.py:554-568`). Il gruppo di un utente è **derivato** dalla riga del
suo worker, come la docstring dichiara: «A user's routing group is its worker's
``group``, read from the row» (`commander.py:48-49`). Nei registri del worker
(`user_items`/`connection_items`/`page_items`, `register_registry.py:133-140`)
la parola `group` non compare affatto.

Questa è anche una **contraddizione interna al libro**: B7 lo dice giusto
(«ricopiato in ogni riga del *roster*»), E26 dice «in ogni registro».

**Delta**: **divergente** (l'affermazione è più larga del fatto).

**Opzioni**: (a) nessun codice — il gruppo derivato è il disegno voluto;
(b) allineare E26 al testo di B7.

**Verdetto: —**

#### B1 — I conteggi per modulo: nove esatti, uno derivato di +3
**Il libro dice** (*11 · Piano SPA — orchestrazione*), tabella con intestazione
**«Modulo · Ruolo · Stmt · Cov»** e totale di blocco «2.580 stmt · 95%».

**Il codice dà** (misurato 2026-08-13, `pytest --cov=src/genro_asgi/spa`):

| Modulo | Libro | Oggi | Esito |
|--------|-------|------|-------|
| `spa/commander.py` | 1209 · 95% | **1212** · 95% | +3 stmt |
| `spa/worker.py` | 782 · 95% | 782 · 95% | esatto |
| `spa/register_registry.py` | 146 · 100% | 146 · 100% | esatto |
| `spa/evaluator.py` | 124 · 100% | 124 · 100% | esatto |
| `spa/global_store.py` | 75 · 100% | 75 · 100% | esatto |
| `spa/worker_entry.py` | 69 · 72% | 69 · 72% | esatto |
| `spa/register.py` | 66 · 100% | 66 · 100% | esatto |
| `spa/environ.py` | 60 · 100% | 60 · 100% | esatto |
| `spa/subscription_index.py` | 44 · 100% | 44 · 100% | esatto |
| totale di blocco | 2.580 · 95% | **2.583** · 95% | +3 stmt |

**Àncore**: la tabella del libro sta in
`docs/html/architettura_blocchi.html:610` (la riga di `commander.py`) e il
totale di blocco a `docs/html/architettura_blocchi.html:603`, ripetuto in prosa
a `docs/html/architettura_blocchi.html:671`; il modulo che deriva è
`src/genro_asgi/spa/commander.py:1-3183`, misurato con
`pytest --cov=src/genro_asgi/spa` il 2026-08-13.

**Rilievo di metodo, per la fase 5**: la nota di fase 1 (00_authorities:360-363)
prevedeva «uno scarto sui conteggi già visibile: `commander.py` è oggi 3183
righe». Quello scarto **non esiste**: la colonna del libro è `Stmt`, non righe
fisiche — i numeri sono i conteggi di `coverage.py`, e nove su dieci coincidono
alla cifra. L'unico scarto reale è di **tre statement** in `commander.py`,
maturato dopo la stampa del libro.

**Delta**: **conforme con deriva numerica minima** (+3 stmt su 2.583, 0,1%).

**Opzioni**: (a) nessun codice; (b) aggiornare i due numeri (1212 e 2.583) alla
prossima rigenerazione del libro — l'ebook si rigenera da misura, quindi la
scheda è un promemoria di rigenerazione, non una correzione a mano.

**Verdetto: —**

#### B7 — «nessun test passa mai un valore diverso» (e le due àncore)
**Il libro dice** (*Stato delle capacità*): «Gruppi di worker — **Solo
progettato** — esiste solo l'*etichetta*: un kwarg `group` di default "default"
ricopiato in ogni riga del roster (`commander.py:445`, 990) e riletto solo dal
log di sepoltura e dal monitor. L'instradamento è cieco al gruppo —
`decide_worker` sceglie per saturazione — e nessun test passa mai un valore
diverso».

**Il codice fa**: la sostanza tiene interamente. Kwarg a `commander.py:445`
(default `DEFAULT_GROUP`, `commander.py:323-324`, dichiarato PROVISIONAL);
copia nella riga di roster a **`commander.py:997`** (l'ebook dice 990: àncora
derivata di 7 righe); riletta in due soli punti, il log di sepoltura
(`commander.py:890`, `894`) e il monitor (`commander.py:1989`);
`decide_worker` (`commander.py:2127`) non nomina il gruppo.

L'ultima clausola è però **letteralmente falsa oggi**: un test passa
`group="site-group"`
(`tests/test_spa_application.py:57`). Ciò che quel test asserisce è solo che il
kwarg viene sbucciato e inoltrato al commander
(`tests/test_spa_application.py:61-69`): nessun comportamento cambia col
valore, nessun instradamento viene osservato. La sostanza della frase — la
colonna non è la feature — resta intatta.

**Delta**: **conforme nella sostanza**, due precisazioni da fare (àncora 990 →
997; «nessun test passa mai un valore diverso» → «un test passa un valore
diverso e asserisce solo che viene inoltrato»).

**Opzioni**: (a) nessun codice; (b) correggere àncora e clausola alla prossima
rigenerazione.

**Verdetto: —**

---

## Lente 2 — Essenzialità su questa zona

Metodo: le tre domande dell'onere della prova (00_authorities §3). Specie 1
(difese per scenari impossibili) e specie 3 (indirezione senza significato);
nessun esperimento di strip in questa fase — solo analisi dei chiamanti. La
regola di casa vale su ogni proposta di specie 1: **si rimuove, o si sostituisce
con un errore rumoroso — mai gestione silenziosa**.

Dove una difesa non è mai eseguita dai test, la prova è la colonna
`Missing` di coverage misurata oggi su `src/genro_asgi/spa/worker.py` (37
statement non eseguiti su 782).

### SD1 — I salti taciti della fotografia del monitor
**Il pezzo**: nei tre camminamenti di `monitor_state` ogni riga letta è
ricontrollata e saltata se sparita: `worker.py:941-943` (utenti),
`worker.py:947-949` (la connessione all'altro capo di un arco),
`worker.py:965-966` (connessioni), `worker.py:981-983` (pagine).

**Chi lo ha postulato**: nessuna autorità esterna — la docstring stessa
(`worker.py:893-899`) motiva il disegno: fotografia senza `dispatch_lock`, «a
row swept while it is taken is simply not in it».

**Cosa si rompe senza**: niente in un caso, qualcosa in un altro. Le due
`continue` di utenti e pagine (`worker.py:943` e `983`) **non sono mai
eseguite** dalla suite; quella delle connessioni (`worker.py:966`) sì. Il salto
di `worker.py:947-949` è di natura diversa: è un arco pendente
(`connections` che nomina una connessione già demolita) e non una riga
mancante, quindi va giudicato a parte.

**C'è una strada più corta**: sì — prendere `dispatch_lock` per la fotografia
e togliere tutti e quattro i controlli. Ma il costo è dichiarato nella
docstring (il lock è tenuto da passate lunghe: un pacco di move, un batch
discendente intero) e la fotografia è un poll. La proposta **non** è di
togliere la tolleranza, è di sceglierne una sola forma per tutti e tre i
camminamenti invece di tre varianti.

**Proposta**: uniformare i tre salti a un solo idioma (l'attuale delle
connessioni, che è l'unico esercitato) e decidere se il salto resta silenzioso
o produce una riga di debug — oggi non produce nulla e la fase 3 ha già
dimostrato, su un caso gemello, che il silenzio non prova niente.

**Verdetto: —**

### SD2 — La REPLY perduta senza rumore
**Il pezzo**: `WorkerChannelClient.send_frame` (`worker.py:456-464`) inghiotte
`BrokenPipeError`/`ConnectionResetError` con un log di debug e **restituisce
l'id come se avesse spedito** (`worker.py:461-464`, non eseguite dalla suite).

**Chi lo ha postulato**: nessuna autorità. La classe esiste perché
`channel/client.py` è ratificato intoccabile e una REPLY riusa l'id della CALL
(`worker.py:446-454`).

**Cosa si rompe senza**: l'eccezione risalirebbe a `guarded_service`
(`worker.py:715-725`), che la registra con `logger.exception` — cioè
esattamente il comportamento rumoroso che la regola di casa chiede, già
presente e già motivato («a REPLY the dropped channel refused, past
`answer_call`'s own catch — is logged here»).

**C'è una strada più corta**: sì, tre righe in meno. `raise ConnectionError`
a `worker.py:458-459` resta (è il caso «non connesso», diverso).

**Proposta**: rimuovere il `try/except` di `worker.py:460-464` e lasciare
salire l'errore fino alla guardia che già esiste. La regola di casa: un canale
caduto è un fatto, non un silenzio.

**Verdetto: —**

### SD3 — La concessione che nessuno attende, e il futuro già risolto
**Il pezzo**: `grant_global_lock` (`worker.py:1814-1827`) scarta la concessione
quando `future is None or future.done()` (`worker.py:1822`); il ramo di scarto
(`worker.py:1823-1826`) non è mai eseguito.

**Chi lo ha postulato**: nessuna autorità; la docstring dichiara il caso
(«the acquire was cancelled»).

**Cosa si rompe senza**: il ramo `is None` è raggiungibile per costruzione —
`acquire_global_lock` cancella la propria voce nel `finally`
(`worker.py:1788-1789`), quindi una concessione che arriva dopo una
cancellazione trova la mappa vuota. Il secondo ramo, `future.done()`, richiede
una voce ancora registrata con un futuro già risolto: non esiste finestra in
cui questo accada, perché l'unico `set_result` è qui e la voce muore subito
dopo.

**Proposta**: tenere `is None` (raggiungibile, e giustamente silenzioso: il
commander rilascerà da sé alla morte del canale) e togliere `or future.done()`,
oppure trasformare quel solo caso in errore rumoroso. Due mezze difese in una
condizione sola sono ciò che rende impossibile dire quale delle due serve.

**Verdetto: —**

### SD4 — I due `except Exception` sui batch discendenti
**Il pezzo**: `apply_datachange_in` (`worker.py:1339-1342`) e
`apply_dbevents_in` (`worker.py:1716-1719`) avvolgono l'intero batch in un
`except Exception` con `logger.exception`. Nessuno dei due gestori è eseguito
dalla suite (`worker.py:1341-1342`, `1718-1719`).

**Chi lo ha postulato**: nessuna autorità; le due docstring non li motivano
(dicono perché il lavoro è fuori dal loop, non perché l'errore va inghiottito).

**Cosa si rompe senza**: l'eccezione morirebbe nel task creato da
`spawn_service` (`worker.py:704-713`) — un task il cui errore non viene mai
recuperato, cioè un warning di asyncio invece di un log. Questa è la ragione
strutturale per cui la CALL ha `guarded_service`: le due vie EVENT non hanno
un equivalente e questi due `except` ne fanno le veci.

**C'è una strada più corta**: sì — una sola guardia in `spawn_service` al posto
di due `except` identici in due punti diversi, che è anche il modo in cui la
via CALL è già fatta.

**Proposta**: spostare la guardia in `spawn_service` (una sola, per tutte le
vie discendenti) e togliere i due `try/except`. Nessun comportamento cambia;
spariscono quattro righe e una duplicazione.

**Verdetto: —**

### SD5 — Il confronto d'orologio che non può fallire
**Il pezzo**: `cpu_fraction` (`worker.py:1028-1043`) esce con `None` se
`previous_ts is None or previous_used is None or now <= previous_ts`
(`worker.py:1041`).

**Chi lo ha postulato**: nessuna autorità; la docstring motiva solo il primo
caso («None on the first call»).

**Cosa si rompe senza**: `time.monotonic()` non torna indietro, quindi
`now < previous_ts` è impossibile; `now == previous_ts` è invece **possibile**
su due sonde nello stesso tick di orologio e senza la difesa sarebbe una
`ZeroDivisionError` — cioè uno scenario improbabile che finisce in errore
rumoroso, il che è ammesso dalla regola fondamentale ma non è la scelta fatta
qui. `previous_used is None` è impossibile in modo diverso: i due campi sono
assegnati insieme (`worker.py:1040`), quindi la seconda metà della congiunzione
non può essere vera senza la prima.

**Proposta**: togliere `previous_used is None` (impossibile per costruzione) e
decidere se `now <= previous_ts` resta un `None` silenzioso o diventa un
errore. Il valore in gioco è una frazione di CPU che il valutatore legge: un
`None` in più è già un caso previsto a monte.

**Verdetto: —**

### SI1 — `Outbox.ping_now`: nessun lettore in produzione
**Il pezzo**: la proprietà `ping_now` (`worker.py:440-443`), «True when there is
something to drain».

**Chi la chiama**: nessuno in `src/`. L'unico lettore è
`tests/test_spa_worker.py:190`. Il contatore vero (`pending()`,
`worker.py:435-438`) ha invece un lettore reale, `occupancy_report`
(`worker.py:1019`).

**Proposta**: rimuovere la coppia (proprietà + la riga di test che la
asserisce). È il caso più puro di specie 3 della zona: un nome che aggiunge
niente a `pending() > 0` e che nessun produttore consulta.

**Verdetto: —**

### SI2 — I tre inoltri di una riga di `RegisterRegistry`
**Il pezzo**: `new_register` (`register_registry.py:157-168`), `add_index`
(`register_registry.py:170-177`), `update_page`
(`register_registry.py:436-438`). Il primo crea e ospita; gli altri due sono
inoltri di una riga a `Register.add_index` e `page_items.update`.

**Chi li chiama**: nessuno in `src/`. I chiamanti sono solo i test
(`tests/test_register_registry.py:47-68` per `new_register`,
`tests/test_register_registry.py:150-153` per `update_page`;
`add_index` è esercitato solo nella sua forma di `Register`,
`tests/test_registry.py:156-170`).

**Chi li ha postulati**: la docstring del modulo, che li dichiara **seam di
estensione** — «The extension seam» (`register_registry.py:48-54`) e il
vocabolario di ciclo di vita (`register_registry.py:56-61`). Non sono
accrescimento: sono API dichiarata per un consumatore che ancora non esiste in
questo repo (genropy-asgi).

**Proposta**: nessuna rimozione proposta; la scheda esiste per **nominare la
scelta**: sono tre superfici pubbliche senza consumatore interno, quindi ogni
riga che le riguarda è coperta solo dai test che le esercitano. Se il titolare
decide che la seam va tenuta, la voce muore qui (e la fase 5 la registra tra le
Scartate con questa motivazione).

**Verdetto: —**

### SI3 — Il kwarg `channel` del costruttore del worker
**Il pezzo**: `UserStickyWorker.__init__` accetta `channel`
(`worker.py:479`, documentato a `worker.py:490`) e lo aggancia in coda
(`worker.py:553-554`). La riga 554 **non è mai eseguita** dalla suite.

**Chi lo chiama**: nessuno. Entrambe le vie reali di costruzione passano da
`attach_channel`: il processo figlio (`worker_entry.py:118-119`) e il worker
in-process (`commander.py:1060-1061`).

**Cosa si rompe senza**: niente — `attach_channel` (`worker.py:624-628`) fa
esattamente il lavoro e resta l'unica porta.

**Proposta**: rimuovere il kwarg e le sue due righe, oppure dichiararlo seam
come SI2 (ma qui nessuna docstring lo dichiara tale: è nato come comodità).

**Verdetto: —**

### SI4 — `holds_target`, e perché resta
**Il pezzo**: `holds_target` (`worker.py:1306-1308`) è un involucro di una riga
su `target_row(...) is not None`.

**Chi lo chiama**: due punti (`worker.py:1282` nello switch,
`worker.py:1348` nel batch discendente).

**Giudizio proposto**: **tenere**. Non è indirezione senza significato: il nome
dice il concetto («questo worker tiene il destinatario?») nei due soli punti
che decidono su di esso, e togliere l'involucro renderebbe entrambi meno
leggibili. La scheda esiste perché la fase 5 sappia che il caso è stato
guardato e archiviato, non dimenticato.

**Verdetto: —**

---

## Cosa questa fase NON ha fatto

- **Nessun esperimento di strip**: deciso in pianificazione (fase analitica).
  Le cinque schede SD nominano il pezzo con precisione sufficiente a farne uno,
  se il titolare lo vuole prima di dare il verdetto.
- **Nessun castello di pezze (specie 4)**: l'issue li dichiara fenomeno del
  commander e in questi otto moduli nessuno salta agli occhi. `worker.py` non è
  stato toccato da wf#8 (verificato in pianificazione), quindi non ha
  accrescimento di quella run.
- **Nessuna verifica delle affermazioni non `spa-world`**: E2, E15-E18,
  E23-E25, B6, B8, B9 appartengono alle zone `tests` e `recycling-code`
  (fasi 2 e 3).
- **Nessun verdetto**: le caselle restano vuote per il walkthrough.

**Conteggio**: 18 affermazioni confermate · 7 schede di disaccordo (E4, E14,
E21, E22, E26, B1, B7) · 9 schede di lente 2 (SD1-SD5, SI1-SI4) = 16 schede con
verdetto in attesa.
