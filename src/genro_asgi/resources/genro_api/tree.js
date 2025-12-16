// tree.js - API Tree web component for Genro API Explorer
// Uses Shoelace sl-tree and sl-tree-item

const autoloaderUrl = "https://cdn.jsdelivr.net/npm/@shoelace-style/shoelace@2.18/cdn/shoelace-autoloader.js";
let discoverFn = null;

async function loadDiscover() {
  if (!discoverFn) {
    const module = await import(autoloaderUrl);
    discoverFn = module.discover;
  }
  return discoverFn;
}

class ApiTree extends HTMLElement {
  constructor() {
    super();
    this._data = null;
    this._baseUrl = "/_genro_api";
  }

  setBaseUrl(url) {
    this._baseUrl = url;
  }

  async loadNodes(app = "") {
    const url = app
      ? `${this._baseUrl}/nodes?app=${encodeURIComponent(app)}`
      : `${this._baseUrl}/nodes`;

    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      this._data = await res.json();
      await this.render();
    } catch (err) {
      console.error("Failed to load nodes:", err);
      this.innerHTML = `<div style="color:red;padding:1rem;">Error: ${err.message}</div>`;
    }
  }

  connectedCallback() {
    this.render();
  }

  renderPath(pathName, pathData, parentPath = "") {
    const item = document.createElement("sl-tree-item");
    const method = Object.keys(pathData)[0]?.toUpperCase() || "GET";
    const opData = pathData[Object.keys(pathData)[0]] || {};
    const summary = opData.summary || pathName;

    item.innerHTML = `
      <span class="endpoint">
        <span class="method method-${method.toLowerCase()}">${method}</span>
        <span class="path-name">${pathName}</span>
      </span>
    `;

    item.addEventListener("click", (e) => {
      e.stopPropagation();
      this.dispatchEvent(new CustomEvent("endpoint-selected", {
        detail: {
          path: parentPath + pathName,
          method: method,
          operation: opData,
          fullPath: pathData
        },
        bubbles: true,
        composed: true
      }));
    });

    return item;
  }

  renderRouter(name, routerData, parentPath = "") {
    const item = document.createElement("sl-tree-item");
    const doc = routerData.owner_doc || routerData.description || "";
    const shortDoc = doc.split(".")[0]; // Prima frase

    item.innerHTML = `
      <span class="router">
        <span class="router-icon">📁</span>
        <span class="router-name">${name}</span>
        ${shortDoc ? `<span class="router-doc">${shortDoc}</span>` : ""}
      </span>
    `;

    const currentPath = parentPath + "/" + name;

    // Render paths (endpoints) di questo router
    if (routerData.paths) {
      for (const [pathName, pathData] of Object.entries(routerData.paths)) {
        item.appendChild(this.renderPath(pathName, pathData, currentPath));
      }
    }

    // Render sub-routers ricorsivamente
    if (routerData.routers) {
      for (const [subName, subData] of Object.entries(routerData.routers)) {
        item.appendChild(this.renderRouter(subName, subData, currentPath));
      }
    }

    return item;
  }

  async render() {
    if (!this._data) {
      this.innerHTML = `<div class="tree-placeholder">Loading...</div>`;
      return;
    }

    const tree = document.createElement("sl-tree");

    // Root level paths
    if (this._data.paths) {
      for (const [pathName, pathData] of Object.entries(this._data.paths)) {
        tree.appendChild(this.renderPath(pathName, pathData, ""));
      }
    }

    // Root level routers
    if (this._data.routers) {
      for (const [name, routerData] of Object.entries(this._data.routers)) {
        tree.appendChild(this.renderRouter(name, routerData, ""));
      }
    }

    this.innerHTML = "";
    this.appendChild(tree);

    // Add styles
    const style = document.createElement("style");
    style.textContent = `
      api-tree {
        display: block;
        height: 100%;
        overflow: auto;
        padding: 0.5rem;
      }
      .tree-placeholder {
        padding: 1rem;
        color: #666;
      }
      .endpoint {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
      }
      .method {
        font-size: 0.7rem;
        font-weight: bold;
        padding: 0.1rem 0.3rem;
        border-radius: 3px;
        text-transform: uppercase;
      }
      .method-get { background: #61affe; color: white; }
      .method-post { background: #49cc90; color: white; }
      .method-put { background: #fca130; color: white; }
      .method-delete { background: #f93e3e; color: white; }
      .method-patch { background: #50e3c2; color: white; }
      .path-name {
        font-family: monospace;
        font-size: 0.9rem;
      }
      .router {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
      }
      .router-icon {
        font-size: 1rem;
      }
      .router-name {
        font-weight: 600;
        color: #1e40af;
      }
      .router-doc {
        font-size: 0.8rem;
        color: #666;
        font-style: italic;
      }
    `;
    this.appendChild(style);

    // Trigger Shoelace autoloader
    const discover = await loadDiscover();
    await discover(this);
  }
}

customElements.define("api-tree", ApiTree);
