# WebSockets and WSX Protocol

Real-time communication is a first-class citizen in Genro-ASGI.

## Native WebSockets
The `WebSocket` class handles the full lifecycle of a persistent connection, including the handshake, message framing, and graceful closure.

## WSX: Extended WebSockets
WSX is an RPC (Remote Procedure Call) protocol built on top of WebSockets. It allows for:
- **Typed Method Calls**: Calling Python methods from JS with automatic argument serialization.
- **Bidirectional RPC**: JavaScript can call Python, and Python can push commands to JavaScript.
- **State Persistence**: Maintaining a continuous conversation between the client and the specific server worker.
