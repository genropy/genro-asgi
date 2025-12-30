## Source: initial_specifications/interview/answers/N-cli.md

**Come si avvia genro-asgi da riga di comando?**

- C'è un comando CLI?
- Come funziona `python -m genro_asgi`?

genro-asgi offre due modi per avviare il server da CLI:

1. **Comando installato** (definito in pyproject.toml):
   ```bash
   genro-asgi serve ./myapp --port 9000
   ```

2. **Via python -m**:
   ```bash
   python -m genro_asgi serve ./myapp --port 9000
   ```

Il file `__main__.py` è un file speciale Python che permette di eseguire un package come script.
Quando esegui `python -m <package>`, Python cerca ed esegue `<package>/__main__.py`.

```bash
# Avvia server
genro-asgi serve <app_dir> [options]

# Mostra versione
genro-asgi --version
genro-asgi -v

# Mostra help
genro-asgi --help
genro-asgi -h
```

| Opzione | Default | Descrizione |
|---------|---------|-------------|
| `--host HOST` | 127.0.0.1 | Host del server |
| `--port PORT` | 8000 | Porta del server |
| `--reload` | false | Abilita auto-reload (development) |

```bash
# Avvia in development mode con auto-reload
genro-asgi serve ./my_app --port 8080 --reload

# Output:
# genro-asgi starting...
# App dir: ./my_app
# Server: http://127.0.0.1:8080
# Mode: development (auto-reload enabled)
```

```toml
[project.scripts]
genro-asgi = "genro_asgi.__main__:main"
```

La directory app deve contenere un file di configurazione:
- `config.yaml` oppure
- `genro-asgi.yaml`

- [\_\_main\_\_.py](../../../src/genro_asgi/__main__.py) - Entry point CLI
- [pyproject.toml](../../../pyproject.toml) - Definizione script

