// qr-scan.js — in-app QR scanner shared by the add + guest pages.
// Uses the native BarcodeDetector when available, otherwise falls back to the
// vendored jsQR (so it also works on iOS Safari). Exposes window.CompassScan.
(function () {
  var T = window.COMPASS_I18N || {};
  function t(key, fallback) { return T[key] || fallback; }

  function buildOverlay() {
    var overlay = document.createElement("div");
    overlay.className = "qr-overlay";
    var hint = document.createElement("div");
    hint.className = "qr-hint";
    hint.textContent = t("scanHint", "Point the camera at the QR code");
    var cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "qr-cancel";
    cancel.textContent = t("cancel", "Cancel");
    overlay.innerHTML =
      '<div class="qr-card">' +
      '<video class="qr-video" playsinline muted></video>' +
      '<div class="qr-frame"></div>' +
      "</div>";
    var card = overlay.querySelector(".qr-card");
    card.appendChild(hint);
    card.appendChild(cancel);
    return overlay;
  }

  async function start(onResult, onError) {
    function fail(msg) { if (onError) onError(msg); }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      return fail(t("noCamera", "Camera isn't available. Paste the link instead."));
    }

    var overlay = buildOverlay();
    document.body.appendChild(overlay);
    var video = overlay.querySelector(".qr-video");
    var canvas = document.createElement("canvas");
    var ctx = canvas.getContext("2d", { willReadFrequently: true });
    var stream = null, raf = null, stopped = false;

    function cleanup() {
      stopped = true;
      if (raf) cancelAnimationFrame(raf);
      if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
      overlay.remove();
    }
    overlay.querySelector(".qr-cancel").addEventListener("click", cleanup);

    var detector = ("BarcodeDetector" in window)
      ? new window.BarcodeDetector({ formats: ["qr_code"] })
      : null;

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
      });
      video.srcObject = stream;
      await video.play();
    } catch (e) {
      cleanup();
      return fail(t("cameraDenied", "Camera access was denied. Paste the link instead."));
    }

    async function tick() {
      if (stopped) return;
      if (video.readyState === video.HAVE_ENOUGH_DATA) {
        var text = null;
        try {
          if (detector) {
            var codes = await detector.detect(video);
            if (codes && codes.length) text = codes[0].rawValue;
          } else if (window.jsQR) {
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            var img = ctx.getImageData(0, 0, canvas.width, canvas.height);
            var code = window.jsQR(img.data, img.width, img.height, {
              inversionAttempts: "dontInvert",
            });
            if (code) text = code.data;
          } else {
            cleanup();
            return fail(t("scanUnsupported", "Scanning isn't supported here. Paste the link instead."));
          }
        } catch (e) { /* keep scanning */ }
        if (text) { cleanup(); return onResult(text); }
      }
      raf = requestAnimationFrame(tick);
    }
    raf = requestAnimationFrame(tick);
  }

  window.CompassScan = { start: start };
})();
