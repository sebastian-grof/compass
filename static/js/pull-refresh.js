// Pull-to-refresh for the installed PWA: standalone display mode has no browser
// chrome, so there is otherwise no way to reload the tournament list. Touch-only
// and dependency-free; native browser pull-to-refresh is suppressed via
// overscroll-behavior in app.css so the two never double-fire.
(function () {
  var THRESHOLD = 70; // px of (damped) pull needed to trigger a reload
  var indicator = document.getElementById("ptr");
  if (!indicator) return;

  var startY = 0;
  var pulling = false;
  var armed = false;

  function reset() {
    pulling = false;
    armed = false;
    indicator.classList.remove("visible", "armed", "refreshing");
    indicator.style.transform = "";
  }

  document.addEventListener("touchstart", function (e) {
    if (document.scrollingElement.scrollTop > 0) return;
    startY = e.touches[0].clientY;
    pulling = true;
    armed = false;
  }, { passive: true });

  document.addEventListener("touchmove", function (e) {
    if (!pulling) return;
    var dy = e.touches[0].clientY - startY;
    if (dy <= 0) {
      indicator.classList.remove("visible", "armed");
      indicator.style.transform = "";
      armed = false;
      return;
    }
    var pull = Math.min(dy / 2.2, THRESHOLD + 24);
    indicator.style.transform = "translate(-50%, " + pull + "px)";
    indicator.classList.add("visible");
    armed = pull >= THRESHOLD;
    indicator.classList.toggle("armed", armed);
  }, { passive: true });

  document.addEventListener("touchend", function () {
    if (!pulling) return;
    if (armed) {
      indicator.classList.add("refreshing");
      location.reload();
    } else {
      reset();
    }
    pulling = false;
  });

  document.addEventListener("touchcancel", reset);
})();
