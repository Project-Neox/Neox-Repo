/* Neox APT Repository — site dinamikleri */
(function () {
  "use strict";

  /* ---------- Toast ---------- */
  var toast = document.getElementById("toast");
  var toastTimer = null;
  function showToast(msg) {
    toast.textContent = msg;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove("show"); }, 1800);
  }

  /* ---------- Kopyala dugmeleri ---------- */
  function fallbackCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (e) { /* yoksay */ }
    document.body.removeChild(ta);
  }

  document.querySelectorAll(".copy-btn[data-copy-target]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var el = document.getElementById(btn.getAttribute("data-copy-target"));
      if (!el) return;
      var text = el.textContent.replace(/⧉/g, "").trim();
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(
          function () { flash(btn); },
          function () { fallbackCopy(text); flash(btn); }
        );
      } else {
        fallbackCopy(text);
        flash(btn);
      }
    });
  });

  function flash(btn) {
    btn.classList.add("copied");
    var old = btn.textContent;
    btn.textContent = "✓";
    showToast("Panoya kopyalandı");
    setTimeout(function () { btn.classList.remove("copied"); btn.textContent = old; }, 1500);
  }

  /* ---------- Paketler (packages.json) ---------- */
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function renderPackages(doc) {
    var grid = document.getElementById("packagesGrid");
    var countEl = document.getElementById("paketCount");
    var statCount = document.getElementById("statCount");

    var pkgs = doc.packages || [];
    countEl.textContent = "· " + (doc.count != null ? doc.count : pkgs.length) + " paket";
    statCount.textContent = doc.count != null ? doc.count : pkgs.length;

    if (!pkgs.length) {
      grid.innerHTML = '<div class="loading">Depoda henüz paket yok — ilk paketi <code>pool/</code> dizinine ekleyebilirsin.</div>';
      return;
    }

    grid.innerHTML = pkgs.map(function (p) {
      var installBtn = '<button class="copy-btn pkg-install" data-install="' + escapeHtml(p.name) + '" title="Kurulum komutunu kopyala">⧉ sudo apt install ' + escapeHtml(p.name) + "</button>";
      var dlBtn = p.filename
        ? '<a class="copy-btn" href="' + escapeHtml(p.filename) + '" title=".deb indir">⬇ .deb</a>'
        : "";
      return (
        '<article class="package-card">' +
          '<div class="package-head">' +
            '<span class="package-name">' + escapeHtml(p.name) + "</span>" +
            '<span class="badges">' +
              '<span class="badge version">v' + escapeHtml(p.version) + "</span>" +
              '<span class="badge arch">' + escapeHtml(p.architecture) + "</span>" +
            "</span>" +
          "</div>" +
          '<p class="package-desc">' + escapeHtml(p.description || "Açıklama yok.") + "</p>" +
          '<div class="package-meta">📦 ' + escapeHtml(p.size_human || "") +
            (p.maintainer ? " · 👤 " + escapeHtml(p.maintainer) : "") + "</div>" +
          '<div class="package-actions">' + installBtn + dlBtn + "</div>" +
        "</article>"
      );
    }).join("");

    grid.querySelectorAll(".pkg-install").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var name = btn.getAttribute("data-install");
        var text = "sudo apt install " + name;
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(function () { flash(btn); }, function () { fallbackCopy(text); flash(btn); });
        } else {
          fallbackCopy(text);
          flash(btn);
        }
      });
    });
  }

  fetch("packages.json", { cache: "no-cache" })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (doc) {
      renderPackages(doc);
      document.getElementById("statCount").title = "Son güncelleme: " + (doc.updated || "?");
    })
    .catch(function () {
      document.getElementById("packagesGrid").innerHTML = "";
      document.getElementById("packagesFallback").hidden = false;
    });

  /* ---------- Mobil nav ---------- */
  var toggle = document.getElementById("navToggle");
  var links = document.getElementById("navLinks");
  toggle.addEventListener("click", function () { links.classList.toggle("open"); });
  links.querySelectorAll("a").forEach(function (a) {
    a.addEventListener("click", function () { links.classList.remove("open"); });
  });
})();
