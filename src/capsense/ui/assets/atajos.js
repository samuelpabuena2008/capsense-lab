// Atajos de teclado de la aplicación: M = medir, 1-5 = vistas, F11 = pantalla completa.
(function () {
  const VISTAS = ["nav-medicion", "nav-calculos", "nav-historial", "nav-conexion", "nav-simulacion"];

  function escribiendo(e) {
    const t = e.target;
    return t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
  }

  window.capsensePantallaCompleta = function () {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.pantalla_completa) {
      window.pywebview.api.pantalla_completa();
    } else if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      document.documentElement.requestFullscreen().catch(function () {});
    }
  };

  document.addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.altKey || e.metaKey || escribiendo(e)) return;
    if (e.key === "F11") {
      e.preventDefault();
      window.capsensePantallaCompleta();
      return;
    }
    if (e.key === "m" || e.key === "M") {
      const b = document.getElementById("btn-medir");
      if (b && !b.disabled) b.click();
      return;
    }
    const i = "12345".indexOf(e.key);
    if (i >= 0) {
      const b = document.getElementById(VISTAS[i]);
      if (b) b.click();
    }
  });
})();
