# -*- coding: utf-8 -*-
"""
DEOX yardımcı fonksiyonlar modülü.

Yapılandırma okuma, sistem yolları, boyut/süre formatlama, komut çalıştırma,
loglama, sürüm karşılaştırma ve Debian bağımlılık dizgisi ayrıştırma gibi
istemcinin her yerinde kullanılan ortak araçları içerir.
"""

import configparser
import json
import logging
import os
import platform
import re
import subprocess
import sys
from datetime import datetime

APP_NAME = "deox"
APP_VERSION = "1.0.0"

# DEOX_ROOT ortam değişkeni ile tüm sistem yollarının başına bir önek eklenebilir.
# Bu sayede root olmadan test/chroot kurulumları yapılabilir.
# Örn: DEOX_ROOT=/tmp/deox-test  ⇒  /etc/deox  →  /tmp/deox-test/etc/deox
ROOT_PREFIX = os.environ.get("DEOX_ROOT", "")

# İstemci dizini (deox-client/) — paket içi öntanımlı yapılandırma dosyaları
CLIENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LOGGER = logging.getLogger("deox")


class DeoxError(Exception):
    """Kullanıcıya gösterilebilen, dostane DEOX hatası."""

    pass


# ---------------------------------------------------------------------------
# Yollar
# ---------------------------------------------------------------------------

def root_path(path):
    """Mutlak yolu DEOX_ROOT öneki ile birleştirir (test/chroot desteği)."""
    if ROOT_PREFIX and path.startswith("/"):
        return os.path.join(ROOT_PREFIX, path.lstrip("/"))
    return path


def system_paths():
    """DEOX'un kullandığı standart sistem yollarını sözlük olarak döndürür."""
    return {
        "etc": root_path("/etc/deox"),                      # yapılandırma
        "lib": root_path("/var/lib/deox"),                  # veritabanları
        "cache": root_path("/var/cache/deox"),              # önbellek
        "log": root_path("/var/log/deox.log"),              # log dosyası
        "hooks": root_path("/etc/deox/hooks.d"),            # hook scriptleri
        "snapshots": root_path("/var/lib/deox/snapshots"),   # snapshot'lar
        "sync_db": root_path("/var/lib/deox/sync/deox.db"),  # uzak (sync) db
        "local_db": root_path("/var/lib/deox/local/deox.db"),  # yerel db
        "cache_pkg": root_path("/var/cache/deox/pkg"),      # .deb önbelleği
        # Test modunda (root değilken) dpkg --root hedefi
        "rootfs": root_path("/var/lib/deox/rootfs"),
        # Çevrimdışı oy kuyruğu
        "votes": root_path("/var/lib/deox/votes.json"),
    }


def ensure_dir(path):
    """Dizin yoksa oluşturur."""
    if path:
        os.makedirs(path, exist_ok=True)
    return path


def is_root():
    """İşlem root yetkisiyle mi çalışıyor?"""
    return hasattr(os, "geteuid") and os.geteuid() == 0


# ---------------------------------------------------------------------------
# Yapılandırma
# ---------------------------------------------------------------------------

DEFAULTS = {
    "CacheDir": "/var/cache/deox/",
    "DBPath": "/var/lib/deox/",
    "LogFile": "/var/log/deox.log",
    "Architecture": "auto",
    "Color": "true",
    "ParallelDownloads": "5",
    "DownloadTimeout": "30",
    "NoConfirm": "false",
    "Proxy": "",
}


class Config:
    """
    deox.conf yapılandırmasını okur.

    Okuma sırası (sonra gelen öncekini ezer):
      1. deox-client/config/deox.conf  (paket içi öntanımlı)
      2. /etc/deox/deox.conf            (sistem — DEOX_ROOT öneki ile)
      3. ~/.config/deox/deox.conf       (kullanıcı)
    """

    def __init__(self, paths=None):
        self.paths = paths or system_paths()
        self.parser = configparser.ConfigParser()
        self.parser["general"] = dict(DEFAULTS)
        candidates = [
            os.path.join(CLIENT_DIR, "config", "deox.conf"),
            os.path.join(self.paths["etc"], "deox.conf"),
            os.path.join(os.path.expanduser("~"), ".config", "deox", "deox.conf"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                self.parser.read(path, encoding="utf-8")

    def get(self, key, fallback=None):
        return self.parser.get("general", key, fallback=fallback)

    def getint(self, key, fallback=0):
        try:
            return self.parser.getint("general", key, fallback=fallback)
        except ValueError:
            return fallback

    def getboolean(self, key, fallback=False):
        try:
            return self.parser.getboolean("general", key, fallback=fallback)
        except ValueError:
            return fallback

    @property
    def cache_dir(self):
        return root_path(self.get("CacheDir"))

    @property
    def db_path(self):
        return root_path(self.get("DBPath"))

    @property
    def log_file(self):
        return root_path(self.get("LogFile"))

    @property
    def architecture(self):
        arch = self.get("Architecture", "auto")
        if arch in (None, "", "auto"):
            return detect_architecture()
        return arch

    @property
    def color(self):
        return self.getboolean("Color", True)

    @property
    def parallel_downloads(self):
        return max(1, self.getint("ParallelDownloads", 5))

    @property
    def download_timeout(self):
        return self.getint("DownloadTimeout", 30)

    @property
    def no_confirm(self):
        return self.getboolean("NoConfirm", False)

    @property
    def proxy(self):
        return self.get("Proxy", "") or None


def load_repos(config):
    """
    Depo kaynaklarını döndürür (öncelik sırasına göre dizilmiş).

    İki kaynaktan okunur (repos.conf öncekini ezer):
      1. deox.conf içindeki depo bölümleri (örn. [deox-core])
      2. repos.conf içindeki bölümler
         (paket içi öntanımlı → /etc/deox/repos.conf)
    Her bölüm bir depoyu temsil eder: Server, Enabled, Priority anahtarları.
    """
    repos = {}

    def _add(name, server, enabled, priority):
        if not name or not server:
            return
        repos[name] = {
            "name": name,
            "server": server,
            "enabled": enabled,
            "priority": priority,
        }

    # 1) deox.conf içindeki depo bölümleri ([general] ve [repositories] hariç)
    for section in config.parser.sections():
        if section in ("general", "repositories"):
            continue
        sec = config.parser[section]
        server = sec.get("Server") or sec.get("URL") or sec.get("url")
        _add(section, server,
             sec.getboolean("Enabled", fallback=True),
             sec.getint("Priority", fallback=100))

    # 2) repos.conf dosyaları
    for path in (os.path.join(CLIENT_DIR, "config", "repos.conf"),
                 os.path.join(config.paths["etc"], "repos.conf")):
        if not os.path.isfile(path):
            continue
        cp = configparser.ConfigParser()
        cp.read(path, encoding="utf-8")
        for section in cp.sections():
            sec = cp[section]
            server = sec.get("Server") or sec.get("URL") or sec.get("url")
            _add(section, server,
                 sec.getboolean("Enabled", fallback=True),
                 sec.getint("Priority", fallback=100))

    return sorted(repos.values(), key=lambda r: (r["priority"], r["name"]))


# ---------------------------------------------------------------------------
# Sistem / komut yardımcıları
# ---------------------------------------------------------------------------

def detect_architecture():
    """Hedef mimariyi bulur: dpkg --print-architecture, yoksa platform."""
    rc, out, _ = run_cmd(["dpkg", "--print-architecture"])
    if rc == 0 and out.strip():
        return out.strip()
    machine = platform.machine()
    return {
        "x86_64": "amd64", "amd64": "amd64",
        "aarch64": "arm64", "arm64": "arm64",
        "armv7l": "armhf", "armv6l": "armhf",
        "i686": "i386", "i386": "i386",
    }.get(machine, machine)


def run_cmd(cmd, timeout=None):
    """Komut çalıştırır; (returncode, stdout, stderr) üçlüsü döndürür."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return 127, "", "komut bulunamadı: %s" % cmd[0]
    except subprocess.TimeoutExpired:
        return 124, "", "komut zaman aşımına uğradı: %s" % " ".join(cmd)


def setup_logging(log_file, verbose=False, debug=False):
    """Loglama sistemini kurar: dosya + (verbose/debug ise) stderr."""
    LOGGER.setLevel(logging.DEBUG)
    LOGGER.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    if verbose or debug:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.DEBUG if debug else logging.INFO)
        handler.setFormatter(fmt)
        LOGGER.addHandler(handler)
    if log_file:
        try:
            ensure_dir(os.path.dirname(log_file))
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(fmt)
            LOGGER.addHandler(file_handler)
        except OSError:
            pass  # log dosyası yazılamıyorsa sessizce geç
    return LOGGER


# ---------------------------------------------------------------------------
# Biçimlendirme
# ---------------------------------------------------------------------------

def format_size(nbytes):
    """Bayt cinsinden değeri '1.2 MB' biçiminde okunaklı dizgeye çevirir."""
    try:
        nbytes = float(nbytes)
    except (TypeError, ValueError):
        return "? B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if nbytes < 1024 or unit == "TB":
            if unit == "B":
                return "%d %s" % (int(nbytes), unit)
            return "%.1f %s" % (nbytes, unit)
        nbytes /= 1024
    return "%.1f TB" % nbytes


def format_eta(seconds):
    """Saniye cinsinden süreyi '0:03' / '1:12:05' biçimine çevirir."""
    seconds = max(int(seconds or 0), 0)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%d:%02d" % (minutes, secs)


def now_str():
    """Şu anın ISO formatında dizgesi."""
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# JSON yardımcıları
# ---------------------------------------------------------------------------

def read_json(path, default=None):
    """JSON dosyasını okur; yoksa/bozuksa varsayılanı döndürür."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    """Veriyi pretty-print JSON olarak dosyaya yazar."""
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ---------------------------------------------------------------------------
# Sürüm ve bağımlılık ayrıştırma
# ---------------------------------------------------------------------------

def split_version(version):
    """
    Debian sürüm dizgesini bileşenlerine ayırır.
    '1:3.2.1-2' → (epoch='1', upstream='3.2.1', revision='2')
    """
    epoch = ""
    rest = version or ""
    if ":" in rest:
        epoch, rest = rest.split(":", 1)
    if "-" in rest:
        upstream, _, revision = rest.rpartition("-")
    else:
        upstream, revision = rest, ""
    return epoch, upstream, revision


def compare_versions(v1, op, v2):
    """
    İki Debian sürümünü karşılaştırır.
    Önce 'dpkg --compare-versions' kullanılır; bulunamazsa kaba bir
    sayısal karşılaştırma yapılır.
    """
    op = {"<": "<<", ">": ">>"}.get(op, op)
    try:
        proc = subprocess.run(["dpkg", "--compare-versions", v1, op, v2],
                              capture_output=True, timeout=10)
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        pass

    def _key(v):
        key = []
        for part in re.split(r"[.\-:+~]", v or ""):
            key.append((0, int(part)) if part.isdigit() else (1, part))
        return key

    a, b = _key(v1), _key(v2)
    return {
        "=": a == b, "<<": a < b, "<=": a <= b,
        ">=": a >= b, ">>": a > b,
    }.get(op, False)


_DEP_RE = re.compile(
    r"^([a-zA-Z0-9][a-zA-Z0-9+.\-]*)(?::[a-z0-9\-]+)?"  # paket adı (+ :arch)
    r"(?:\s*\(\s*(<<|<=|=|>=|>>|<|>)\s*([^)\s]+)\s*\))?"   # (opsiyonel sürüm kısıtı)
)


def parse_depends(dep_str):
    """
    Debian bağımlılık dizgesini ayrıştırır.

    'libc6 (>= 2.34), foo | bar' örneği için dönüş değeri:
        [[('libc6', '>=', '2.34')], [('foo', None, None), ('bar', None, None)]]

    Her iç liste bir virgülle ayrılmış gruptur; grup içindeki her demet
    '|' ile ayrılmış bir alternatifi temsil eder.
    """
    groups = []
    if not dep_str:
        return groups
    for part in dep_str.split(","):
        part = part.strip()
        if not part:
            continue
        alternatives = []
        for alt in part.split("|"):
            alt = alt.strip()
            if not alt:
                continue
            match = _DEP_RE.match(alt)
            if match:
                alternatives.append((match.group(1), match.group(2), match.group(3)))
        if alternatives:
            groups.append(alternatives)
    return groups


def parse_control(text):
    """
    'dpkg-deb -f' / control dosyası çıktısını sözlüğe çevirir.
    Devam satırları (boşlukla başlayanlar) önceki alanın değerine eklenir.
    """
    fields = {}
    current = None
    for line in (text or "").splitlines():
        if not line.strip():
            current = None
            continue
        if line[0] in " \t" and current:
            fields[current] += "\n" + line.strip()
        elif ":" in line:
            key, _, value = line.partition(":")
            current = key.strip()
            fields[current] = value.strip()
    return fields
