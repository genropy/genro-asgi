// Renders the diagrams ourselves: the fence emits <div class="gnr-mermaid">source</div>,
// which the theme does not touch, so the source is still in the DOM when we get here.
//
// useMaxWidth:false keeps every diagram at its NATURAL size instead of squeezing it
// into the column — a wide diagram then scrolls horizontally and stays readable,
// rather than shrinking until the labels are dots.
(function () {
  function render() {
    if (!window.mermaid) return;
    window.mermaid.initialize({
      startOnLoad: false,
      securityLevel: "loose",
      flowchart: {useMaxWidth: false, htmlLabels: true},
      sequence: {useMaxWidth: false},
      theme: document.body.dataset.mdColorScheme === "slate" ? "dark" : "default",
    });
    document.querySelectorAll("div.gnr-mermaid").forEach(function (el, i) {
      if (el.dataset.done) return;
      el.dataset.done = "1";
      var src = el.textContent.trim();
      window.mermaid.render("gnr-d" + i + "-" + Date.now(), src)
        .then(function (r) { el.innerHTML = r.svg; })
        .catch(function (e) {
          el.innerHTML = '<pre style="color:#c00">mermaid: ' + String(e) + "</pre>";
        });
    });
  }
  if (window.document$ && window.document$.subscribe) window.document$.subscribe(render);
  else document.addEventListener("DOMContentLoaded", render);
})();
