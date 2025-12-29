// doc.js - API Documentation panel component for Genro API Explorer
// Displays documentation for selected nodes (routers and endpoints)

class ApiDoc extends HTMLElement {
  constructor() {
    super();
    this._baseUrl = "/_genro_api";
    this._app = "";
  }

  setBaseUrl(url) {
    this._baseUrl = url;
  }

  setApp(app) {
    this._app = app;
    this._remoteMode = false;
  }

  setRemoteMode(url) {
    this._remoteMode = true;
    this._remoteUrl = url;
  }

  async loadDoc(path) {
    const params = new URLSearchParams({ path });
    if (this._app) params.set("app", this._app);
    const url = `${this._baseUrl}/getdoc?${params}`;

    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      this.render(data);
    } catch (err) {
      console.error("Failed to load doc:", err);
      this.innerHTML = `<div class="doc-error">Error: ${err.message}</div>`;
    }
  }

  render(data) {
    if (!data || data.error) {
      this.innerHTML = `<div class="doc-error">${data?.error || "No data"}</div>`;
      return;
    }

    // Check if this is a router (has description/owner_doc) or endpoint (has method like get/post)
    const isRouter = data.type === "router" || (data.description !== undefined && !this._hasMethod(data));
    const html = isRouter ? this._renderRouter(data) : this._renderEndpoint(data);

    this.innerHTML = `
      <div class="doc-container">
        ${html}
      </div>
      <style>
        api-doc {
          display: block;
          height: 100%;
          overflow: auto;
          padding: 1rem;
          background: #f8fafc;
        }
        .doc-container {
          max-width: 800px;
        }
        .doc-error {
          color: #dc2626;
          padding: 1rem;
        }
        .doc-path {
          font-family: monospace;
          font-size: 1.2rem;
          font-weight: 600;
          color: #1e293b;
          margin-bottom: 0.5rem;
          padding: 0.5rem;
          background: #e2e8f0;
          border-radius: 4px;
        }
        .doc-type {
          display: inline-block;
          font-size: 0.75rem;
          padding: 0.2rem 0.5rem;
          border-radius: 4px;
          margin-right: 0.5rem;
          text-transform: uppercase;
          font-weight: bold;
        }
        .doc-type-router {
          background: #8b5cf6;
          color: white;
        }
        .doc-type-endpoint {
          background: #10b981;
          color: white;
        }
        .doc-method {
          display: inline-block;
          font-size: 0.75rem;
          padding: 0.2rem 0.5rem;
          border-radius: 4px;
          font-weight: bold;
          text-transform: uppercase;
        }
        .doc-method-get { background: #61affe; color: white; }
        .doc-method-post { background: #49cc90; color: white; }
        .doc-method-put { background: #fca130; color: white; }
        .doc-method-delete { background: #f93e3e; color: white; }
        .doc-description {
          margin: 1rem 0;
          color: #475569;
          line-height: 1.6;
        }
        .doc-section {
          margin: 1rem 0;
        }
        .doc-section-title {
          font-weight: 600;
          color: #334155;
          margin-bottom: 0.5rem;
          font-size: 0.9rem;
          text-transform: uppercase;
        }
        .doc-params {
          background: white;
          border: 1px solid #e2e8f0;
          border-radius: 4px;
          overflow: hidden;
        }
        .doc-param {
          padding: 0.75rem;
          border-bottom: 1px solid #e2e8f0;
        }
        .doc-param:last-child {
          border-bottom: none;
        }
        .doc-param-name {
          font-family: monospace;
          font-weight: 600;
          color: #1e40af;
        }
        .doc-param-type {
          font-family: monospace;
          font-size: 0.85rem;
          color: #64748b;
          margin-left: 0.5rem;
        }
        .doc-param-required {
          font-size: 0.7rem;
          color: #dc2626;
          margin-left: 0.5rem;
        }
        .doc-param-desc {
          margin-top: 0.25rem;
          font-size: 0.9rem;
          color: #475569;
        }
        .doc-owner {
          font-size: 0.85rem;
          color: #64748b;
          font-style: italic;
        }
        .doc-responses {
          background: white;
          border: 1px solid #e2e8f0;
          border-radius: 4px;
          overflow: hidden;
        }
        .doc-response {
          padding: 0.75rem;
          border-bottom: 1px solid #e2e8f0;
        }
        .doc-response:last-child {
          border-bottom: none;
        }
        .doc-response-code {
          font-family: monospace;
          font-weight: 600;
          padding: 0.2rem 0.4rem;
          border-radius: 3px;
          margin-right: 0.5rem;
        }
        .doc-response-code-2 { background: #d1fae5; color: #065f46; }
        .doc-response-code-4 { background: #fee2e2; color: #991b1b; }
        .doc-response-code-5 { background: #fef3c7; color: #92400e; }
        .doc-response-desc {
          color: #475569;
        }
        .doc-response-type {
          font-family: monospace;
          font-size: 0.85rem;
          color: #6366f1;
          margin-left: 0.5rem;
        }
        .doc-response-schema {
          margin-top: 0.25rem;
          font-family: monospace;
          font-size: 0.85rem;
          color: #64748b;
        }
      </style>
    `;
  }

  _renderRouter(data) {
    return `
      <div class="doc-path">
        <span class="doc-type doc-type-router">Router</span>
        ${data.path || data.name}
      </div>
      ${data.description ? `<div class="doc-description">${data.description}</div>` : ""}
      ${data.owner_doc ? `<div class="doc-owner">${data.owner_doc}</div>` : ""}
    `;
  }

  _hasMethod(data) {
    // Check if data has HTTP method keys (get, post, put, delete, patch)
    const methods = ["get", "post", "put", "delete", "patch"];
    return methods.some(m => data[m] !== undefined);
  }

  _getMethodAndOperation(data) {
    // Handle both formats:
    // 1. Direct: {"get": {...operation...}}
    // 2. Wrapped: {openapi: {"get": {...operation...}}}
    const methods = ["get", "post", "put", "delete", "patch"];

    // Check direct format first
    for (const m of methods) {
      if (data[m]) {
        return { method: m.toUpperCase(), operation: data[m] };
      }
    }

    // Check wrapped format
    if (data.openapi) {
      for (const m of methods) {
        if (data.openapi[m]) {
          return { method: m.toUpperCase(), operation: data.openapi[m] };
        }
      }
    }

    return { method: "POST", operation: null };
  }

  _renderEndpoint(data) {
    const { method, operation } = this._getMethodAndOperation(data);
    const params = this._extractParams(data, operation);
    const responses = this._extractResponses(operation);
    const description = operation?.description || operation?.summary || data.doc || "";
    const name = operation?.operationId || data.path || data.name || "";

    return `
      <div class="doc-path">
        <span class="doc-type doc-type-endpoint">Endpoint</span>
        <span class="doc-method doc-method-${method.toLowerCase()}">${method}</span>
        ${name}
      </div>
      ${description ? `<div class="doc-description">${description}</div>` : ""}
      ${params.length > 0 ? this._renderParams(params) : ""}
      ${responses.length > 0 ? this._renderResponses(responses) : ""}
    `;
  }

  _extractParams(data, operation = null) {
    const params = [];

    // If operation not passed, try to extract it
    if (!operation) {
      const result = this._getMethodAndOperation(data);
      operation = result.operation;
    }

    // From openapi operation parameters
    if (operation?.parameters) {
      for (const p of operation.parameters) {
        params.push({
          name: p.name,
          type: p.schema?.type || "any",
          required: p.required || false,
          description: p.description || "",
          in: p.in || "query"
        });
      }
    }

    // From requestBody (for POST with body params)
    if (operation?.requestBody?.content?.["application/json"]?.schema?.properties) {
      const props = operation.requestBody.content["application/json"].schema.properties;
      const required = operation.requestBody.content["application/json"].schema.required || [];
      for (const [name, schema] of Object.entries(props)) {
        params.push({
          name,
          type: schema.type || "any",
          required: required.includes(name),
          description: schema.description || "",
          in: "body"
        });
      }
    }

    // From metadata if available (native format)
    if (data.metadata?.parameters) {
      for (const [name, info] of Object.entries(data.metadata.parameters)) {
        params.push({
          name,
          type: info.type || "any",
          required: info.required || false,
          description: info.description || ""
        });
      }
    }

    return params;
  }

  _renderParams(params) {
    const items = params.map(p => `
      <div class="doc-param">
        <span class="doc-param-name">${p.name}</span>
        <span class="doc-param-type">${p.type}</span>
        ${p.required ? '<span class="doc-param-required">required</span>' : ""}
        ${p.description ? `<div class="doc-param-desc">${p.description}</div>` : ""}
      </div>
    `).join("");

    return `
      <div class="doc-section">
        <div class="doc-section-title">Parameters</div>
        <div class="doc-params">${items}</div>
      </div>
    `;
  }

  _extractResponses(operation) {
    const responses = [];
    if (!operation?.responses) return responses;

    for (const [code, resp] of Object.entries(operation.responses)) {
      const schema = resp.content?.["application/json"]?.schema;
      responses.push({
        code,
        description: resp.description || "",
        type: schema?.type || null,
        properties: schema?.properties || null
      });
    }
    return responses;
  }

  _renderResponses(responses) {
    const items = responses.map(r => {
      let schemaInfo = "";
      if (r.type) {
        schemaInfo = `<span class="doc-response-type">${r.type}</span>`;
      }
      if (r.properties) {
        const props = Object.entries(r.properties)
          .map(([k, v]) => `${k}: ${v.type || "any"}`)
          .join(", ");
        schemaInfo += props ? `<div class="doc-response-schema">{${props}}</div>` : "";
      }
      return `
        <div class="doc-response">
          <span class="doc-response-code doc-response-code-${r.code[0]}">${r.code}</span>
          <span class="doc-response-desc">${r.description}</span>
          ${schemaInfo}
        </div>
      `;
    }).join("");

    return `
      <div class="doc-section">
        <div class="doc-section-title">Responses</div>
        <div class="doc-responses">${items}</div>
      </div>
    `;
  }

  showPlaceholder() {
    this.innerHTML = `
      <div class="doc-placeholder">
        Select an endpoint or router to view documentation
      </div>
      <style>
        .doc-placeholder {
          display: flex;
          align-items: center;
          justify-content: center;
          height: 100%;
          color: #64748b;
          font-style: italic;
        }
      </style>
    `;
  }

  connectedCallback() {
    this.showPlaceholder();
  }
}

customElements.define("api-doc", ApiDoc);
