# Architettura di deployment: gruppi, UV, subcommander e Kubernetes

Data: 19 agosto 2026  
Stato: proposta architetturale per sessione di analisi e ratifica  
Perimetro: evoluzione dell'orchestrazione user-sticky di `genro-asgi`

## 1. Obiettivo

Portare l'attuale modello di orchestrazione da un singolo server con worker
locali a un deployment Kubernetes, senza delegare a Kubernetes le decisioni
applicative di placement e scaling.

Il modello target conserva gli stessi concetti a ogni scala:

```text
Server / Front
    └── Root Commander
            ├── Group
            │     └── Worker
            └── Subcommander
                    ├── Group
                    │     └── Worker
                    └── Subcommander (eventuale estensione futura)
```

Il commander resta l'unico proprietario delle policy. Kubernetes crea,
isola, esegue e osserva i container, ma non decide quanti worker applicativi
servono, quali utenti ospitano o quale versione deve ricevere traffico.

## 2. Stato delle decisioni

### Decisioni già assunte

- L'utente è l'unità primaria di affinità e placement.
- Tutte le pagine e connessioni dello stesso utente vivono sul medesimo worker.
- Il front resta stateless.
- Il gruppo è un confine di policy, risorse e versione applicativa.
- Il numero dei worker deriva dall'occupazione e non da un target statico.
- La mobilità usa `hold → freeze → reassign → unfreeze`.
- Il trasferimento diretto worker-to-worker è escluso per ridurre la complessità.
- Un crash improvviso del worker può far ripartire il numero limitato di utenti
  coinvolti; è un rischio operativo accettato.
- In Kubernetes il commander, non HPA, decide crescita e riduzione dei worker.
- UV è lo strumento previsto per produrre ambienti Python riproducibili.

### Orientamenti da consolidare

- Il commander può possedere direttamente gruppi oppure subcommander.
- Redis è il candidato naturale per freezer e coordinamento condivisi nel
  deployment multi-container o multi-nodo.
- Un worker Kubernetes è un Pod controllato logicamente dal commander.
- Un gruppo di versione dovrebbe riferirsi a un'immagine immutabile, costruita
  con un ambiente UV, invece di creare il virtualenv durante l'avvio del Pod.

### Decisioni ancora da ratificare

- Il significato concreto di un subcommander: shard, nodo, zona, tenant,
  applicazione o combinazione di questi elementi.
- Se il root commander attraversa il data path di ogni richiesta o risolve una
  destinazione che il front contatta direttamente.
- Persistenza e ricostruzione della directory `user → subcommander`.
- Protocollo di lease e fencing fra commander e subcommander.
- Forma delle risorse Kubernetes: Pod diretti, CRD dedicata o controller
  separato.
- Failure model di root commander e subcommander.

## 3. Principi architetturali

### 3.1 Un solo decisore per dominio

Ogni risorsa deve avere un solo policy owner:

```text
Root Commander  → subcommander, budget e assegnazione del ramo
Subcommander    → gruppi e worker del proprio dominio
Group           → capacità, placement e lifecycle dei propri worker
Worker          → stato vivo degli utenti assegnati
Kubernetes      → realtà infrastrutturale osservata
```

Il root non crea o termina direttamente un worker posseduto da un
subcommander. Kubernetes non modifica autonomamente il numero dei worker.

### 3.2 Desired state e observed state

Il commander non deve operare come client imperativo fire-and-forget. Deve
riconciliare continuamente:

```text
desired state deciso dal commander
              ↕
observed state letto dalla Kubernetes API
              ↓
azione idempotente necessaria
```

Esempio:

```text
Desired: il gruppo stable deve conservare capacità per due newcomer.
Observed: stable_0002 è in terminating e stable_0003 non è ancora ready.
Action: non chiudere altri worker; attendere stable_0003 e rivalutare.
```

Ogni decisione viene ricalcolata su una fotografia nuova. Non si porta un
piano obsoleto attraverso più cicli di riconciliazione.

### 3.3 Affinità forte, mobilità esplicita

L'affinità user-sticky è forte durante la residenza, ma non permanente. Un
utente cambia worker soltanto attraverso una transizione osservabile:

```text
RESIDENT
   → ON_HOLD
   → FROZEN
   → UNASSIGNED
   → ASSIGNED
   → ADOPTING
   → RESIDENT
```

Non devono esistere due copie residenti e autoritative dello stesso utente.

## 4. Gruppi e versioni applicative

### 4.1 Il gruppo come grammar immutabile

Un gruppo raccoglie worker equivalenti per:

- versione applicativa;
- immagine container;
- versione Python;
- dipendenze;
- classe worker;
- configurazione applicativa;
- quote e soglie di occupazione;
- policy di freeze;
- compatibilità del parcel.

La configurazione effettiva del gruppo deve essere identificabile con un
digest. Due worker dello stesso gruppo devono nascere dalla stessa grammar.

```text
group stable
    image: registry.example/erp@sha256:...
    python: 3.12
    parcel_schema: erp-user-v4

group canary
    image: registry.example/erp@sha256:...
    python: 3.13
    parcel_schema: erp-user-v5
```

### 4.2 Stable, blue/green e canary

L'orchestratore rende disponibili i gruppi; la policy applicativa sceglie la
coorte. Il motore non deve necessariamente implementare percentuali canary.

Possibili criteri applicativi:

- tenant;
- utente;
- ruolo;
- feature flag;
- lista esplicita;
- hash stabile dell'identità;
- gruppo indicato dall'avatar.

Una volta assegnato, l'utente resta nel gruppo finché una manovra esplicita non
decide altrimenti. Non è previsto fallback silenzioso fra versioni.

### 4.3 Lifecycle di una versione

```text
BUILD
  → REGISTERED
  → WARMING
  → ACCEPTING
  → DRAINING
  → RETIRED
```

Procedura raccomandata:

1. UV risolve e sincronizza l'ambiente durante la build.
2. La pipeline produce un'immagine immutabile e la pubblica per digest.
3. Il commander registra il nuovo gruppo senza assegnargli utenti.
4. Avvia la reception e ne verifica readiness e compatibilità.
5. L'applicazione assegna la coorte prevista.
6. Il gruppo viene osservato prima della promozione.
7. La vecchia versione smette di accettare nuove assegnazioni.
8. Gli utenti residenti vengono drenati secondo la policy di compatibilità.
9. Il commander ritira gli ultimi worker e deregistra il gruppo.

Se i parcel non sono compatibili fra versioni, il passaggio di gruppo richiede
una ripartenza controllata dell'utente oppure una migrazione applicativa
esplicita. Il logout è preferibile a un unpickle incompatibile.

## 5. Ruolo di UV

### 5.1 Deployment locale

Nel deployment a processi locali, un gruppo può indicare un proprio executable:

```text
UV → virtualenv del gruppo → python -m worker_entry
```

Questo permette a stable e canary di convivere sullo stesso host con
interpreti e dipendenze differenti.

### 5.2 Deployment Kubernetes

Nel deployment Kubernetes UV dovrebbe operare principalmente in build time:

```text
pyproject + uv.lock
        ↓
uv sync --frozen
        ↓
immagine worker immutabile
        ↓
Pod del gruppo
```

Non è raccomandata la creazione o l'aggiornamento del virtualenv al boot del
Pod di produzione. L'immagine deve essere riproducibile, verificabile e
rollbackabile senza dipendere dalla rete al momento dell'avvio.

### 5.3 Contratto di versione

Ogni worker presenta al commander almeno:

- image digest;
- versione applicativa;
- versione del protocollo;
- versione del parcel;
- versione Python;
- group id;
- worker handle e generation.

La readiness applicativa viene concessa soltanto se il contratto corrisponde
alla grammar registrata dal gruppo.

## 6. Gerarchia dei commander

### 6.1 Root commander

Il root possiede:

- directory `user → ramo`;
- budget concessi ai subcommander;
- lifecycle dei subcommander;
- stato globale dell'applicazione;
- log delle decisioni gerarchiche;
- policy di accoglienza fra rami;
- controllo delle crisi che superano il singolo gruppo.

Il root non deve duplicare la mappa interna `user → group → worker` di ogni
subcommander.

### 6.2 Subcommander

Il subcommander possiede:

- i gruppi del proprio dominio;
- placement degli utenti del ramo;
- lifecycle dei worker;
- quote ricevute dal parent;
- stato `running`, `saturated`, `draining`, `broken`;
- riconciliazione Kubernetes delle proprie risorse.

Un subcommander è una vera autorità delegata, non un proxy trasparente.

### 6.3 Directory gerarchica

La catena minima di risoluzione è:

```text
root:          user → subcommander
subcommander:  user → group
group:         user → worker_handle
worker handle: generation → Pod UID / connessione attiva
```

Ogni livello scrive soltanto la propria mappa. Il parent conosce il figlio
responsabile, non i dettagli sotto di esso.

### 6.4 Trasferimento fra subcommander

```text
1. Il root marca l'utente ON_HOLD con transfer epoch N.
2. Il subcommander sorgente congela il parcel sul backend condiviso.
3. La sorgente rilascia l'ownership per epoch N.
4. Il root assegna il subcommander destinazione con epoch N+1.
5. La destinazione assegna gruppo e worker.
6. Il worker adotta atomicamente il parcel.
7. La destinazione conferma RESIDENT.
8. Il root rilascia le richieste in attesa.
```

La destinazione non può adottare prima del rilascio della sorgente. Una
generation o epoch precedente non può tornare autoritativa.

## 7. Kubernetes come runtime controllato

### 7.1 Responsabilità del commander

- decidere crescita e riduzione;
- scegliere immagine e gruppo;
- creare il Pod tramite API;
- attendere presentazione e readiness;
- ordinare drain e quit;
- decidere replacement e retirement;
- interpretare crash, OOM, eviction e timeout;
- registrare motivazione e risultato di ogni ordine.

### 7.2 Responsabilità di Kubernetes

- scheduling infrastrutturale sul nodo;
- isolamento CPU, memoria e filesystem;
- networking e DNS;
- avvio e terminazione del container;
- reporting di Pod phase, readiness, OOM ed eviction;
- applicazione di quota, RBAC e network policy;
- gestione di node loss e manutenzione del cluster.

Lo scheduling infrastrutturale del Pod su un nodo non confligge con il
placement applicativo dell'utente sul worker: sono decisioni su piani diversi.

### 7.3 Controller da non sovrapporre

Per i worker controllati dal commander non devono agire contemporaneamente:

- HPA;
- replica count di un Deployment gestito da GitOps;
- VPA con restart automatico;
- operator che ricreano autonomamente i worker;
- script esterni di autoscaling.

VPA può essere usato in modalità raccomandazione. Alert e policy amministrative
possono osservare, ma non mutare la cardinalità senza passare dal commander.

### 7.4 Risorsa Pod e restart

La prima implementazione può creare Pod diretti con:

```text
restartPolicy: Never
```

La morte diventa così un fatto osservabile. Il commander decide se generare un
nuovo Pod, restringere il gruppo o dichiararlo broken. Una futura CRD può
rendere più esplicito il desired state, ma non è necessaria per il primo
vertical slice.

### 7.5 Worker handle e incarnation

Il worker logico è distinto dal Pod:

```text
worker_handle = stable_0003
generation    = 18
pod_uid       = 7d4a...
```

Ogni comando e messaggio porta `worker_handle` e `generation`. Dopo l'avvio
della generation 18, qualunque messaggio della 17 viene respinto. Questo è il
fencing minimo contro Pod o connessioni rientrati dopo una partizione.

Etichette Kubernetes raccomandate:

```text
genro.app
genro.root_commander
genro.subcommander
genro.group
genro.worker_handle
genro.generation
genro.version
```

## 8. Risorse e autoscaling

### 8.1 Cascata dei budget

```text
cluster/namespace budget
        ↓
root commander concession
        ↓
subcommander budget
        ↓
group quota
        ↓
worker request/limit e occupancy threshold
```

Il parent concede un budget al figlio; non decide il dettaglio dei suoi worker.
Il figlio non può crescere oltre la concessione anche se Kubernetes avrebbe
risorse fisiche disponibili.

### 8.2 Fusibili

Il numero dei worker resta una conseguenza del carico. Sono comunque necessari
limiti di sicurezza, distinti dai target:

- massimo Pod per gruppo e subcommander;
- massimo Pod creati per intervallo;
- backoff dopo launch failure;
- quota CPU/memoria del namespace;
- limite socket/connessioni;
- limite della coda di richieste in hold.

Questi limiti proteggono da misure errate e loop di riconciliazione, senza
trasformarsi nella policy ordinaria di dimensionamento.

### 8.3 Compattazione

Il commander chiude un worker soltanto se:

- non è la reception necessaria;
- gli altri worker possono riassorbire il carico stimato;
- resta integra la riserva dei newcomer;
- il backend del freezer ha spazio;
- il Pod successore, quando necessario, è ready;
- nessun'altra manovra possiede gli utenti interessati.

Gli utenti eccezionalmente grandi possono essere classificati `oversized` e
rendere il worker temporaneamente non drenabile, senza dichiararlo guasto.

## 9. Freezer e backend condiviso

### 9.1 Separazione fra codec e backend

```text
FreezeCodec
    └── PickleCodec

FreezeBackend
    ├── FilesystemBackend
    └── RedisBackend
```

Pickle conserva fedelmente lo stato Python. Il backend decide dove vive il
payload e quali primitive atomiche sono disponibili.

### 9.2 Filesystem

Adatto a:

- sviluppo;
- deployment locale;
- singolo commander e worker sullo stesso host;
- freezer transitorio.

Richiede file temporaneo, rename atomico, header e gestione dei parcel
incompleti.

### 9.3 Redis

Adatto a:

- Pod su nodi diversi;
- trasferimento fra subcommander;
- TTL e reaping;
- claim e consume atomici;
- ricostruzione dopo restart dei componenti;
- pending events durante la mobilità.

Redis sostituisce il backend, non il codec: il payload ordinario può restare
pickle. Le operazioni minime sono:

```text
put(user, epoch, payload, metadata, ttl)
claim(user, epoch, worker_generation)
consume(user, epoch, worker_generation)
release(user, epoch, worker_generation)
drop(user, epoch)
```

`claim` e `consume` devono essere atomici. Un claim con epoch o generation non
corrente viene respinto.

### 9.4 Parcel grandi

Per pochi KB Redis è adatto. Per eccezioni molto grandi:

```text
Redis        → metadata, lease, checksum e riferimento
Object store → payload
```

DuckDB è utile quando il DataFrame è già dato applicativo persistente e
interrogabile. In quel caso il parcel dovrebbe contenere un riferimento alla
tabella o alla query, non usare DuckDB come passaggio di serializzazione
generale.

### 9.5 Envelope del parcel

Prima del payload pickle:

```text
format_version
application
application_version
parcel_schema
source_group
user
transfer_epoch
created_at
payload_size
checksum
codec
```

Il worker valida l'envelope prima di deserializzare. Pickle viene accettato
soltanto da backend e producer fidati.

## 10. Comunicazione e rete

### 10.1 Connessione del worker

In Kubernetes è preferibile che il worker apra una connessione outbound verso
il commander o subcommander che lo possiede. Questo evita di dipendere dal Pod
IP e conserva il pattern di presentazione già esistente.

```text
Worker Pod → Commander Service → present(worker, group, generation, versions)
```

Il commander accetta la connessione soltanto se trova una incarnation attesa
con le stesse credenziali e generation.

### 10.2 Sicurezza

- ServiceAccount distinto per commander e worker;
- RBAC del commander limitato al namespace e alle risorse necessarie;
- worker senza permesso di creare o eliminare Pod;
- autenticazione reciproca del canale;
- NetworkPolicy fra front, commander, subcommander, worker e Redis;
- secret montati per ruolo e non condivisi universalmente;
- image digest e admission policy verificabili.

## 11. Failure model

### 11.1 Worker crash

È un evento straordinario ma previsto. Kubernetes riferisce il fatto, il
commander rimuove l'incarnation e crea il replacement se la capacità lo
richiede. Gli utenti residenti non congelati possono ripartire.

Non è richiesta replica continua dello stato. Devono essere misurati:

- causa del crash;
- utenti coinvolti;
- tempo di replacement;
- frequenza per gruppo e versione;
- eventuali parcel orfani.

### 11.2 Worker drain ordinato

Il commander impedisce nuove assegnazioni, marca gli utenti in trasferimento,
attende freeze e uscita, poi elimina il Pod. `terminationGracePeriodSeconds`
deve coprire il budget di drain. Un `preStop` può notificare il worker, ma la
decisione e lo stato della manovra restano del commander.

### 11.3 Subcommander crash

Da ratificare. Contratto raccomandato:

- il root interrompe nuove assegnazioni al ramo;
- la directory persistente conserva l'ownership precedente con lease scaduto;
- il root ordina a Kubernetes una nuova incarnation del subcommander;
- il nuovo processo ricostruisce gruppi e worker osservando API e backend;
- worker con generation valida si ripresentano;
- gli utenti non ricostruibili ripartono in modo controllato;
- nessun secondo subcommander prende autorità prima del fencing del precedente.

### 11.4 Root commander crash

Il container server/commander viene riavviato da Kubernetes. Il soft boot deve
ricostruire almeno:

- subcommander registrati;
- directory degli utenti o sua derivazione;
- worker incarnation osservate;
- parcel validi;
- manovre interrotte e relative epoch.

Non è obbligatoria inizialmente una coppia active/active. È invece obbligatorio
che un root riavviato non possa accettare come corrente una incarnation obsoleta.

### 11.5 Eventi infrastrutturali

Node loss, eviction, OOM e rifiuto per quota non sono decisioni concorrenti di
Kubernetes: sono fatti esterni. Il commander li osserva, li registra e decide
la risposta applicativa.

## 12. Data path: alternative da analizzare

### Alternativa A — Root nel data path

```text
Front → Root → Subcommander → Worker
```

Vantaggi:

- una sola porta di ingresso;
- directory sempre autoritativa;
- barrier e rifiuti centralizzati.

Svantaggi:

- hop aggiuntivi;
- root come collo di bottiglia;
- blast radius maggiore.

### Alternativa B — Risoluzione e inoltro diretto

```text
Front → Root resolve(user) → Worker/Subcommander
Front → destinazione finché placement epoch resta valido
```

Vantaggi:

- data path più corto;
- root prevalentemente control plane.

Svantaggi:

- cache e invalidazione del placement;
- fencing visibile anche al front;
- gestione più complessa delle richieste durante il move.

### Raccomandazione iniziale

Usare l'alternativa A nel primo vertical slice per preservare la semantica
attuale. Misurare il root prima di introdurre cache e routing diretto. La
separazione fra API di risoluzione e protocollo worker deve comunque evitare
che l'alternativa A diventi irreversibile.

## 13. Osservabilità

Ogni decisione deve produrre una riga strutturata con:

- `decided_by`;
- `order`;
- `subject`;
- `reason`;
- fotografia delle risorse;
- placement epoch;
- desired e observed state;
- risultato e durata.

Metriche minime:

- worker desired/running/ready/terminating/failed;
- placement e utenti per livello;
- richieste refused e tempo on-hold;
- dimensione e durata freeze/unfreeze P50/P95/P99;
- Pod start e readiness latency;
- OOM, eviction e crash;
- reconcile lag ed errori Kubernetes API;
- utilizzo delle concessioni root/subcommander/group;
- utenti ripartiti dopo failure;
- numero e durata delle manovre in corso.

## 14. Percorso di implementazione raccomandato

### Fase K1 — Runtime astratto

- Estrarre `WorkerRuntime` dal `WorkerHandler`.
- Conservare `LocalProcessRuntime` come sentinella.
- Implementare un fake runtime deterministico per i test.

### Fase K2 — Kubernetes vertical slice

- Un root commander.
- Un gruppo.
- Worker Pod diretto con `restartPolicy: Never`.
- Presentazione outbound e fencing per generation.
- Start, readiness, quit e crash osservato.

### Fase K3 — Backend condiviso

- Separare codec e backend del freezer.
- Implementare Redis con claim/consume atomico ed epoch.
- Provare freeze su un worker e adoption su un Pod differente.

### Fase K4 — Gruppi di versione

- Immagini costruite con UV.
- Stable e canary simultanei.
- Policy applicativa di assegnazione.
- Drain e retirement della vecchia versione.

### Fase K5 — Primo subcommander

- Root con un gruppo diretto e un subcommander.
- Directory `user → ramo`.
- Budget delegato.
- Trasferimento via freezer condiviso.
- Crash e ricostruzione del subcommander.

### Fase K6 — Failure injection e hardening

- kill del worker;
- node loss simulata;
- eviction durante il freeze;
- restart del subcommander;
- restart del root;
- Redis temporaneamente indisponibile;
- Kubernetes API in timeout;
- Pod vecchio che tenta di ripresentarsi;
- immagine o parcel incompatibili;
- quota namespace esaurita.

## 15. Criteri di accettazione architetturale

Il disegno può considerarsi validato quando:

1. esiste un solo owner dimostrabile per ogni utente;
2. nessun controller esterno modifica la cardinalità dei worker;
3. ogni ordine Kubernetes è idempotente e riconciliabile;
4. una generation obsoleta non può essere riammessa;
5. il freeze può essere adottato su un altro nodo una volta sola;
6. stable e canary convivono con immagini e parcel schema dichiarati;
7. il drain non perde utenti in una partenza ordinata;
8. un worker crashato coinvolge soltanto i propri utenti;
9. il restart di un subcommander non crea doppia ownership;
10. il root può ricostruire uno stato coerente dopo il proprio restart;
11. quote e fusibili impediscono una crescita incontrollata;
12. ogni decisione è ricostruibile dal log di orchestrazione.

## 16. Valutazione

La direzione `commander → subcommander → group → worker` è coerente con
l'architettura esistente perché estende ricorsivamente ownership e placement,
senza introdurre un secondo scheduler applicativo.

La scelta di lasciare al commander tutte le decisioni e a Kubernetes la realtà
infrastrutturale evita conflitti con HPA e conserva una sola fonte di policy.
Il rischio principale non è Kubernetes, ma la distribuzione dell'autorità:
directory, lease, epoch e fencing devono essere parte del modello fin dal primo
subcommander.

Se questi invarianti vengono rispettati, il passaggio al cluster non richiede
di abbandonare user-sticky, gruppi, freezer o single-writer. Richiede di rendere
espliciti i confini che sul singolo processo erano garantiti implicitamente
dalla memoria e dal sistema operativo.
