# Missing Doc - 02_server_foundation - Status

Materiale estratto da documenti sorgente, organizzato per destinazione.

## Legenda

| Stato | Significato |
|-------|-------------|
| ~~INTEGRATO~~ | Contenuto già in specifications/, può essere eliminato |
| ⚠️ OBSOLETO | Contiene API/nomi vecchi (es: `routedclass` → `routing`) |
| 📋 CAP XX | Da integrare nel capitolo XX |

---

## File e Stato

| File | Stato | Note |
|------|-------|------|
| `genro-toolbox.md` | ~~INTEGRATO~~ | SmartOptions in `02/02_configuration.md` |
| `configuration.md` | ~~PARZIALE~~ + 📋 CAP 06 | SmartOptions OK, middleware per-app → Cap 06 |

---

## Dettagli per file

### genro-toolbox.md

**Stato**: ~~INTEGRATO~~

Contenuto integrato in `specifications/02_server_foundation/02_configuration.md`:
- SmartOptions class
- Precedenza configurazione
- Type extraction da signature
- Merge con operatore `+`

**Azione**: Può essere eliminato.

### configuration.md

**Stato**: ~~PARZIALMENTE INTEGRATO~~ + 📋 CAP 06

Integrato:
- ~~SmartOptions base~~
- ~~Precedenza DEFAULTS < YAML < env < argv~~
- ~~Server config section~~

Da integrare in Cap 06:
- 📋 Middleware per-app config
- 📋 `routesplugins:` section in YAML
- ⚠️ `routedclass.configure()` - **VERIFICARE SE OBSOLETO** (potrebbe essere `routing.configure()`)

**Azione**: Mantenere fino a completamento Cap 06, poi eliminare.
