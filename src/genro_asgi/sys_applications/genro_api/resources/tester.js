// tester.js - API Tester component for Genro API Explorer
// Form for testing API endpoints with parameter inputs and execute button

class ApiTester extends HTMLElement {
  constructor() {
    super();
    this._endpoint = null;  // Current endpoint data
    this._app = "";         // Current app name
    this._baseUrl = "";     // Base URL for API calls
  }

  setApp(app) {
    this._app = app;
    this._remoteMode = false;
  }

  setBaseUrl(url) {
    this._baseUrl = url;
  }

  setRemoteMode(url) {
    this._remoteMode = true;
    this._remoteUrl = url;
  }

  setEndpoint(data, selectedPath = null) {
    this._endpoint = data;
    // Parse method and operation from data (handle direct format)
    const { method, operation, path } = this._parseEndpoint(data);
    this._method = method;
    this._operation = operation;
    // Use selectedPath if provided (from tree selection), otherwise use parsed path
    this._path = selectedPath || path;
    this.render();
  }

  _parseEndpoint(data) {
    // Handle both formats:
    // 1. Direct: {"get": {...operation...}}
    // 2. Wrapped: {openapi: {"get": {...operation...}}, path: "..."}
    const methods = ["get", "post", "put", "delete", "patch"];

    // Check direct format first
    for (const m of methods) {
      if (data[m]) {
        return {
          method: m.toUpperCase(),
          operation: data[m],
          path: data[m].operationId || ""
        };
      }
    }

    // Check wrapped format
    if (data.openapi) {
      for (const m of methods) {
        if (data.openapi[m]) {
          return {
            method: m.toUpperCase(),
            operation: data.openapi[m],
            path: data.path || data.openapi[m].operationId || ""
          };
        }
      }
    }

    return { method: "POST", operation: null, path: data.path || "" };
  }

  showPlaceholder() {
    this.innerHTML = `
      <div class="tester-placeholder">
        Select an endpoint to test it
      </div>
      ${this._getStyles()}
    `;
  }

  render() {
    if (!this._endpoint || this._endpoint.type === "router") {
      this.showPlaceholder();
      return;
    }

    const method = this._method || "POST";
    const params = this._extractParams();
    const path = this._path || "";

    this.innerHTML = `
      <div class="tester-container">
        <div class="tester-header">
          <span class="tester-method tester-method-${method.toLowerCase()}">${method}</span>
          <span class="tester-path">${path}</span>
        </div>
        ${params.length > 0 ? this._renderForm(params) : '<div class="tester-no-params">No parameters required</div>'}
        <div class="tester-actions">
          <button class="tester-execute" id="execute-btn">Execute</button>
        </div>
      </div>
      ${this._getStyles()}
    `;

    this._bindEvents();
  }

  _extractParams() {
    const params = [];
    const operation = this._operation;

    // From openapi parameters (query params for GET)
    if (operation?.parameters) {
      for (const p of operation.parameters) {
        params.push({
          name: p.name,
          type: p.schema?.type || "string",
          required: p.required || false,
          description: p.description || "",
          in: p.in || "query",
          default: p.schema?.default,
          enum: p.schema?.enum,
          enumEndpoint: p.schema?.["x-enum-endpoint"]
        });
      }
    }

    // From requestBody (for POST)
    if (operation?.requestBody?.content?.["application/json"]?.schema?.properties) {
      const props = operation.requestBody.content["application/json"].schema.properties;
      const required = operation.requestBody.content["application/json"].schema.required || [];
      for (const [name, schema] of Object.entries(props)) {
        params.push({
          name,
          type: schema.type || "string",
          required: required.includes(name),
          description: schema.description || "",
          in: "body",
          default: schema.default,
          enum: schema.enum,
          enumEndpoint: schema["x-enum-endpoint"]
        });
      }
    }

    return params;
  }

  _renderForm(params) {
    const fields = params.map(p => this._renderField(p)).join("");
    return `<div class="tester-form">${fields}</div>`;
  }

  _renderField(param) {
    const inputType = this._getInputType(param.type);
    const requiredMark = param.required ? '<span class="tester-required">*</span>' : "";
    const defaultValue = param.default !== undefined ? param.default : "";

    return `
      <div class="tester-field">
        <label class="tester-label">
          ${param.name}${requiredMark}
          <span class="tester-field-type">${param.type}</span>
        </label>
        ${this._renderInput(param, inputType, defaultValue)}
        ${param.description ? `<div class="tester-field-desc">${param.description}</div>` : ""}
      </div>
    `;
  }

  _renderInput(param, inputType, defaultValue) {
    if (param.enum) {
      const options = param.enum.map(v =>
        `<sl-option value="${v}"${v === defaultValue ? ' selected' : ''}>${v}</sl-option>`
      ).join("");
      return `<sl-select name="${param.name}" class="tester-select" value="${defaultValue}">${options}</sl-select>`;
    }
    if (param.enumEndpoint) {
      // Dynamic enum - sl-select with popup, loaded async
      return `<sl-select name="${param.name}" class="tester-select" value="${defaultValue}"
              data-enum-endpoint="${param.enumEndpoint}" hoist>
              <sl-option value="">Loading...</sl-option>
              </sl-select>`;
    }
    if (param.type === "boolean") {
      const checked = defaultValue === true ? "checked" : "";
      return `<input type="checkbox" name="${param.name}" class="tester-checkbox" ${checked}>`;
    }
    return `<input type="${inputType}" name="${param.name}" class="tester-input"
            value="${defaultValue}" placeholder="${param.required ? 'required' : 'optional'}">`;
  }

  _getInputType(type) {
    switch (type) {
      case "integer":
      case "number":
        return "number";
      case "boolean":
        return "checkbox";
      default:
        return "text";
    }
  }

  _bindEvents() {
    const btn = this.querySelector("#execute-btn");
    if (btn) {
      btn.addEventListener("click", () => this._execute());
    }
    this._loadDynamicEnums();
  }

  async _loadDynamicEnums() {
    const selects = this.querySelectorAll("[data-enum-endpoint]");
    for (const select of selects) {
      const endpoint = select.dataset.enumEndpoint;
      // Build URL: replace last path segment with endpoint name
      const pathParts = this._endpoint.path.split("/");
      pathParts[pathParts.length - 1] = endpoint;
      const relativePath = pathParts.join("/");
      const url = this._app ? `/${this._app}/${relativePath}` : `/${relativePath}`;
      try {
        const response = await fetch(url);
        const values = await response.json();
        select.innerHTML = values.map(v => `<sl-option value="${v}">${v}</sl-option>`).join("");
      } catch (e) {
        console.error(`Failed to load enum from ${url}:`, e);
        select.innerHTML = `<sl-option value="">Error loading options</sl-option>`;
      }
    }
  }

  async _execute() {
    if (!this._endpoint) return;

    const path = this._path || this._endpoint.path || "";
    const params = this._collectParams();

    let url;
    let fetchOptions = {};

    if (this._remoteMode && this._remoteUrl) {
      // Remote mode: use the base URL from OpenAPI spec
      // Extract server URL from remote OpenAPI URL
      const remoteUrlObj = new URL(this._remoteUrl);
      const serverBase = `${remoteUrlObj.protocol}//${remoteUrlObj.host}`;
      url = serverBase + (path.startsWith("/") ? path : "/" + path);

      // Remote APIs typically use standard REST conventions
      const method = this._method || "GET";
      fetchOptions.method = method;

      if (method === "GET" || method === "DELETE") {
        const qs = new URLSearchParams(params);
        url = qs.toString() ? `${url}?${qs}` : url;
      } else {
        fetchOptions.headers = { "Content-Type": "application/json" };
        fetchOptions.body = JSON.stringify(params);
      }
    } else {
      // Local mode: genro-asgi dispatcher uses query params for all methods
      url = this._app ? `/${this._app}${path}` : path;
      if (!url.startsWith("/")) url = "/" + url;

      const qs = new URLSearchParams();
      for (const [key, value] of Object.entries(params)) {
        qs.set(key, String(value));
      }
      url = qs.toString() ? `${url}?${qs}` : url;
    }

    const fullUrl = url;

    const startTime = performance.now();

    try {
      const response = await fetch(fullUrl, fetchOptions);
      const endTime = performance.now();
      const duration = Math.round(endTime - startTime);
      const contentType = response.headers.get("content-type") || "";

      let data;
      if (contentType.includes("application/json")) {
        data = await response.json();
      } else {
        // Non-JSON response (CSV, markdown, HTML, etc.)
        data = await response.text();
      }

      // Emit response event
      this.dispatchEvent(new CustomEvent("api-response", {
        bubbles: true,
        detail: {
          status: response.status,
          statusText: response.statusText,
          headers: Object.fromEntries(response.headers.entries()),
          data,
          duration,
          isText: !contentType.includes("application/json")
        }
      }));

    } catch (err) {
      const endTime = performance.now();
      this.dispatchEvent(new CustomEvent("api-response", {
        bubbles: true,
        detail: {
          status: 0,
          statusText: "Network Error",
          headers: {},
          data: { error: err.message },
          duration: Math.round(endTime - startTime)
        }
      }));
    }
  }

  _collectParams() {
    const params = {};
    const inputs = this.querySelectorAll(".tester-input, .tester-checkbox, .tester-select");
    for (const input of inputs) {
      const name = input.name;
      if (input.type === "checkbox") {
        params[name] = input.checked;
      } else if (input.value !== "") {
        // Convert numbers
        if (input.type === "number" && input.value) {
          params[name] = Number(input.value);
        } else {
          params[name] = input.value;
        }
      }
    }
    return params;
  }

  _getStyles() {
    return `
      <style>
        api-tester {
          display: block;
          height: 100%;
          overflow: auto;
          padding: 1rem;
          background: #fffbeb;
        }
        .tester-placeholder {
          display: flex;
          align-items: center;
          justify-content: center;
          height: 100%;
          color: #92400e;
          font-style: italic;
        }
        .tester-container {
          max-width: 600px;
        }
        .tester-header {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.5rem;
          background: #fef3c7;
          border-radius: 4px;
          margin-bottom: 1rem;
        }
        .tester-method {
          font-size: 0.75rem;
          font-weight: bold;
          padding: 0.2rem 0.5rem;
          border-radius: 4px;
          text-transform: uppercase;
        }
        .tester-method-get { background: #61affe; color: white; }
        .tester-method-post { background: #49cc90; color: white; }
        .tester-method-put { background: #fca130; color: white; }
        .tester-method-delete { background: #f93e3e; color: white; }
        .tester-path {
          font-family: monospace;
          font-size: 0.9rem;
          color: #92400e;
        }
        .tester-form {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }
        .tester-field {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
        }
        .tester-label {
          font-weight: 600;
          font-size: 0.9rem;
          color: #78350f;
        }
        .tester-field-type {
          font-weight: normal;
          font-size: 0.8rem;
          color: #b45309;
          margin-left: 0.5rem;
        }
        .tester-required {
          color: #dc2626;
          margin-left: 0.25rem;
        }
        .tester-input {
          padding: 0.5rem;
          border: 1px solid #fcd34d;
          border-radius: 4px;
          font-size: 0.9rem;
          background: white;
        }
        .tester-input:focus {
          outline: none;
          border-color: #f59e0b;
          box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.2);
        }
        .tester-checkbox {
          width: 1.25rem;
          height: 1.25rem;
          accent-color: #f59e0b;
        }
        .tester-select {
          width: 100%;
        }
        .tester-field-desc {
          font-size: 0.8rem;
          color: #92400e;
        }
        .tester-no-params {
          padding: 1rem;
          text-align: center;
          color: #92400e;
          font-style: italic;
        }
        .tester-actions {
          margin-top: 1rem;
        }
        .tester-execute {
          width: 100%;
          padding: 0.75rem;
          background: #f59e0b;
          color: white;
          border: none;
          border-radius: 4px;
          font-weight: 600;
          font-size: 1rem;
          cursor: pointer;
          transition: background 0.2s;
        }
        .tester-execute:hover {
          background: #d97706;
        }
        .tester-execute:active {
          background: #b45309;
        }
      </style>
    `;
  }

  connectedCallback() {
    this.showPlaceholder();
  }
}

customElements.define("api-tester", ApiTester);
