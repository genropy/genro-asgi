# SpaManager and Session Management

`SpaManager` handles the complexity of Single Page Applications.

## State Hierarchy
1.  **User**: User identity (Avatar).
2.  **Connection**: Single device/browser connection.
3.  **Session**: Master application context (e.g., the main page hosting iframes).
4.  **Page**: Single page instance or widget with its own WebSocket connection.

## Advanced Features
- **Worker Affinity**: Routing requests to the specific worker holding the session state.
- **TreeDict State**: Each hierarchy level maintains a hierarchical dictionary for state data.
