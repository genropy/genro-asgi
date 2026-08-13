# Fase 6 — Rassegna di coerenza dei deliverable dell'audit

Rassegna incrociata dei sei file scritti dalle fasi 1-5, con tre controlli
eseguiti (non letti): risoluzione di ogni riferimento `file:riga` contro
l'albero corrente, copertura autorità → registri → schede, e un controllo
semantico che verifica che l'àncora citata accanto a un simbolo cada davvero
dentro o vicino a quel simbolo. Nessun verdetto è stato riempito; nessuna scheda
è stata aggiunta, rimossa o riscritta nella sostanza.

Prosa in italiano come gli altri deliverable dell'audit (materiale da
walkthrough: la sezione «Segnalato al titolare» si legge accanto ai registri).

---

## Auto-corretto

Sette correzioni, tutte della stessa specie: un **numerale che contraddiceva la
propria lista di àncore**, verificata contro l'albero. In nessun caso cambia un
rilievo, una proposta, una motivazione o un verdetto.

| # | File | Cosa | Perché |
|---|------|------|--------|
| 1 | `audit/zone_tests.md` (T-D2) | «I sette chiamanti di test» → «Gli otto chiamanti di test» | La riga elenca **otto** àncore (`tests/test_spa_move.py:2184, 2207, 2233, 2467, 2503, 2517, 2543, 2677`) e l'albero ne ha otto: `grep -n 'recycle_worker(' tests/test_spa_move.py` dà 8 chiamate + 1 assegnazione monkeypatch (`2407`, correttamente esclusa). |
| 2 | `audit/slimming_ledger.md` (L15) | idem, stessa frase | Stessa lista di otto àncore, stessa verifica. |
| 3 | `audit/zone_tests.md` (T-D5) | «sette chiamanti di `worker_time_to_limit`» → «otto» | Le àncore elencate sono otto (7 in `tests/test_spa_evaluator.py` + `tests/test_spa_move.py:2357`) e l'albero ne conferma otto. |
| 4 | `audit/slimming_ledger.md` (L16) | «Sette chiamanti nella suite» → «Otto» | Stessa lista, stessa verifica. |
| 5 | `audit/zone_tests.md` (sezione C) | «**17 chiamanti**» di `settled_at` → «**16 chiamanti**» | Le àncore elencate sono 16 e l'albero ne ha 16: il 17 nasce da un `grep -c 'settled_at('` che conta anche la riga di definizione (`tests/test_spa_move.py:78`). |
| 6 | `audit/slimming_ledger.md` (Scartate, sezione C) | idem | Stessa origine, stessa correzione. |
| 7 | `audit/zone_recycling_code.md` (Conteggio) | «32 schede … **32 voci, 32 in attesa di verdetto**» → 33 | L'enumerazione della frase stessa somma 33 (6+10+7+D8+5+3+1), il file ha 33 intestazioni di scheda e 33 caselle di verdetto, e la contabilità del libro mastro (37 + 24 = 61 = 33+12+16) presuppone 33. |

Due correzioni minori di forma, nello stesso spirito:

| # | File | Cosa | Perché |
|---|------|------|--------|
| 8 | `audit/zone_tests.md` (sezione C) | «ha quattro membri: `__init__`, `start`, `add_worker`, `stop` e la property `names`» → «ha quattro metodi — … — più la property `names`» | La frase annunciava quattro e ne elencava cinque. L'albero: quattro metodi (`tests/test_spa_move.py:157, 164, 169, 182`) più la property (`188`). Il fatto non cambia. |
| 9 | `audit/zone_tests.md` (Conteggio) | «**14 schede**, tutte con verdetto VUOTO» → «**12 schede**», con le due conclusioni trasversali dichiarate esplicitamente non-schede | Il file ha 12 schede e 12 caselle di verdetto (T-D1..T-D7, sezione B, sezione C, TS1..TS3); il 14 le sommava alle due conclusioni trasversali, che non hanno casella. La contabilità del libro mastro conta 12 per questo file. Vedi la segnalazione 1 qui sotto. |

---

## Segnalato al titolare (non corretto)

1. **Il 14 della fase 3 sopravvive nella nota di piano.** La correzione 9
   allinea il deliverable a 12 schede, ma la nota `> Done:` della fase 3 in
   `plan.md` dice ancora «14 cards» — e le note delle fasi chiuse sono fuori dal
   perimetro di questa fase (`Files:` ammette solo `audit/*.md` e questo file).
   *Azione suggerita*: nessuna, se il titolare legge 12 come «schede con
   verdetto» e 14 come «schede + conclusioni»; altrimenti l'allineamento della
   nota va fatto in finalize.

2. **Le 11 affermazioni dell'ebook mai portate a scheda restano una decisione di
   perimetro, non un difetto risolvibile qui.** Sono E2, E15-E18, E23-E25, B6,
   B8, B9 (zone `tests` e `recycling-code`), registrate dalla fase 5 nella §5 di
   `audit/reconciliation_record.md` con due opzioni e una casella di verdetto.
   La rassegna conferma il fatto — nessuna delle 11 compare in una scheda delle
   fasi 2-4 — e conferma che portarle a scheda ora sarebbe **nuovo lavoro di
   audit**, non una correzione di coerenza. *Azione suggerita*: la §5 è la prima
   voce di perimetro del walkthrough, insieme a L1 e R4.

3. **Quattro coppie «simbolo + àncora» che il controllo semantico segnala e che
   sono corrette.** Registrate perché il controllo è riproducibile e chi lo
   rieseguisse le rivedrebbe: `wait_until` accanto a `commander.py:3177`
   (L21 — è il nome **proposto** per il helper fuso, l'àncora è la guardia
   esistente dentro `wait_worker_ready`); `RegisterRegistry` accanto a
   `register_registry.py:157` e `OccupancyEvaluator` accanto a
   `evaluator.py:288` (nomi di **classe**, àncore dentro un loro metodo);
   `LocalPool` accanto a `tests/test_spa_move.py:78` (la frase nomina la classe
   proprio per **negare** che `settled_at` le appartenga). *Azione suggerita*:
   nessuna.

4. **Nessun difetto di sostanza trovato.** I risultati degli esperimenti di
   strip coincidono fra `audit/zone_tests.md` e le voci L14-L20 del libro
   mastro (cinque difese incementate a 249/249, D1 e D7 con un test ciascuna);
   ogni voce `L` dichiara schede di origine che esistono; ogni voce `R` dichiara
   un punto di fedeltà, un nome di battesimo o un'affermazione dell'ebook che
   esiste. Nessuna casella di verdetto è stata riempita da questa fase né dalle
   precedenti.

---

## Stato finale

**Controllo dei riferimenti** (`file:riga` risolti contro l'albero corrente,
incluse le forme a intervallo e a elenco):

```
references checked: 641
unresolved: 0
```

**Copertura**:

```
fidelity points absent from reconciliation_record: none   (F1..F6)
baptism names absent from reconciliation_record:   none   (i 10 simboli)
ebook claims absent from both registers:           none   (36 dichiarate: 7 a scheda,
                                                           18 confermate in zona, 11 in §5)
zone cards found: 61 (il contatore d'origine ne vedeva 59: saltava le due
  schede a livello di sezione di zone_tests — Sezione B e C, entrambe in Scartate)
unaccounted (neither register nor Scartate): none
verdict slots: 46; non-empty: 0
```

**Controllo semantico delle àncore**: 185 coppie «simbolo + `file:riga`»
esaminate, 4 segnalate e tutte spiegate (voce 3 sopra), 0 da correggere.

**Suite e lint**: `pytest tests/ -q` → **1569 passati, 2 saltati**;
`ruff check .` → *All checks passed*. Nessun residuo degli esperimenti di strip
della fase 3: `git status --porcelain` mostra modifiche solo sotto `.phased/`.

**File rivisti** (6, tutti sotto `.phased/active/17-design-audit/audit/`):
`00_authorities.md` (406 righe), `zone_recycling_code.md` (649),
`zone_tests.md` (298), `zone_spa_world.md` (545),
`reconciliation_record.md` (567), `slimming_ledger.md` (640).
Nessun file preesistente fuori da questo elenco è stato toccato: nessuna riga
sotto `src/` o `tests/` è stata modificata in tutta la run.
