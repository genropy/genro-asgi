// response.js - API Response component for Genro API Explorer
// Displays API response with status, timing, and formatted JSON

class ApiResponse extends HTMLElement {
  constructor() {
    super();
    this._response = null;
  }

  setResponse(response) {
    this._response = response;
    this.render();
  }

  showPlaceholder() {
    this.innerHTML = `
      <div class="response-placeholder">
        Execute a request to see the response
      </div>
      ${this._getStyles()}
    `;
  }

  render() {
    if (!this._response) {
      this.showPlaceholder();
      return;
    }

    const { status, statusText, headers, data, duration } = this._response;
    const statusClass = this._getStatusClass(status);

    this.innerHTML = `
      <div class="response-container">
        <div class="response-header">
          <span class="response-status ${statusClass}">${status}</span>
          <span class="response-status-text">${statusText}</span>
          <span class="response-time">${duration}ms</span>
          <button class="response-copy" id="copy-btn" title="Copy response">📋</button>
        </div>
        <div class="response-body">
          <pre class="response-json">${this._formatJson(data)}</pre>
        </div>
        ${Object.keys(headers).length > 0 ? this._renderHeaders(headers) : ""}
      </div>
      ${this._getStyles()}
    `;

    this._bindEvents();
  }

  _getStatusClass(status) {
    if (status === 0) return "response-status-error";
    if (status >= 200 && status < 300) return "response-status-success";
    if (status >= 400 && status < 500) return "response-status-client-error";
    if (status >= 500) return "response-status-server-error";
    return "";
  }

  _formatJson(data) {
    try {
      const json = JSON.stringify(data, null, 2);
      return this._syntaxHighlight(json);
    } catch {
      return String(data);
    }
  }

  _syntaxHighlight(json) {
    // Simple JSON syntax highlighting
    return json
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?)/g, (match) => {
        let cls = "json-string";
        if (/:$/.test(match)) {
          cls = "json-key";
        }
        return `<span class="${cls}">${match}</span>`;
      })
      .replace(/\b(true|false)\b/g, '<span class="json-boolean">$1</span>')
      .replace(/\b(null)\b/g, '<span class="json-null">$1</span>')
      .replace(/\b(-?\d+\.?\d*)\b/g, '<span class="json-number">$1</span>');
  }

  _renderHeaders(headers) {
    const headerItems = Object.entries(headers)
      .map(([k, v]) => `<div class="response-header-item"><span class="header-key">${k}:</span> ${v}</div>`)
      .join("");

    return `
      <details class="response-headers">
        <summary class="response-headers-title">Response Headers</summary>
        <div class="response-headers-list">${headerItems}</div>
      </details>
    `;
  }

  _bindEvents() {
    const copyBtn = this.querySelector("#copy-btn");
    if (copyBtn) {
      copyBtn.addEventListener("click", () => this._copyResponse());
    }
  }

  async _copyResponse() {
    if (!this._response?.data) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(this._response.data, null, 2));
      const btn = this.querySelector("#copy-btn");
      if (btn) {
        btn.textContent = "✓";
        setTimeout(() => { btn.textContent = "📋"; }, 1500);
      }
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  }

  _getStyles() {
    return `
      <style>
        api-response {
          display: block;
          height: 100%;
          overflow: auto;
          padding: 1rem;
          background: #fdf2f8;
        }
        .response-placeholder {
          display: flex;
          align-items: center;
          justify-content: center;
          height: 100%;
          color: #9d174d;
          font-style: italic;
        }
        .response-container {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }
        .response-header {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.5rem;
          background: #fce7f3;
          border-radius: 4px;
        }
        .response-status {
          font-weight: bold;
          padding: 0.2rem 0.5rem;
          border-radius: 4px;
          font-family: monospace;
        }
        .response-status-success { background: #d1fae5; color: #065f46; }
        .response-status-client-error { background: #fee2e2; color: #991b1b; }
        .response-status-server-error { background: #fef3c7; color: #92400e; }
        .response-status-error { background: #f3f4f6; color: #6b7280; }
        .response-status-text {
          color: #9d174d;
          font-size: 0.9rem;
        }
        .response-time {
          margin-left: auto;
          font-size: 0.85rem;
          color: #be185d;
          font-family: monospace;
        }
        .response-copy {
          background: none;
          border: none;
          cursor: pointer;
          font-size: 1rem;
          padding: 0.25rem;
          border-radius: 4px;
        }
        .response-copy:hover {
          background: #fbcfe8;
        }
        .response-body {
          background: white;
          border: 1px solid #f9a8d4;
          border-radius: 4px;
          overflow: auto;
          max-height: 400px;
        }
        .response-json {
          margin: 0;
          padding: 0.75rem;
          font-family: monospace;
          font-size: 0.85rem;
          line-height: 1.5;
          white-space: pre-wrap;
          word-wrap: break-word;
        }
        .json-key { color: #0369a1; }
        .json-string { color: #059669; }
        .json-number { color: #d97706; }
        .json-boolean { color: #7c3aed; }
        .json-null { color: #6b7280; }
        .response-headers {
          margin-top: 0.5rem;
        }
        .response-headers-title {
          cursor: pointer;
          font-size: 0.85rem;
          color: #9d174d;
          padding: 0.25rem;
        }
        .response-headers-title:hover {
          background: #fce7f3;
          border-radius: 4px;
        }
        .response-headers-list {
          margin-top: 0.5rem;
          padding: 0.5rem;
          background: white;
          border: 1px solid #f9a8d4;
          border-radius: 4px;
          font-size: 0.8rem;
          font-family: monospace;
        }
        .response-header-item {
          padding: 0.2rem 0;
        }
        .header-key {
          color: #9d174d;
          font-weight: 600;
        }
      </style>
    `;
  }

  connectedCallback() {
    this.showPlaceholder();
  }
}

customElements.define("api-response", ApiResponse);
