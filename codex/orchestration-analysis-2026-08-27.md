# Analisi dell'orchestrazione di genropy-asgi

**Data:** 27 agosto 2026  
**Destinatari:** team di sviluppo genro-asgi / genropy-asgi  
**Stato:** analisi tecnica per revisione  
**Ambito:** orchestrazione commander/worker, affinità utente, dimensionamento della pool, gestione dello stato e relazione con i benchmark Hetzner del 27 agosto 2026

## 1. Sintesi esecutiva

L'architettura di orchestrazione è coerente con la natura di GenroPy: applicazione legacy sincrona, lavoro Python soggetto al GIL e stato applicativo consistente associato a utente, connessioni e pagine.

Il vantaggio osservato nei benchmark non va attribuito genericamente ad ASGI. Deriva soprattutto da due scelte architetturali:

1. **località dello stato:** il register e gli store dell'utente vivono nello stesso processo che esegue le sue richieste;
2. **parallelismo fra processi indipendenti:** più worker forniscono più GIL, senza convergere sul daemon centrale del legacy per ogni accesso al register.

I risultati misurati sono coerenti con questo modello: il vantaggio del ponte cresce dal 29% nella baseline a un utente al 56% nella corsa con 32 utenti totali. Contestualmente cresce la memoria del ponte, perché vengono attivati ulteriori processi, e diminuisce durante lo scarico. Il comportamento è compatibile con un sistema che scambia memoria distribuita per minore contesa e maggiore parallelismo.

La base progettuale è valida. Il principale rischio non è oggi la prestazione del percorso ordinario, ma la correttezza e la prevedibilità nelle transizioni: arrivi simultanei, saturazione, nascita e chiusura dei worker, freeze/thaw, crash, ripristino e consegna di eventi fra worker.

Le priorità raccomandate sono:

1. rendere il controllo della memoria consapevole dei limiti cgroup;
2. verificare l'ammissione di molti utenti fra due fotografie di occupancy;
3. aggiungere alla occupancy segnali di coda e pressione dell'executor;
4. estendere i benchmark con fault injection e prove esplicite delle transizioni di stato;
5. consolidare una documentazione corrente, separata dai documenti storici o superati.

## 2. Fonti e criterio di lettura

L'analisi è basata su:

- implementazione corrente di `genropy-asgi`;
- implementazione corrente dell'orchestrazione in `genro-asgi` core;
- documentazione pubblicabile corrente, in particolare `docs/the-pool.rst`;
- documenti sotto `docs/internal`;
- report e CSV delle prove Hetzner del 27 agosto 2026.

Alcuni documenti in `docs/internal` sono marcati **DA REVISIONARE** o **SUPERSEDED**. Sono utili per ricostruire motivazioni e risultati storici, ma non sono stati considerati fonte autorevole quando divergono dal codice corrente.

## 3. Modello architetturale osservato

### 3.1 Front e commander

`GenropySpaApplication` è il front ASGI. La sua responsabilità specifica è limitata: monta il sito alla root, verifica la configurazione dei gruppi, espone metriche aggregate e delega al commander generico del core la gestione della pool.

Il commander mantiene la superficie globale necessaria all'instradamento:

- identità note;
- relazione connection id → utente;
- relazione pagina → connessione;
- gruppo e collocazione dell'utente;
- stato frozen/on-hold;
- global store autorevole;
- desk delle consegne e sottoscrizioni;
- stato e telemetria dei gruppi e dei worker.

Il commander è quindi il piano di controllo e la superficie di coordinamento, non il luogo in cui viene eseguito il sito legacy.

### 3.2 Worker

Ogni `GenropyWorker` è un processo che ospita:

- un `GnrWsgiSite`;
- il bridge ASGI → WSGI;
- un thread pool per il traffico sincrono;
- un thread pool separato per servizi e deposito;
- register e store locali;
- connessioni, pagine e stato degli utenti assegnati;
- metriche di processo e fotografie periodiche.

Il sito legacy rimane sostanzialmente invariato. Il worker materializza preventivamente alcune risorse lazy (`resources_dirs`, storage `gnr` e `dojo`) per evitare che la prima richiesta concorrente paghi inizializzazioni o incontri strutture parzialmente costruite.

### 3.3 Affinità per utente

Il principio fondante è che tutte le connessioni e le pagine di un utente risiedano nello stesso worker del suo stato.

Il routing usa `spa_connection_id`, creato dal sito e inviato al browser. Il commander risolve:

`connection id → utente → gruppo → worker`

L'affinità è per identità utente, non semplicemente per connessione. Questo evita che due finestre o connessioni dello stesso utente finiscano su processi diversi con store incoerenti.

### 3.4 Register daemonless

`GenropyRegisterClient` sostituisce il daemon con un adapter in-process. Le chiamate legacy al register diventano metodi espliciti che leggono i registri locali o invocano operazioni sincrone del worker sotto `dispatch_lock`.

I principali effetti sono:

- eliminazione di serializzazione e round-trip di rete per le letture locali;
- accesso diretto alle Bag in memoria;
- isolamento dello stato per worker;
- necessità dell'affinità per garantire correttezza.

Il cambiamento è particolarmente rilevante perché l'analisi storica ha misurato circa 56 operazioni di register per richiesta HTTP in un replay realistico. Il costo di ogni operazione via daemon era ridotto in assoluto ma moltiplicato per molte chiamate e, soprattutto, centralizzato per tutti i processi.

### 3.5 Stato condiviso

Lo stato è deliberatamente suddiviso:

- **per utente/pagina/connessione:** locale al worker;
- **global store:** copia autorevole unica sul commander;
- **datachange fra utenti:** consegna indirizzata attraverso il commander ai worker che ospitano pagine sottoscritte.

Il global store non è una replica eventualmente coerente: nel codice corrente il master vive sul commander. Le letture non protette fanno una CALL al master; le sezioni read-modify-write usano un lease esclusivo.

### 3.6 Nascita dei worker

La configurazione dichiara un gruppo e una factory per il motore del sito. Un template costruisce una volta il `GnrWsgiSite`, congela l'heap e genera i worker tramite `fork`.

Questa scelta riduce:

- tempo di bootstrap;
- lavoro ripetuto di costruzione del sito;
- memoria inizialmente privata, grazie al copy-on-write.

Richiede però disciplina fork-safe per connessioni database, thread, lock e librerie native.

### 3.7 Dimensionamento della pool

La pool parte con un worker di reception. Un nuovo utente viene proposto ai worker esistenti, ordinati dal più pieno al meno pieno. Ogni worker accetta o rifiuta in base a:

- stato del processo;
- numero massimo di utenti, se configurato;
- occupancy corrente più costo stimato del nuovo utente;
- riserva specifica della reception.

Se nessun worker accetta, il gruppo può crearne uno nuovo, subordinatamente alla disponibilità di memoria. In assenza di risorse risponde con `503` e `Retry-After`.

Le soglie di default osservate sono:

- ammissione fino all'80%;
- restart oltre il 95%;
- compattazione soltanto se i superstiti restano sotto il 40%;
- riserva della reception del 50%;
- costo iniziale di un nuovo utente pari al 5%;
- un posto di riserva per newcomer.

La separazione fra soglia di crescita e soglia di chiusura costituisce un'isteresi corretta e riduce il rischio di oscillazione continua.

### 3.8 Occupancy

Nel codice corrente l'occupancy è il massimo fra:

- RSS rispetto alla quota assegnata a un worker;
- CPU utilizzata rispetto a un core.

Il valore viene limitato al 100%. La CPU è calcolata confrontando fotografie successive; l'RSS viene letto da `/proc/self/status` quando disponibile.

La scelta del massimo è prudente: un worker è considerato pieno se è saturo in una qualunque delle dimensioni osservate. Tuttavia la misura non include direttamente coda del thread pool, richieste in attesa o latenza.

### 3.9 Freeze, thaw e compattazione

Un utente inattivo può essere rimosso dalla memoria attiva e serializzato nel freezer. Alla richiesta successiva viene risvegliato su un worker che dispone di spazio, non necessariamente quello originario.

La chiusura di un worker con utenti richiede una sequenza coordinata:

1. blocco degli utenti;
2. snapshot/freeze;
3. drenaggio delle richieste;
4. deposito dello stato;
5. chiusura del worker;
6. nuova assegnazione al risveglio.

Questa è la parte più complessa del sistema e quella che merita la maggiore copertura end-to-end.

## 4. Relazione con i benchmark del 27 agosto 2026

### 4.1 Disegno delle prove

Le prove Tipo 1 rigiocano la stessa sessione reale sui due stack:

- 117 chiamate utili;
- stesso ordine e stessi form;
- identificatori server-side appresi e riscritti;
- ingresso di un nuovo utente ogni 3 secondi;
- giro compresso a circa 53 secondi;
- restart e giro di scarto prima della misura;
- mediana delle latenze in intervalli di 5 secondi;
- req/s in ingresso;
- occupancy dei worker del ponte;
- CPU e memoria da `docker stats`.

### 4.2 Risultati principali

Attesa totale riportata:

| Corsa | Legacy | Ponte | Differenza |
|---|---:|---:|---:|
| 1 utente | 3.697 ms | 2.633 ms | −29% |
| 8 utenti | 39.119 ms | 23.583 ms | −40% |
| 16 utenti | 97.272 ms | 55.747 ms | −43% |
| 32 utenti | 299.056 ms | 128.087 ms | −56% |

Le corse a 32 utenti contengono 32 utenti totali, non simultanei. Con ingresso ogni 3 secondi e giro da 53 secondi il massimo concorrente è circa 18.

### 4.3 Interpretazione architetturale

La progressione del vantaggio è coerente con l'architettura:

- a un utente prevale il risparmio del register locale e del percorso più diretto;
- aumentando la sovrapposizione, i worker separati consentono parallelismo fra GIL;
- il legacy mantiene un daemon centrale raggiunto da tutti i processi;
- il ponte distribuisce sia lavoro sia register;
- req/s quasi identiche indicano che i due stack ricevono sostanzialmente lo stesso carico offerto;
- la latenza crescente del legacy suggerisce maggiore accodamento, non maggior lavoro inviato.

L'aumento della memoria del ponte è previsto: ogni nuovo processo porta una copia copy-on-write del sito che diventa progressivamente privata. Nella vista macchina la memoria del ponte scende durante lo scarico; il fenomeno è compatibile con chiusura o compattazione dei worker e non presenta, da solo, la firma di un leak monotono.

### 4.4 Cosa i benchmark non dimostrano

Le prove dichiarano correttamente di non cercare la saturazione. Non consentono quindi di concludere:

- throughput massimo del ponte;
- soglia di 503;
- comportamento al limite di memoria;
- correttezza durante un crash;
- perdita o duplicazione di datachange durante migrazione;
- durabilità del freezer;
- stabilità su ore o giorni;
- qualità del controller con utenti molto eterogenei.

## 5. Valutazione positiva

### 5.1 Allineamento fra stato e computazione

La scelta di collocare nello stesso processo lo stato e il lavoro dell'utente elimina una classe ampia di accessi remoti e semplifica la coerenza locale. È una scelta particolarmente adatta a GenroPy, dove pagine e store sono oggetti ricchi e non meri record facilmente ricostruibili.

### 5.2 Compatibilità col legacy

Il sito non deve essere riscritto. Il bridge conserva il contratto del register e traduce le strutture legacy nel modello del core. Questo riduce il rischio di adozione e consente una migrazione progressiva.

### 5.3 Separazione delle responsabilità

La distinzione fra core generico e adapter GenroPy è buona:

- il core orchestra processi, routing e stato distribuito;
- genropy-asgi ospita il sito legacy e traduce register e Bag;
- il commander non importa la logica applicativa del sito.

### 5.4 Isteresi e rifiuto esplicito

Soglie diverse per crescita e compattazione evitano il thrashing. Quando le risorse non consentono crescita, il sistema risponde esplicitamente con 503 e `Retry-After`, comportamento preferibile a timeout opachi o OOM non controllati.

### 5.5 Osservabilità già presente

Sono disponibili:

- fotografie dei worker;
- occupancy e conteggi;
- metriche aggregate;
- log degli ordini di orchestrazione;
- monitor interno;
- strumenti diagnostici opzionali.

La base necessaria per verificare il controller esiste già.

## 6. Rischi e punti da approfondire

### R1 — Memoria host invece del limite cgroup

**Priorità: alta**

Il commander determina `MemTotal` tramite `os.sysconf` e `MemAvailable` da `/proc/meminfo`. In un container questi valori possono rappresentare la macchina host, mentre il processo è soggetto a un limite cgroup più basso.

Nel laboratorio il server ha 64 GB ma il container dichiara 2 GB. Se il controller assume la memoria host, può autorizzare crescita oltre il limite reale del container e incontrare l'OOM killer prima delle proprie soglie.

**Raccomandazione:** introdurre una sorgente cgroup v2/v1 e definire:

`memoria_effettiva = min(memoria_host, limite_cgroup)`

Usare `memory.current`, `memory.max` e gli equivalenti v1 anche per allarmi e concession.

### R2 — Ammissioni consecutive su fotografia non aggiornata

**Priorità: alta**

L'ammissione confronta occupancy fotografata più costo del singolo nuovo utente. Il numero di utenti già assegnati viene usato soltanto contro `worker_max_users`; non appare sommato come occupancy provvisoria quando il limite utenti è infinito.

Fra due fotografie, diversi arrivi ravvicinati potrebbero quindi essere giudicati tutti contro la stessa occupancy. Il lock di placement impedisce la nascita simultanea incoerente di worker, ma non aggiorna necessariamente la stima di carico dopo ogni ammissione.

**Raccomandazione:** aggiungere una `reserved_occupancy` per worker o calcolare:

`occupancy_fotografata + costo_utenti_assegnati_dopo_la_foto + costo_nuovo_utente`

Prima di modificare il codice, costruire un test con 20–50 login simultanei e fotografia volutamente ritardata.

### R3 — Occupancy priva di pressione dell'executor

**Priorità: alta**

CPU e RSS non descrivono completamente un servizio sincrono in thread pool. La latenza può crescere per coda, richieste bloccate su I/O o lock e saturazione del pool prima che CPU/RSS superino le soglie.

**Raccomandazione:** valutare come componenti aggiuntivi:

- thread attivi / thread disponibili;
- profondità della coda;
- richieste in volo;
- tempo medio/p95 di attesa prima dell'esecuzione;
- latenza recente separata dal tempo di servizio.

La occupancy dovrebbe restare semplice, ma la pressione dell'executor è un segnale più prossimo al problema percepito dall'utente.

### R4 — `fullest first` con utenti eterogenei

**Priorità: media**

Riempire prima i worker caldi riduce processi e memoria, ma può concentrare utenti pesanti. La stima per utente viene appresa dopo l'osservazione; un utente che alterna fasi leggere e pesanti può essere collocato usando un costo storico poco rappresentativo.

**Raccomandazione:** confrontare su workload eterogeneo:

- fullest-first corrente;
- best-fit con costo previsto;
- least-loaded;
- fullest-first con protezione sulla coda dell'executor.

L'obiettivo non è necessariamente cambiare policy, ma verificare che il risparmio di memoria non produca p95 peggiori.

### R5 — Crash improvviso del worker

**Priorità: alta**

Freeze e shutdown ordinato salvano lo stato. Un `SIGKILL`, OOM o crash nativo può interrompere il processo prima del deposito. Il commander può rilevare la morte, ma lo stato attivo non ancora congelato potrebbe non essere ricostruibile integralmente.

**Raccomandazione:** definire e documentare esplicitamente la garanzia:

- quali parti sopravvivono a un crash;
- se l'utente deve rifare login;
- quali operazioni possono andare perse;
- come vengono ripulite mappe, code e lock;
- cosa accade ai datachange pendenti.

### R6 — Freeze/thaw e compattazione

**Priorità: alta**

La sequenza è ben ragionata e dispone di numerosi test di contratto, ma è il percorso con il maggior numero di stati intermedi. Sono possibili errori difficili da osservare: snapshot parziale, doppia adozione, hold non rilasciato, evento consegnato al vecchio worker o directory freezer incompleta.

**Raccomandazione:** aggiungere test end-to-end con interruzioni in ogni fase della sequenza, non soltanto unit test delle singole operazioni.

### R7 — Commander come punto centrale

**Priorità: media**

Il commander elimina il daemon dal percorso locale ma rimane autorevole per routing, global store e consegne cross-worker. È progettato per lavoro prevalentemente I/O-bound e leggero, ma resta un punto singolo di coordinamento e disponibilità.

**Raccomandazione:** misurare separatamente:

- throughput del solo forwarding/wire;
- latenza delle CALL al global store;
- costo del fan-out dei datachange;
- comportamento con migliaia di connessioni e pagine;
- ripristino dopo arresto non ordinato del commander.

### R8 — Sicurezza e gestione del freezer

**Priorità: media**

Il freezer contiene stato applicativo persistente dell'utente. Deve essere trattato come dato sensibile e versionato.

**Raccomandazione:** verificare:

- permessi del filesystem;
- atomicità della scrittura tramite file temporaneo + rename;
- validazione dei parcel;
- compatibilità fra versioni del codice;
- quota e garbage collection;
- comportamento su filesystem pieno;
- eventuale cifratura richiesta dal contesto operativo.

### R9 — Fork safety

**Priorità: media**

Il template pre-costruito è un'ottimizzazione importante. Il progetto ha già affrontato risorse lazy e connessioni database, ma ogni nuova dipendenza può introdurre thread, lock o handle non sicuri dopo fork.

**Raccomandazione:** mantenere una checklist esplicita per le risorse inizializzate nel template e un test che crea ripetutamente worker, esegue query, storage, export e shutdown.

### R10 — Deriva documentale

**Priorità: media**

I documenti interni descrivono più generazioni dell'architettura. Un esempio è il global store, descritto in un documento superato come replica eventualmente coerente e nel codice corrente come master unico sul commander.

**Raccomandazione:** aggiungere a ogni documento:

- stato autorevole/storico;
- versione del core cui si riferisce;
- link al documento sostitutivo;
- data dell'ultima verifica contro il codice.

## 7. Piano di verifica raccomandato

### 7.1 Livello A — percorso ordinario ripetibile

Per ogni configurazione eseguire almeno cinque corse, alternando l'ordine legacy/ponte. Riportare mediana delle corse e intervallo di confidenza.

Metriche:

- latenza accoppiata per `user/round/seq`;
- p50, p90 e p95;
- req/s offerte e completate;
- `late_ms` del driver;
- errori e timeout;
- CPU, RSS e cgroup memory;
- worker vivi e utenti per worker;
- coda/pressione executor.

### 7.2 Livello B — transizioni controllate

Scenari:

1. 50 login simultanei;
2. crescita fino alla nascita di 2, 3 e 4 worker;
3. mantenimento al plateau per almeno 5 minuti;
4. uscita graduale e compattazione;
5. freeze di utenti inattivi;
6. risveglio su worker differente;
7. riavvio ordinato dell'intero servizio.

Invarianti da verificare:

- un utente attivo ha un solo worker autorevole;
- nessuna richiesta viene inviata a un worker in uscita;
- nessun hold resta orfano;
- nessun utente supera la capacità dichiarata;
- il numero di worker non oscilla vicino alle soglie;
- store e pagine sopravvivono a freeze/thaw.

### 7.3 Livello C — fault injection

Durante richieste reali e datachange:

- `SIGTERM` al worker;
- `SIGKILL` al worker;
- arresto del commander;
- risposta mancata sul wire;
- freezer temporaneamente non scrivibile;
- filesystem pieno;
- timeout del global-store lease;
- morte del worker mentre detiene il lease;
- morte durante freeze e durante adoption.

Per ogni caso dichiarare l'esito atteso prima del test: recupero trasparente, 503 temporaneo, perdita della sessione o necessità di nuovo login.

### 7.4 Livello D — correttezza distribuita

Con almeno due worker:

- utente A modifica un record, utente B sottoscritto riceve una sola notifica;
- datachange durante migrazione di B;
- più pagine dello stesso utente ricevono lo stesso aggiornamento secondo contratto;
- ordine e coalescenza delle notifiche;
- global store con letture e read-modify-write concorrenti;
- scadenza e scarto degli eventi non consegnati;
- restart con eventi pendenti.

### 7.5 Livello E — durata

Eseguire una prova di almeno 8–24 ore con churn continuo e plateau periodici.

Controllare:

- crescita RSS per worker;
- memoria restituita dopo compattazione;
- directory freezer e file orfani;
- processi zombie;
- mappe commander senza proprietario;
- connessioni database;
- errori di lock;
- tempi di nascita dei worker;
- frequenza di 503 e restart.

## 8. Migliorie alla telemetria

Si raccomanda di aggiungere o rendere direttamente esportabili:

- `worker_occupancy_percent` con componenti separate;
- `worker_cpu_percent`;
- `worker_rss_bytes`;
- `worker_cgroup_memory_current_bytes`;
- `worker_users_placed`;
- `worker_http_inflight`;
- `worker_executor_active_threads`;
- `worker_executor_queue_depth`;
- `worker_request_queue_wait_seconds`;
- `worker_birth_seconds`;
- `pool_worker_count`;
- `pool_assignments_total`;
- `pool_assignment_refusals_total{reason=...}`;
- `pool_freeze_total`, `pool_thaw_total`, `pool_transfer_failures_total`;
- `pool_503_total{reason=saturated|broken}`;
- `commander_global_store_call_seconds`;
- `commander_delivery_queue_depth`;
- `commander_undelivered_events_total`.

Nei report, occupancy aggregata e componenti dovrebbero essere entrambe disponibili. Un valore unico è utile al controller; le componenti sono necessarie per capire perché abbia deciso.

## 9. Azioni consigliate, ordinate

### P0 — prima di considerare conclusa la validazione

1. Verificare e correggere la memoria rispetto ai limiti cgroup.
2. Scrivere il test di burst fra due fotografie di occupancy.
3. Definire formalmente la garanzia su crash improvviso del worker.
4. Eseguire test cross-worker di datachange durante freeze/compattazione.

### P1 — robustezza e capacità operativa

1. Aggiungere telemetria dell'executor.
2. Eseguire churn con plateau stabile e più seed.
3. Aggiungere fault injection sistematica.
4. Eseguire prova di durata.
5. Consolidare la documentazione autorevole.

### P2 — ottimizzazione

1. Confrontare policy di placement su utenti eterogenei.
2. Calibrare soglie e costo iniziale dell'utente sui dati reali.
3. Valutare una stima per utente basata su EWMA di CPU, queue wait e memoria.
4. Misurare il commander come possibile tetto futuro.

## 10. Giudizio conclusivo

L'orchestrazione non appare come un semplice wrapper ASGI intorno al legacy. È una ridistribuzione consapevole della proprietà dello stato:

- il worker possiede ciò che serve rapidamente e coerentemente all'utente;
- il commander possiede ciò che deve essere globale o instradato;
- il freezer rende spostabile ciò che normalmente è locale;
- la pool usa processi per superare il limite del GIL.

Questa impostazione è adatta al problema e i benchmark ne supportano la tesi principale. Il vantaggio crescente con il numero di utenti è tecnicamente credibile e coerente con la rimozione del daemon centrale.

Il passo successivo non dovrebbe essere cercare subito percentuali prestazionali ancora migliori. Dovrebbe essere dimostrare che tutte le transizioni di proprietà dello stato sono sicure sotto concorrenza, saturazione e guasto. Se burst admission, cgroup memory, freeze/thaw, crash recovery e consegna cross-worker superano prove ripetibili e avverse, l'architettura può essere considerata non soltanto veloce, ma operativamente matura.

## Appendice A — File principali esaminati

### genropy-asgi

- `src/genropy_asgi/spa/genropy_spa_application.py`
- `src/genropy_asgi/spa/genropy_worker.py`
- `src/genropy_asgi/spa/config.py`
- `src/genropy_asgi/siteregister/siteregister_client.py`
- `docs/internal/architecture.rst`
- `docs/internal/performance_analysis.md`
- `docs/internal/pool-internals.rst`
- `docs/the-pool.rst`

### genro-asgi core

- `src/genro_asgi/spa/orchestration/spa_commander.py`
- `src/genro_asgi/spa/orchestration/group_handler.py`
- `src/genro_asgi/spa/orchestration/worker_handler.py`
- `src/genro_asgi/spa/orchestration/spa_worker.py`
- `src/genro_asgi/spa/orchestration/freeze_handler.py`
- `src/genro_asgi/spa/orchestration/template_entry.py`
- `src/genro_asgi/spa/orchestration/envelope_handler.py`

### Benchmark

- `benchmarks/session_bench.py`
- `benchmarks/churn_driver.py`
- report Tipo 1 e Tipo 2 del 27 agosto 2026;
- CSV per-call, per-second e docker stats associati.

## Appendice B — Nota sulla terminologia

- **Legacy:** gunicorn + gnrdaemon/register centrale.
- **Ponte:** genropy-asgi sopra genro-asgi, con register locale e pool sticky.
- **Reception:** worker più anziano del gruppo, con capacità riservata per nuovi ingressi.
- **Occupancy:** massimo fra le componenti di pressione misurate per il worker.
- **Freeze:** serializzazione dello stato utente fuori dalla memoria attiva.
- **Thaw/adoption:** ripristino dello stato congelato su un worker disponibile.
- **Compattazione:** chiusura di un worker quando gli altri possono assorbirne gli utenti mantenendo riserva e soglie.
