# Analisi del repository genro-asgi

Data: 19 agosto 2026  
Branch analizzato: `wf/orchestration-m4-request-login` (`bce7e19`)  
Confronto principale: `main` (`ca75bfb`) e tag `v0.34.0` (`fab91f3`)

## Sintesi esecutiva

Il repository non è in una rifattorizzazione ordinaria: sta sostituendo il cuore
di orchestrazione SPA conservando temporaneamente in parallelo la macchina
legacy. La strategia è sensata e disciplinata: nuovo stack isolato, contratti
legacy mantenuti come sentinelle, fasi piccole, decisioni registrate e test ad
alta copertura.

Lo stato reale al 19 agosto 2026 è:

- il server ASGI generale è maturo e largamente operativo;
- la vecchia orchestrazione SPA continua a essere quella pubblica e completa;
- la nuova orchestrazione ha completato Macro 1–3;
- Macro 4 ha completato 4 fasi su 5: request chain, login e nuovo front sono
  implementati, ma manca l'end-to-end reale dell'intera giornata operativa;
- Macro 5 deve ancora portare il data plane, completare l'integrazione delle
  manovre operative, la persistenza di riavvio e l'osservabilità;
- Macro 6 farà il cutover, esporrà il nuovo front e rimuoverà il legacy.

Giudizio complessivo: **rifattorizzazione ben governata e con buona evidenza di
correttezza, ma non ancora pronta per il cutover**. Il rischio principale non è
la qualità locale del codice già scritto; è la quantità di comportamento
operativo ancora concentrata nel legacy e da migrare in Macro 5.

## Evidenze raccolte

- Worktree pulito all'inizio; al termine l'unica aggiunta è questo rapporto
  nella cartella `codex/` autorizzata.
- `ruff check --no-cache src/ tests/`: superato.
- Suite completa, eseguita consentendo i socket Unix ma mettendo cache e
  copertura in `/tmp`: **1.988 passed, 2 skipped**, 2 avvisi di deprecazione.
- Copertura complessiva: **97%** su 9.660 statement.
- Nuova orchestrazione: 5.172 righe fisiche in `spa/orchestration/`.
- Cuore legacy ancora presente: 6.602 righe fra `spa/commander.py` e
  `spa/worker.py`, oltre al vecchio front.
- Da `v0.34.0` a HEAD: 83 file toccati, 23.280 righe aggiunte e 627 rimosse.
- Rispetto a `main`, il branch Macro 4 aggiunge circa 2.885 righe nette in 21
  file; la maggioranza è costituita da piano, note e test.
- `mypy src/` è non bloccante per policy e oggi segnala **124 errori in 19
  file**. Ventinove sono nel nuovo front, in gran parte dovuti all'idioma della
  grammatica con default `None`; altri riguardano invarianti runtime non visibili
  al type checker. È debito reale, anche se non è un gate di progetto.
- Sul repository collegato `genropy-asgi`: **132 test superati**, controllo
  `ruff` pulito e 16 segnalazioni mypy, 13 delle quali sono import GenroPy senza
  stub. Le modifiche locali già presenti nei documenti e la cartella `users/`
  non sono state toccate.
- Verifica mirata delle policy del nuovo orchestratore: **186 test superati**
  su gruppi, accoglienza, capacità, partenze, freezer, request chain e
  configurazione multi-versione.
- Benchmark locale Pandas 3.0.2: per DataFrame di pochi KB pickle/unpickle resta
  sotto il millisecondo; su un DataFrame numerico da circa 80 MB ha richiesto
  rispettivamente circa 43 ms e 28 ms. Il costo da sorvegliare nei casi
  eccezionali è soprattutto la memoria di picco, non la latenza ordinaria.

## Architettura attuale

### Base server

Il nucleo segue una separazione coerente:

1. `BaseServer` possiede runtime, applicazioni, lifecycle, pool sincrono e
   request registry.
2. Le applicazioni possiedono comportamento, router e identità `code`/`mount`.
3. `AsgiServer` compone autenticazione, sessioni, middleware, storage, task e
   comunicazione tramite mixin.
4. OpenAPI e MCP sono facce dello stesso albero di route.
5. `_server` è l'applicazione amministrativa automatica.

Questa parte è sostanzialmente allineata fra codice, test e prima parte
dell'ebook.

### SPA legacy, ancora pubblica

`applications/spa_app.py` esporta `SpaApplication`, che possiede
`UserStickyCommander` e `UserStickyWorker`. Qui vivono ancora tutte le capacità
operative complete: datachange e dbevent, sottoscrizioni, global store, move
live, ladder di bilanciamento, riciclo, hard restart, dump/restore, monitor e
worker locale.

Il legacy non è semplicemente codice morto: oggi è il riferimento di continuità
e la macchina che serve il traffico reale.

### Nuovo stack

Il nuovo asse di ownership è chiaro:

`server → SpaApplicationNew → SpaCommander → GroupHandler → WorkerHandler → socket → SpaWorker`

Le responsabilità risultano più leggibili:

- `SpaCommander`: indici globali, lifecycle, barrier, request chain, fold,
  freezer e controlli macchina;
- `GroupHandler`: placement, capacità, crescita, riduzione e restart dei worker;
- `WorkerHandler`: processo, wire e sorveglianza;
- `SpaWorker`: stato vivo di utenti/connessioni/pagine e sito WSGI;
- `EnvelopeHandler`: fold gerarchico degli eventi;
- `FreezeHandler`: persistenza temporanea dello stato utente su disco;
- `SpaApplicationNew`: front stateless, cookie, demux e traduzione HTTP.

Il nuovo front non è esportato da `applications/__init__.py` né dal package
principale: è coerente con il fatto che il cutover non sia ancora avvenuto.

### Mobilità tramite freezer

Nel nuovo stack la mobilità non manca: è stata deliberatamente ricondotta a un
solo percorso, `hold → freeze → placement vuoto → assegnazione → unfreeze`.
Questo percorso viene usato per la chiusura di un worker scarico, la sostituzione
ordinata di un worker e il risveglio di un utente. La richiesta che incontra un
utente fra due case attende sulla barrier; la nuova assegnazione viene decisa
sulla fotografia aggiornata del gruppo.

Il trasferimento diretto worker-to-worker e il `move live` del legacy non sono
quindi requisiti mancanti da riprodurre: sono complessità intenzionalmente
eliminate. L'ipotesi di progetto è che lo stato ordinario sia piccolo — oggi
tipicamente pochi KB — e che freeze/unfreeze sia saltuario. I benchmark svolti
confermano che questa ipotesi rende il costo di serializzazione trascurabile nel
percorso comune. Utenti eccezionali con grandi DataFrame vanno trattati con
metriche, soglie e margine di memoria, non imponendo al percorso comune un
secondo protocollo di migrazione.

DuckDB può essere utile quando un grande dataset è già uno stato applicativo,
interrogabile e ricostruibile per query; non risulta invece vantaggioso come
formato intermedio generale del freezer. Nei test era più lento di pickle sui
DataFrame numerici, non preservava sempre gli stessi dtype e richiedeva una
conversione esplicita per il dtype `str` di Pandas 3. Conviene quindi congelare
con pickle lo stato ordinario e, quando necessario, conservare nel parcel un
riferimento a una tabella DuckDB invece dell'intero DataFrame.

### Gruppi di versione e provisioning

Ogni gruppo può usare un proprio `executable`, modulo e classe worker: è il
confine corretto per stable, blue/green e canary. La decisione operativa è usare
UV per creare e mantenere i virtualenv delle diverse versioni; questo completa
il provisioning senza caricare l'orchestratore della gestione degli ambienti.
La scelta della coorte resta una policy applicativa: il motore conserva
l'affinità al gruppo e non applica autonomamente percentuali canary o fallback.
Va verificato nel bridge il collegamento fra l'etichetta applicativa di gruppo e
`record_user_group`, ma non è necessario introdurre un policy engine generico
se questa responsabilità resta deliberatamente all'applicazione.

### Crash del worker come rischio accettato

Una partenza ordinata congela gli utenti e consente la riassegnazione. Una morte
improvvisa, invece, considera non affidabile lo stato residente e fa ripartire
il numero limitato di utenti coinvolti. In linea teorica checkpoint o journal
potrebbero rendere trasparente anche questo caso, ma lo stato è una
sincronizzazione fra client e server e il crash di un singolo worker è assunto
come evento straordinario. Il riavvio di pochi utenti è quindi un rischio e un
disservizio consapevolmente accettati, non una lacuna rispetto al requisito.

Questa scelta evita replica continua, consenso sullo stato e recovery logico di
copie potenzialmente divergenti. Deve restare osservabile e confinata: numero di
utenti persi, causa della morte, tempo di ripartenza e frequenza dei crash sono
le metriche che possono invalidare in futuro l'assunzione.

## Stato del programma di rifattorizzazione

### Completato

- Macro 1: fondamenta, freezer, connector e handler del worker.
- Macro 2: nuovo processo worker, registri, freeze/adoption e wire.
- Macro 3: gruppi, commander, placement, heartbeat, fold e indici.
- Macro 4 / fase 1: gruppi posseduti dal commander, barrier e lifecycle.
- Macro 4 / fase 2: request chain completa e rifiuti tipizzati.
- Macro 4 / fase 3: login e relabel uniforme.
- Macro 4 / fase 4: nuovo front montabile, configurazione e traduzioni HTTP.

### Mancante prima del cutover

1. Macro 4 / fase 5: end-to-end con processi reali, sito WSGI reale, due gruppi,
   login, secondo browser, wake dal freezer, avatar switch e 503 sotto pressione.
2. Macro 5:
   - datachange/dbevent indirizzati;
   - sottoscrizioni e mailbox pendenti;
   - notifiche e broadcast;
   - global-store lock grant;
   - manovre freeze/reassign, recycle e ladder operativa complete, senza
     reintrodurre il move diretto cassato dal disegno;
   - hard restart, dump/restore e soft boot;
   - worker in-process;
   - monitor del pool e metriche Prometheus.
3. Macro 6: cutover, eliminazione del doppio stack, riclassificazione dei test e
   riallineamento della documentazione.
4. Dipendenza esterna dichiarata come bloccante per il traffico reale: seam
   `sticky_cid` in `genropy-asgi`.

## Il bridge genropy-asgi

`genropy-asgi` non è un semplice adattatore WSGI. È il consumer più esigente
dell'orchestrazione SPA e oggi fornisce:

- `GenropySpaApplication`, sottoclasse del front SPA legacy;
- `GenropyWorker`, sottoclasse di `UserStickyWorker`;
- un `GnrWsgiSite` reale dietro il seam `wsgi_app`;
- `GenropyRegisterClient`, che traduce il contratto del vecchio daemon in
  chiamate dirette al worker;
- Bag legacy, datachange, sottoscrizioni, dbevent, global store e pulizia delle
  cartelle di connessione;
- CLI `gnrasgiserve`, modalità single e pool daemonless.

Il bridge corrente è funzionante sul legacy: la suite include un E2E single e
un E2E CLI con un vero worker subprocess. È però ancora legato esplicitamente a:

- `genro_asgi.applications.spa_app.SpaApplication`;
- `genro_asgi.spa.UserStickyWorker` e `RegisterRegistry`;
- `genro_asgi.channel.hub.EVENT_METHOD`;
- `genro_asgi.spa.global_store`;
- il vocabolario legacy del worker (`new_connection`, `new_page`,
  `change_connection_user`, datachange, sottoscrizioni, dbevent e global lock).

Di conseguenza, Macro 6 non può cancellare il legacy nel solo repository
`genro-asgi`: deve essere preceduta da una versione compatibile di
`genropy-asgi`, provata contro il nuovo front e il nuovo worker.

### Il seam di identità

Il front ASGI instrada con il cookie opaco `sticky_cid`. Il GenroPy legacy,
invece, possiede un proprio `connection_id`, creato e conservato nel cookie del
sito. Nel codice GenroPy esaminato non esiste ancora una lettura esplicita di
`sticky_cid` come identità della connection.

Questo lascia due identità potenzialmente distinte:

`sticky_cid del front → identità di routing`  
`connection_id GenroPy → riga realmente relabelled al login`

Nel single la differenza può restare invisibile perché tutto vive nello stesso
processo. Con più worker diventa critica: il login può rietichettare la riga
GenroPy senza rietichettare la chiave con cui il front instrada la richiesta
successiva. Il piano di `genro-asgi` identifica correttamente questo punto come
bloccante per il traffico reale.

### Copertura attuale del bridge

Il test multiworker oggi prova:

- boot della CLI;
- un worker subprocess;
- pagina servita e ping;
- presenza di `sticky_cid`;
- contatori `/metrics` non nulli.

Non prova ancora:

- due o più worker contemporanei;
- uguaglianza `sticky_cid == connection_id` o un mapping esplicito fra i due;
- login e richiesta successiva sullo stesso utente;
- secondo browser dello stesso utente;
- datachange/dbevent cross-worker;
- global store cross-worker;
- freeze/wake, riassegnazione o restart con un vero sito GenroPy.

Questi scenari devono diventare gate cross-repository prima del cutover.

### Versionamento e documentazione del bridge

`genropy-asgi` dichiara `genro-asgi>=0.33.0` senza limite superiore. Una release
di `genro-asgi` che rimuovesse le classi legacy potrebbe quindi rompere il bridge
senza che il resolver segnali incompatibilità. Il cutover richiede una delle
seguenti strategie:

1. nuova versione del bridge pubblicata prima, compatibile con entrambi gli
   stack per una finestra breve;
2. release coordinate con vincolo esplicito sulle versioni;
3. seam pubblico di compatibilità mantenuto in `genro-asgi` fino al rilascio del
   bridge migrato.

Anche la documentazione interna del bridge è indietro: `pyproject.toml` è a
0.2.0, mentre `CLAUDE.md` e `spa.__version__` riportano ancora 0.1.0; inoltre
`CLAUDE.md` dichiara uso esclusivo della public API, ma l'implementazione importa
moduli interni di channel, SPA e global store.

## Punti di forza

### 1. Strategia di migrazione prudente

Il nuovo stack non importa il legacy e viceversa. I test del vecchio front
restano immutati e fungono da contratto. Questo riduce il rischio di un cutover
graduale ambiguo e rende possibile una sostituzione atomica in Macro 6.

### 2. Ownership più comprensibile

La scomposizione del commander monolitico in commander, gruppi e worker handler
è coerente con le decisioni di dominio. Placement e capacità sono locali al
gruppo; gli indici globali e la fold restano al vertice; il processo e il wire
restano sull'handler stabile.

### 3. Workflow con memoria decisionale

`.phased/` registra obiettivi, decisioni, nomi, deviazioni e verifiche di ogni
fase. Le note non si limitano a dire cosa è stato fatto: conservano anche perché
un'alternativa è stata rifiutata. Questo è particolarmente utile in un dominio
con concorrenza, recovery e stato distribuito.

### 4. Test forti

La suite copre sia contratti pubblici sia implementazione dell'orchestrazione,
con processi reali e socket reali. Il 97% globale non è da solo una garanzia,
ma qui è accompagnato da scenari di concorrenza, morte del worker, freezer,
login, move legacy, freeze/reassign nuovo e fold. La suite completa è verde sul
branch corrente.

### 5. Disciplina sul volume

Il piano considera il volume un difetto e pone limiti per fase. Il nuovo front
ha 108 statement coperti al 98%; il nuovo commander ha 275 statement coperti al
99%. La separazione non ha prodotto molti wrapper vuoti.

## Rischi e incoerenze da risolvere

### P0 — Il cutover dipende da una Macro 5 molto più ampia delle precedenti

Macro 5 accorpa data plane, manovre freeze/reassign, boot/shutdown,
osservabilità e worker locale. Sono aree con failure mode diversi. È il punto
più rischioso del programma perché concentra gran parte delle capacità per cui
l'ebook definisce operativo il sistema legacy. La recovery trasparente da morte
improvvisa del worker non va inclusa come requisito implicito: la policy
accettata è far ripartire i pochi utenti coinvolti.

**Raccomandazione:** dividere Macro 5 in gate indipendenti, almeno:

1. data plane e global store;
2. freeze/reassign, compattazione e recycle;
3. boot, dump/restore e comportamento post-crash dichiarato;
4. osservabilità e worker locale;
5. end-to-end di parità prima di Macro 6.

### P0 — Il cutover deve includere genropy-asgi

Il nuovo `SpaWorker` non espone ancora il data plane consumato da
`GenropyRegisterClient`; quel comportamento è precisamente parte di Macro 5.
Il bridge non può quindi essere migrato con un semplice cambio di classe base.

**Raccomandazione:** trattare `genropy-asgi` come consumer di accettazione di
Macro 5. Ogni seam portato nel nuovo worker va provato subito anche attraverso
il register GenroPy, evitando di scoprire il delta soltanto in Macro 6.

### P0 — Unificare sticky_cid e connection_id

L'identità di routing e quella del register devono essere la stessa oppure
legate da un mapping unico, esplicito e single-writer. Affidarsi al fatto che il
single usa un solo processo non prova il contratto.

**Raccomandazione:** fare arrivare `sticky_cid` al costruttore della connection
GenroPy come identità autoritativa, oppure introdurre nel bridge una traduzione
esplicita. Aggiungere subito un E2E con due worker: login, seconda richiesta e
secondo browser dello stesso utente devono convergere sul medesimo worker.

### P1 — Contratto del freezer da riallineare prima del soft boot

`FreezeHandler` scrive pickle direttamente sul file finale, senza file
temporaneo né rename atomico. Nel modello operativo corrente un crash può far
ripartire gli utenti coinvolti e il freezer di lavoro può essere ripulito: la
scrittura non atomica è quindi un rischio accettabile, purché un parcel parziale
non venga mai adottato come valido. Il requisito cambia soltanto se Macro 5 usa
lo stesso contenuto per soft boot o sopravvivenza dello stato al riavvio.

Prima di usare quel contenuto come input di recovery persistente vanno definiti:

- envelope versionato e validato;
- write atomica con `fsync`/rename o strategia equivalente;
- comportamento su file troncato e schema incompatibile;
- confine di fiducia del pickle, che esegue deserializzazione Python;
- differenza fra freezer operativo transitorio e snapshot di reboot.

Il punto non richiede replica continua né recupero trasparente del worker
crashato. Richiede soltanto che il confine fra mobilità ordinata e recovery di
riavvio non renda autorevole per errore un file incompleto.

### P1 — Le percentuali di memoria di più front non sono coordinate

Il nuovo disegno consente più `SpaApplicationNew`, ciascuna con il proprio
commander e una propria `memory_max_percent` riferita alla macchina. Non esiste
un coordinatore che sommi le concessioni dichiarate. L'allarme osserva il
consumo reale della macchina e ferma la crescita solo dopo il superamento della
soglia; quindi non “cattura” davvero l'over-declaration in configurazione.

**Raccomandazione:** o validare al boot la somma delle concessioni delle app SPA,
o nominare esplicitamente il comportamento come overcommit consentito e
documentare che l'allarme è reattivo, non preventivo.

### P1 — Fonti di verità documentali frammentate

La gerarchia corrente distribuisce autorità fra `SPECIFICATION.md`, ebook,
`CLAUDE.md`, file di design in `temp/`, roadmap e piani `.phased`. Il piano Macro
4 dichiara un ordine di autorità diverso da quello percepibile dalla
documentazione pubblica.

Esempi concreti:

- `docs/architecture/overview.md` è marcato “DA REVISIONARE” ma si presenta
  ancora come sintesi della fonte normativa;
- `CLAUDE.md` descrive soprattutto il legacy e dice ancora che il commander è
  “in corso” di suddivisione, mentre Macro 1–4 sono già implementate;
- l'ebook è aggiornato al 13 agosto e chiama “operativo” il comportamento del
  legacy senza distinguere ciò che è già portato nel nuovo stack;
- il piano Macro 4 dice che l'accesso filesystem passa solo da storage nodes,
  mentre `FreezeHandler` dichiara esplicitamente di essere un'eccezione e usa
  `os`, `Path` e pickle direttamente.

**Raccomandazione:** una sola matrice di parità, aggiornata per macro, con colonne
“legacy operativo”, “nuovo implementato”, “nuovo E2E”, “pubblico dopo cutover”.

### P1 — Debito di typing non misurato come delta

`mypy` è advisory, ma 124 errori rendono difficile usarlo per riconoscere una
regressione. Il nuovo front aggiunge 29 segnalazioni e il nuovo stack altre
segnalazioni su invarianti di processo/wire.

**Raccomandazione:** non serve rendere mypy bloccante subito; basta fissare un
baseline per file e vietare incrementi. Le eccezioni dovrebbero essere locali e
motivate come quelle già presenti in `pyproject.toml`.

### P2 — CI ridotta rispetto ai classifier dichiarati

Il progetto dichiara Python 3.11, 3.12 e 3.13, ma la CI esegue solo Python 3.11
su Linux. L'orchestrazione usa multiprocessing, socket Unix, `/proc` e
comportamenti dipendenti dalla piattaforma.

**Raccomandazione:** matrice minima 3.11/3.13 su Linux, più un job macOS almeno
per channel/orchestration. Mantenere uno solo dei job completi e usare subset
mirati sugli altri per rispettare il timeout.

### P2 — Due avvisi di dipendenza già visibili

La suite segnala API `websockets.legacy` e `WebSocketServerProtocol` deprecate
attraverso uvicorn. Non sono regressioni del branch, ma conviene registrarne la
compatibilità prima che un aggiornamento indiretto le trasformi in errore.

## Lettura dell'ebook rispetto al codice

L'ebook è molto efficace come vista concettuale. Descrive correttamente:

- separazione fra routing e trasporto;
- stato user-sticky e pagina come unità viva;
- motivazione dei gruppi e delle versioni conviventi;
- necessità di mobilità, freezer e supervision, con recovery proporzionata al
  failure model scelto;
- estensione futura multi-macchina/Kubernetes.

Va però letto come combinazione di tre livelli:

1. server generale già operativo;
2. orchestrazione completa oggi operativa nel legacy;
3. architettura target ancora in costruzione nel nuovo stack.

La roadmap interna del libro non mostra questo terzo asse e, dopo l'avvio del
rebuild, può far sembrare già portate capacità che sono ancora nella futura
Macro 5. Il libro non è sbagliato sul prodotto esistente, ma non è sufficiente
per misurare la prontezza del nuovo stack.

## Valutazione della direzione di design

La direzione è buona:

- l'applicazione possiede il proprio pool;
- il commander è vertice di dominio, non supervisore di ogni dettaglio;
- il gruppo è il confine naturale di versione e placement;
- il worker handler è una identità stabile sopra processi sostituibili;
- la fold è single-writer;
- il front resta stateless e non conosce il wire;
- il legacy viene rimosso in una singola fase dichiarata.

Le due decisioni che richiedono ancora verifica operativa sono:

1. più pool indipendenti sulla stessa macchina senza allocatore comune;
2. separazione esplicita fra freezer transitorio e snapshot persistente, qualora
   il soft boot debba sopravvivere al riavvio.

La mobilità via freezer è invece una decisione architetturale convincente:
unifica compattazione, sostituzione e risveglio, elimina il coordinamento
peer-to-peer e lascia la destinazione libera fino alla richiesta successiva. Il
move diretto va considerato un'ottimizzazione futura solo se misure reali
dimostrassero insufficiente questo modello, non un obiettivo di parità col
legacy.

## Sequenza consigliata

1. Chiudere Macro 4 fase 5 esattamente come pianificata, prima di aggiungere
   altro comportamento.
2. Produrre una matrice di parità legacy/nuovo e usarla come gate di Macro 5.
3. Separare formalmente freezer transitorio e snapshot di reboot, oppure
   rafforzare il formato corrente prima di soft boot/dump/restore; non estendere
   per questo il requisito alla recovery trasparente del singolo worker.
4. Decidere se la concessione memoria multi-front è preventiva o reattiva.
5. Spezzare Macro 5 in sottogate con E2E e failure injection propri.
6. Fissare il baseline mypy e allargare la matrice CI.
7. Prima di Macro 6, eseguire un test di parità su installazione reale con
   restart ordinato, morte worker, ripartenza controllata degli utenti colpiti,
   login concorrente, freeze/reassign, data plane e degradazione 503.
8. Eseguire la stessa matrice attraverso `gnrasgiserve` con almeno due worker,
   includendo identità, datachange, dbevent e global store cross-worker.
9. Pubblicare o vincolare una versione di `genropy-asgi` compatibile col nuovo
   stack.
10. Solo allora fare cutover, rename di `SpaApplicationNew`, esportazione API e
   cancellazione simultanea del legacy e delle sue sentinelle.

## Conclusione

Il repository mostra una qualità di processo superiore alla media: decisioni
esplicite, test numerosi, migrazione isolata e ownership architetturale chiara.
Il nuovo stack ha già una base credibile e il branch corrente è verde.

La lettura prudente, però, è che il progetto si trova circa a metà del rischio,
non a metà delle righe: request chain, mobilità fondamentale e login sono
pronti, mentre data plane, soft boot e integrazione delle manovre operative sono
le parti che determinano la sicurezza del cutover. La recovery trasparente da
crash del singolo worker non è un requisito: la ripartenza del gruppo ristretto
di utenti coinvolti è un rischio esplicito e ragionevole finché crash e impatto
restano rari e osservabili. La priorità dovrebbe quindi essere ridurre e
verificare Macro 5, non accelerare la rimozione del legacy.
