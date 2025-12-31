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

  loadOpenApi(schema, sourceUrl = "") {
    // Convert standard OpenAPI schema to tree structure
    this._openApiSchema = schema;
    this._remoteMode = !!sourceUrl;
    this._remoteUrl = sourceUrl;
    this._basepath = "";

    // Transform OpenAPI paths to our tree structure
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
    const pathGroups = {};

    for (const [pathStr, pathData] of Object.entries(paths)) {
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
        const pathName = pathStr || "/";
        for (const [method, opData] of Object.entries(pathData)) {
          if (["get", "post", "put", "delete", "patch"].includes(method)) {
            router.paths[pathName] = router.paths[pathName] || {};
            router.paths[pathName][method] = this._transformOperation(opData, `/${name}${pathStr}`, method);
          }
        }
      } else {
        const subRouterName = segments[0];
        const remainingPath = "/" + segments.slice(1).join("/");
        if (!subGroups[subRouterName]) {
          subGroups[subRouterName] = {};
        }
        subGroups[subRouterName][remainingPath] = pathData;
      }
    }

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
    const methodKey = Object.keys(pathData)[0];
    const method = methodKey?.toUpperCase() || "GET";
    const opData = pathData[methodKey] || {};

    item.innerHTML = `
      <span class="endpoint">
        <span class="method method-${method.toLowerCase()}">${method}</span>
        <span class="path-name">${pathName}</span>
      </span>
    `;

    const endpointSpan = item.querySelector(".endpoint");
    // Build path: handle cases where pathName already starts with /
    const cleanPathName = pathName.startsWith("/") ? pathName.slice(1) : pathName;
    const fullPath = parentPath ? `${parentPath}/${cleanPathName}` : cleanPathName;

    // Build data object for doc/tester (OpenAPI format)
    const nodeData = { [methodKey]: opData };

    item.addEventListener("click", (e) => {
      e.stopPropagation();
      this._selectItem(endpointSpan);
      this.dispatchEvent(new CustomEvent("node-selected", {
        detail: {
          type: "endpoint",
          path: "/" + fullPath,
          method: method,
          operation: opData,
          data: nodeData  // Include full data for doc/tester
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

    // Build path without leading slash
    const currentPath = parentPath ? `${parentPath}/${name}` : name;

    // Build data for doc panel
    const nodeData = {
      type: "router",
      description: routerData.description || "",
      owner_doc: routerData.owner_doc || ""
    };

    // Click handler per router (folder)
    const routerSpan = item.querySelector(".router");
    routerSpan.addEventListener("click", (e) => {
      e.stopPropagation();
      this._selectItem(routerSpan);
      this.dispatchEvent(new CustomEvent("node-selected", {
        detail: {
          type: "router",
          path: "/" + currentPath,
          name: name,
          doc: doc,
          data: nodeData
        },
        bubbles: true,
        composed: true
      }));
    });

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
