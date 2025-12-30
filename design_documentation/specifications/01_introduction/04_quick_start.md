# Quick Start Guide

Get your first Genro-ASGI server up and running in a few simple steps.

## 1. Installation

Assuming you have `genro-asgi` in your environment:

```bash
pip install genro-asgi
```

## 2. Create your Application

Create a file named `myapp.py`:

```python
from genro_asgi import AsgiApplication, route

class MyFirstApp(AsgiApplication):
    @route("/")
    def index(self):
        return {"message": "Welcome to Genro-ASGI!"}

    @route("/hello/{name}")
    def greet(self, name):
        return {"greeting": f"Hello, {name}!"}
```

## 3. Create the Configuration

Create a file named `config.yaml`:

```yaml
server:
  host: "127.0.0.1"
  port: 8000
  reload: true

apps:
  main:
    module: "myapp:MyFirstApp"
```

## 4. Run the Server

Start the server using the command line:

```bash
python -m genro_asgi --config config.yaml
```

Now open your browser at `http://127.0.0.1:8000` to see your welcome message!
