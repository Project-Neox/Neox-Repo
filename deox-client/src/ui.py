# -*- coding: utf-8 -*-
"""
DEOX terminal arayüzü modülü.

Renkler, ilerleme çubukları, spinner animasyonu, onay kutuları ve tablo
gösterimi gibi tüm görsel çıktılar burada üretilir. Harici bir bağımlılık
 gerektirmez; düz ANSI kaçış kodları kullanılır.

--json kipinde (JSON_MODE) insan tarafından okunan tüm çıktılar bastırılır;
böylece komut çıktısı GUI uygulaması tarafından doğrudan tüketilebilir.

Renk şeması:
    Başlık      : mor/bold      Başarı : yeşil ✓
    Hata        : kırmızı ✗      Uyarı : sarı ⚠
    Bilgi       : cyan ℹ         Paket adı : bold beyaz
    Sürüm       : yeşil          Boyut : cyan
"""

import shutil
import sys
import threading
import time

from . import utils

# --json kipinde insan tarafından okunan stdout çıktıları kapatılır
JSON_MODE = False
# Renkler elle kapatılabilir (--no-color) veya terminal yoksa otomatik kapanır
_COLOR = True
_TTY = sys.stdout.isatty()


def init(color=True, json_mode=False):
    """UI modülünü başlatır: renk ve JSON kipi ayarları."""
    global _COLOR, JSON_MODE
    _COLOR = bool(color) and _TTY
    JSON_MODE = bool(json_mode)


class C:
    """ANSI renk kodları."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"


def _paint(code, text):
    """Metni ANSI kodlarıyla renklendirir (renk kapalıysa düz metin)."""
    if _COLOR:
        return "%s%s%s" % (code, text, C.RESET)
    return text


def _w(text):
    """Emoji gibi geniş karakterleri 2 hücre sayan ekran genişliği."""
    width = 0
    for ch in str(text):
        code = ord(ch)
        if 0x1F000 <= code <= 0x1FAFF or ch in "✓✗⚠ℹ✅":
            width += 2
        else:
            width += 1
    return width


# ---------------------------------------------------------------------------
# Renk sarmalayıcıları
# ---------------------------------------------------------------------------

def red(t): return _paint(C.RED, t)
def green(t): return _paint(C.GREEN, t)
def yellow(t): return _paint(C.YELLOW, t)
def cyan(t): return _paint(C.CYAN, t)
def magenta(t): return _paint(C.MAGENTA, t)
def blue(t): return _paint(C.BLUE, t)
def gray(t): return _paint(C.GRAY, t)
def bold(t): return _paint(C.BOLD, t)
def dim(t): return _paint(C.DIM, t)
def white(t): return _paint(C.BOLD + C.WHITE, t)


def pkg(name):
    """Paket adı: bold beyaz."""
    return white(name)


def ver(version):
    """Sürüm: yeşil."""
    return green(str(version))


def size_s(nbytes):
    """Boyut: cyan."""
    return cyan(utils.format_size(nbytes))


def header(text):
    """Başlık yazdırır: mor/bold."""
    _emit(bold(magenta(text)))


# ---------------------------------------------------------------------------
# Mesaj yardımcıları
# ---------------------------------------------------------------------------

def _emit(text):
    """JSON kipinde olmayan stdout çıktısı."""
    if not JSON_MODE:
        print(text)


def success(msg):
    """Başarı mesajı: yeşil ✓"""
    _emit("%s %s" % (green("✓"), msg))


def error(msg):
    """Hata mesajı: kırmızı ✗ — JSON kipinde bile stderr'e yazılır."""
    print("%s %s" % (red("✗"), msg), file=sys.stderr)


def warning(msg):
    """Uyarı mesajı: sarı ⚠"""
    line = "%s %s" % (yellow("⚠"), msg)
    if JSON_MODE:
        print(line, file=sys.stderr)
    else:
        _emit(line)


def info(msg):
    """Bilgi mesajı: cyan ℹ"""
    _emit("%s %s" % (cyan("ℹ"), msg))


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

def print_banner():
    """DEOX açılış kutusu."""
    if JSON_MODE:
        return
    text = "🔮 DEOX Paket Yöneticisi v%s" % utils.APP_VERSION
    width = _w(text) + 8
    pad = (width - _w(text)) // 2
    print("╔" + "═" * width + "╗")
    print("║" + " " * pad + text + " " * (width - _w(text) - pad) + "║")
    print("╚" + "═" * width + "╝")


# ---------------------------------------------------------------------------
# İlerleme çubukları (çok satırlı, paralel indirmeye uygun)
# ---------------------------------------------------------------------------

class Progress:
    """
    Çok satırlı ilerleme çubuğu yöneticisi.

    Her görev (örn. indirilmekte olan bir paket) ayrı bir satırdır.
    Güncellemelerde tüm satırlar ANSI kaçış kodlarıyla yerinde yeniden çizilir.
    Terminal yoksa (JSON kipi, yönlendirme vb.) sade satırlar basılır.

    Örnek satır:
      ████████████████████░░░░░░░░░░  62.4%  [3.2/5.1 MB]  ⚡ 2.4 MB/s  ETA: 0:03
    """

    BAR_WIDTH = 24

    def __init__(self):
        self._lock = threading.Lock()
        self._tasks = {}      # id → görev sözlüğü
        self._order = []      # görev id'leri (çizim sırası)
        self._lines = 0       # ekranda çizili satır sayısı
        self._last_render = 0.0
        self._active = _TTY and not JSON_MODE

    def add(self, name, total=0):
        """Yeni bir ilerleme görevi ekler; görev id'sini döndürür."""
        with self._lock:
            tid = len(self._order)
            self._tasks[tid] = {
                "name": name, "total": total or 0, "done": 0,
                "speed": 0.0, "finished": False, "ok": True,
            }
            self._order.append(tid)
            if self._active:
                self._redraw_locked()
                self._last_render = time.time()
            else:
                _emit("📦 %s indiriliyor..." % name)
            return tid

    def update(self, tid, done, speed=None, total=None):
        """Görevin ilerlemesini günceller (birden çok thread'den çağrılabilir)."""
        with self._lock:
            task = self._tasks.get(tid)
            if task is None or task["finished"]:
                return
            task["done"] = done
            if speed is not None:
                task["speed"] = speed
            if total:
                task["total"] = total
            now = time.time()
            finished = bool(task["total"]) and done >= task["total"]
            # çok sık yeniden çizimi önlemek için ~10 fps ile sınırla
            if self._active and (finished or now - self._last_render > 0.1):
                self._last_render = now
                self._redraw_locked()

    def finish(self, tid, ok=True):
        """Görevi bitirir; tüm görevler bittiyse yeni satıra geçer."""
        with self._lock:
            task = self._tasks.get(tid)
            if task is None:
                return
            task["finished"] = True
            task["ok"] = ok
            if task["total"]:
                task["done"] = task["total"]
            if self._active:
                self._redraw_locked()
                if all(self._tasks[x]["finished"] for x in self._order):
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    self._lines = 0
            else:
                mark = "✓" if ok else "✗"
                _emit("  %s %s (%s)" % (mark, task["name"],
                                        utils.format_size(task["total"])))

    def _render_line(self, task):
        """Tek bir ilerleme satırını üretir."""
        total = task["total"]
        done = task["done"]
        if task["finished"]:
            mark = green("✓") if task.get("ok", True) else red("✗")
            return "  %s %s (%s)" % (mark, white(task["name"]),
                                     utils.format_size(total))
        if total:
            frac = min(done / total, 1.0)
            filled = int(self.BAR_WIDTH * frac)
            bar = (_paint(C.GREEN, "█" * filled)
                   + _paint(C.GRAY, "░" * (self.BAR_WIDTH - filled)))
            speed = task.get("speed") or 0.0
            eta = (total - done) / speed if speed > 0 and done < total else 0
            right = ("%5.1f%%  [%s/%s]  ⚡ %s/s  ETA: %s"
                     % (frac * 100, utils.format_size(done),
                        utils.format_size(total), utils.format_size(speed),
                        utils.format_eta(eta)))
            line = "  %s  %s" % (bar, right)
        else:
            speed = task.get("speed") or 0.0
            line = "  %s %s  ⚡ %s/s" % (cyan("…"), utils.format_size(done),
                                         utils.format_size(speed))
        max_width = shutil.get_terminal_size((100, 20)).columns
        if _w(line) > max_width:
            line = line[: max_width - 1] + "…"
        return line

    def _redraw_locked(self):
        """Tüm görev satırlarını yerinde yeniden çizer (ANSI)."""
        if self._lines:
            sys.stdout.write("\033[%dA" % self._lines)  # imleci yukarı taşı
        for tid in self._order:
            sys.stdout.write("\033[2K\r" + self._render_line(self._tasks[tid]) + "\n")
        sys.stdout.flush()
        self._lines = len(self._order)


# ---------------------------------------------------------------------------
# Spinner (belirsiz süreli işlemler)
# ---------------------------------------------------------------------------

class Spinner:
    """Belirsiz süreli işlemler için dönen animasyon: ⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"""

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, text):
        self.text = text
        self._stop = threading.Event()
        self._thread = None

    def __enter__(self):
        if _TTY and not JSON_MODE:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        else:
            _emit("… %s" % self.text)
        return self

    def _run(self):
        i = 0
        while not self._stop.is_set():
            sys.stdout.write("\r\033[2K  %s %s"
                             % (self.FRAMES[i % len(self.FRAMES)], self.text))
            sys.stdout.flush()
            i += 1
            self._stop.wait(0.08)

    def __exit__(self, exc_type, exc, tb):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        if _TTY and not JSON_MODE:
            sys.stdout.write("\r\033[2K")
            sys.stdout.flush()
        return False


def spinner(text):
    """Spinner bağlam yöneticisi: `with ui.spinner('işlem...'):`"""
    return Spinner(text)


# ---------------------------------------------------------------------------
# Onay kutusu ve tablo
# ---------------------------------------------------------------------------

def confirm_box(title, rows, total_download, total_installed,
                prompt="Devam etmek istiyor musunuz? [E/h]"):
    """
    Kurulum onay kutusunu çizer; kullanıcı E/Enter ile onaylar, h ile iptal eder.

    rows: [{"name": ..., "version": ..., "size": ...}, ...]
    """
    if JSON_MODE:
        return True  # JSON kipinde onay otomatik (otomasyon/GUI için)
    width = 41
    print("┌" + "─" * width + "┐")
    print("│" + title.center(width)[:width] + "│")
    print("├" + "─" * width + "┤")
    for row in rows:
        line = "  %-16s %-10s %10s" % (
            row["name"], row["version"], utils.format_size(row.get("size", 0)))
        print("│" + line[:width].ljust(width) + "│")
    print("├" + "─" * width + "┤")
    line = "  Toplam İndirme: %s" % utils.format_size(total_download)
    print("│" + line[:width].ljust(width) + "│")
    line = "  Toplam Kurulu Boyut: %s" % utils.format_size(total_installed)
    print("│" + line[:width].ljust(width) + "│")
    print("└" + "─" * width + "┘")
    return confirm(prompt)


def confirm(prompt="Devam etmek istiyor musunuz? [E/h]"):
    """E/Enter → True, h → False döndüren basit onay sorusu."""
    while True:
        try:
            answer = input("%s " % prompt).strip().lower()
        except EOFError:
            return False
        if answer in ("", "e", "evet", "y", "yes"):
            return True
        if answer in ("h", "hayır", "hayir", "n", "no"):
            return False


def table(headers, rows):
    """Basit sütunlu tablo yazdırır."""
    widths = [_w(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], _w(str(cell)))
    fmt = "  ".join("{:<%d}" % w for w in widths)
    _emit(_paint(C.BOLD + C.CYAN, fmt.format(*[str(h) for h in headers])))
    _emit("  ".join("-" * w for w in widths))
    for row in rows:
        _emit(fmt.format(*[str(c) for c in row]))
