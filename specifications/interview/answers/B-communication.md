# B. Communication Modes

**Date**: 2025-12-13
**Status**: Verified

---

## Three modes

| Mode | Description | Transports |
|------|-------------|------------|
| **Static** | Serves files from directory | HTTP |
| **Request/Response** | Request → Response | HTTP, WS, NATS |
| **Fire & Forget** | Message without waiting for response (bidirectional) | WS, NATS |
