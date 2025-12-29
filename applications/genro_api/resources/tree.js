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
    this._selectedItem = null;
  }

  setBaseUrl(url) {
    this._baseUrl = url;
  }

  _selectItem(spanElement) {
    if (this._selectedItem) {
      this._selectedItem.classList.remove("selected");
    }
    this._selectedItem = spanElement;
    spanElement.classList.add("selected");
  }

  async loadNodes(app = "", basepath = "") {
    const params = new URLSearchParams();
    if (app) params.set("app", app);
    if (basepath) params.set("basepath", basepath);

    const queryString = params.toString();
    const url = queryString
      ? `${this._baseUrl}/nodes?${queryString}`
      : `${this._baseUrl}/nodes`;

    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      this._data = await res.json();
      this._basepath = basepath;  // Store for path building
      this._remoteMode = false;
      this._openApiSchema = null;
      await this.render();
    } catch (err) {
      console.error("Failed to load nodes:", err);
      this.innerHTML = `<div style="color:red;padding:1rem;">Error: ${err.message}</div>`;
    }
  }

  loadOpenApi(schema, sourceUrl = "") {
    // Convert standard OpenAPI schema to tree structure
    this._openApiSchema = schema;
    this._remoteMode = true;
    this._remoteUrl = sourceUrl;
    this._basepath = "";

    // Transform OpenAPI paths to our tree structure
    // OpenAPI has { paths: { "/pet/{id}": { get: {...}, post: {...} } } }
    // We need { paths: { "/pet/{id}": { get: {...} } }, routers: {} }
    this._data = this._transformOpenApi(schema);
    this.render();
  }

  _transformOpenApi(schema) {
    const result = {
      description: schema.info?.description || "",
      owner_doc: schema.info?.title || "",
      paths: {},
      routers: {}
    };

    const paths = schema.paths || {};

    // Group paths by their first segment to create router hierarchy
    const pathGroups = {};

    for (const [pathStr, pathData] of Object.entries(paths)) {
      // pathStr is like "/pet/{petId}" or "/store/order"
      const segments = pathStr.split("/").filter(Boolean);

      if (segments.length === 0) {
        // Root path "/"
        for (const [method, opData] of Object.entries(pathData)) {
          if (["get", "post", "put", "delete", "patch"].includes(method)) {
            result.paths["/"] = result.paths["/"] || {};
            result.paths["/"][method] = this._transformOperation(opData, pathStr, method);
          }
        }
      } else if (segments.length === 1) {
        // Single segment like "/pet"
        const name = "/" + segments[0];
        for (const [method, opData] of Object.entries(pathData)) {
          if (["get", "post", "put", "delete", "patch"].includes(method)) {
            result.paths[name] = result.paths[name] || {};
            result.paths[name][method] = this._transformOperation(opData, pathStr, method);
          }
        }
      } else {
        // Multiple segments - group by first segment as router
        const routerName = segments[0];
        const remainingPath = "/" + segments.slice(1).join("/");

        if (!pathGroups[routerName]) {
          pathGroups[routerName] = {};
        }
        pathGroups[routerName][remainingPath] = pathData;
      }
    }

    // Convert groups to routers
    for (const [routerName, routerPaths] of Object.entries(pathGroups)) {
      result.routers[routerName] = this._buildRouter(routerName, routerPaths);
    }

    return result;
  }

  _buildRouter(name, paths) {
    const router = {
      description: "",
      owner_doc: "",
      paths: {},
      routers: {}
    };

    const subGroups = {};

    for (const [pathStr, pathData] of Object.entries(paths)) {
      const segments = pathStr.split("/").filter(Boolean);

      if (segments.length === 0 || segments.length === 1) {
        // Direct path in this router
        const pathName = pathStr || "/";
        for (const [method, opData] of Object.entries(pathData)) {
          if (["get", "post", "put", "delete", "patch"].includes(method)) {
            router.paths[pathName] = router.paths[pathName] || {};
            router.paths[pathName][method] = this._transformOperation(opData, `/${name}${pathStr}`, method);
          }
        }
      } else {
        // Need sub-router
        const subRouterName = segments[0];
        const remainingPath = "/" + segments.slice(1).join("/");
        if (!subGroups[subRouterName]) {
          subGroups[subRouterName] = {};
        }
        subGroups[subRouterName][remainingPath] = pathData;
      }
    }

    // Recursively build sub-routers
    for (const [subName, subPaths] of Object.entries(subGroups)) {
      router.routers[subName] = this._buildRouter(subName, subPaths);
    }

    return router;
  }

  _transformOperation(opData, fullPath, method) {
    return {
      summary: opData.summary || "",
      description: opData.description || "",
      operationId: opData.operationId || "",
      parameters: opData.parameters || [],
      requestBody: opData.requestBody || null,
      responses: opData.responses || {},
      tags: opData.tags || [],
      _fullPath: fullPath,
      _method: method
    };
  }

  connectedCallback() {
    this.render();
  }

  renderPath(pathName, pathData, parentPath = "") {
    const item = document.createElement("sl-tree-item");
    const method = Object.keys(pathData)[0]?.toUpperCase() || "GET";
    const opData = pathData[Object.keys(pathData)[0]] || {};

    item.innerHTML = `
      <span class="endpoint">
        <span class="method method-${method.toLowerCase()}">${method}</span>
        <span class="path-name">${pathName}</span>
      </span>
    `;

    const endpointSpan = item.querySelector(".endpoint");
    // Build path: handle cases where pathName already starts with /
    const cleanPathName = pathName.startsWith("/") ? pathName.slice(1) : pathName;
    // relativePath is for building tree hierarchy
    const relativePath = parentPath ? `${parentPath}/${cleanPathName}` : cleanPathName;
    // fullPath includes basepath for API calls (getdoc)
    const fullPath = this._basepath ? `${this._basepath}/${relativePath}` : relativePath;

    item.addEventListener("click", (e) => {
      e.stopPropagation();
      this._selectItem(endpointSpan);

      const detail = {
        type: "endpoint",
        path: fullPath,
        method: method,
        operation: opData
      };

      // In remote mode, include the full operation data for doc/tester
      if (this._remoteMode) {
        detail.data = opData;
        detail.remoteUrl = this._remoteUrl;
      }

      this.dispatchEvent(new CustomEvent("node-selected", {
        detail,
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

    // relativePath is for building tree hierarchy (without basepath)
    const relativePath = parentPath ? `${parentPath}/${name}` : name;
    // fullPath includes basepath for API calls (getdoc)
    const fullPath = this._basepath ? `${this._basepath}/${relativePath}` : relativePath;

    // Click handler per router (folder)
    const routerSpan = item.querySelector(".router");
    routerSpan.addEventListener("click", (e) => {
      e.stopPropagation();
      this._selectItem(routerSpan);
      this.dispatchEvent(new CustomEvent("node-selected", {
        detail: {
          type: "router",
          path: fullPath,
          name: name,
          doc: doc
        },
        bubbles: true,
        composed: true
      }));
    });

    // Render paths (endpoints) di questo router - pass relativePath for hierarchy
    if (routerData.paths) {
      for (const [pathName, pathData] of Object.entries(routerData.paths)) {
        item.appendChild(this.renderPath(pathName, pathData, relativePath));
      }
    }

    // Render sub-routers ricorsivamente - pass relativePath for hierarchy
    if (routerData.routers) {
      for (const [subName, subData] of Object.entries(routerData.routers)) {
        item.appendChild(this.renderRouter(subName, subData, relativePath));
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
      .endpoint.selected,
      .router.selected {
        background: #bae6fd;
        border-radius: 4px;
        padding: 2px 6px;
      }
    `;
    this.appendChild(style);

    // Trigger Shoelace autoloader
    const discover = await loadDiscover();
    await discover(this);
  }
}

customElements.define("api-tree", ApiTree);
