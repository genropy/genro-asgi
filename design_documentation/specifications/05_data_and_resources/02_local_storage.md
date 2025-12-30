# LocalStorage and File Management

`LocalStorage` provides a secure, async-first abstraction for interacting with the file system.

## Key Concepts
- **Non-blocking I/O**: Operations are wrapped in `smartasync` to prevent blocking the ASGI event loop.
- **Dynamic Mounts**: Directories can be mounted at runtime with specific access permissions (read/write).
- **Hierarchical Access**: Files are accessed via a node-based system, allowing for metadata inspection and structured navigation.

## Usage in Applications
Applications typically access storage via the server instance or by defining their own local mounts during initialization.
