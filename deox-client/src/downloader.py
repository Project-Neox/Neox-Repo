# -*- coding: utf-8 -*-
"""
DEOX indirme motoru.

Özellikler:
  - requests varsa onu kullanır, yoksa standart kütüphanedeki urllib'e düşer
  - HTTP Range ile kaldığı yerden devam (resume) desteği (*.part dosyaları)
  - SHA256/MD5 doğrulaması; uyuşmazlıkta otomatik tekrar indirme (3 deneme)
  - Birden fazla paket için paralel indirme (ThreadPoolExecutor)
  - Her paket için ayrı animasyonlu ilerleme çubuğu (yüzde, boyut, hız, ETA)
  - Proxy desteği (yapılandırma veya ortam değişkenleri)
"""

import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import security
from . import ui
from . import utils

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    requests = None
    _HAS_REQUESTS = False

USER_AGENT = "DEOX/%s" % utils.APP_VERSION
PART_SUFFIX = ".part"


class DownloadError(utils.DeoxError):
    """İndirme işlemi kalıcı olarak başarısız oldu."""


class DownloadItem:
    """İndirilecek tek bir dosyayı temsil eder."""

    def __init__(self, name, url, dest_dir, filename, sha256=None, size=None,
                 md5=None):
        self.name = name                  # görünen ad (örn. paket adı)
        self.url = url                    # tam indirme URL'si
        self.dest_dir = dest_dir          # hedef dizin
        self.filename = filename          # hedef dosya adı
        self.sha256 = sha256
        self.size = size
        self.md5 = md5

    @property
    def dest(self):
        """Tam hedef yolu (başarılı indirme sonrası)."""
        return os.path.join(self.dest_dir, self.filename)

    @property
    def partial(self):
        """Yarı indirme (resume) dosyasının yolu."""
        return self.dest + PART_SUFFIX


class Downloader:
    """Dosya indirme motoru."""

    def __init__(self, config, progress=None):
        self.config = config
        self.progress = progress or ui.Progress()
        self.timeout = config.download_timeout
        self.proxies = self._proxies()
        self._session = None
        if _HAS_REQUESTS:
            self._session = requests.Session()
            self._session.headers["User-Agent"] = USER_AGENT

    def _proxies(self):
        """Proxy ayarını döndürür (önce yapılandırma, sonra ortam değişkenleri)."""
        proxy = self.config.proxy
        if proxy:
            return {"http": proxy, "https": proxy}
        # http_proxy/https_proxy ortam değişkenleri requests ve urllib
        # tarafından otomatik algılanır
        return None

    # ------------------------------------------------------------------
    # Tek dosya
    # ------------------------------------------------------------------

    def download(self, item):
        """
        Dosyayı indirir, checksum doğrular, gerekirse 3 kez yeniden dener.
        Başarısız olursa DownloadError fırlatır; başarılıysa dosya yolunu döndürür.
        """
        utils.ensure_dir(item.dest_dir)
        last_error = None
        for attempt in range(1, security.RETRY_LIMIT + 1):
            try:
                self._download_once(item)
                ok, msg = security.verify_checksums(
                    item.dest, item.sha256, item.md5)
                if not ok:
                    raise DownloadError(msg)
                utils.LOGGER.info("indirme tamamlandı: %s (%s)",
                                  item.filename, msg)
                return item.dest
            except Exception as exc:  # her hata yeniden denenir
                last_error = exc
                utils.LOGGER.warning(
                    "indirme denemesi %d/%d başarısız: %s",
                    attempt, security.RETRY_LIMIT, exc)
                # bozuk tam dosyayı temizle (.part resume için korunur)
                if os.path.exists(item.dest):
                    try:
                        os.remove(item.dest)
                    except OSError:
                        pass
                if attempt < security.RETRY_LIMIT:
                    time.sleep(min(2 ** attempt, 5))  # artan bekleme
        raise DownloadError("%s indirilemedi: %s" % (item.filename, last_error))

    def _download_once(self, item):
        """Tek deneme: resume destekli indirme + ilerleme çubuğu."""
        tid = self.progress.add(item.name, item.size or 0)
        try:
            offset = 0
            if os.path.exists(item.partial):
                offset = os.path.getsize(item.partial)
            if self._session is not None:
                self._download_requests(item, offset, tid)
            else:
                self._download_urllib(item, offset, tid)
            os.replace(item.partial, item.dest)  # atomik taşıma
            self.progress.finish(tid)
        except Exception:
            self.progress.finish(tid, ok=False)
            raise

    def _download_requests(self, item, offset, tid):
        """requests ile indirme (tercih edilen yol)."""
        headers = {"User-Agent": USER_AGENT}
        if offset:
            headers["Range"] = "bytes=%d-" % offset
        resp = self._session.get(item.url, headers=headers, stream=True,
                                 timeout=self.timeout, proxies=self.proxies)
        if resp.status_code not in (200, 206):
            raise DownloadError("HTTP %d: %s" % (resp.status_code, item.url))
        if offset and resp.status_code == 200:
            offset = 0  # sunucu Range desteklemiyor → baştan başla
        total = item.size or 0
        if not total:
            total = offset + int(resp.headers.get("Content-Length", 0) or 0)
        mode = "ab" if offset else "wb"
        downloaded = offset
        start = time.time()
        with open(item.partial, mode) as f:
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                speed = (downloaded - offset) / max(time.time() - start, 1e-6)
                self.progress.update(tid, downloaded, speed=speed, total=total)
        resp.close()

    def _download_urllib(self, item, offset, tid):
        """urllib ile indirme (requests yoksa yedek yol)."""
        headers = {"User-Agent": USER_AGENT}
        if offset:
            headers["Range"] = "bytes=%d-" % offset
        request = urllib.request.Request(item.url, headers=headers)
        try:
            resp = urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            raise DownloadError("HTTP %d: %s" % (exc.code, item.url))
        except urllib.error.URLError as exc:
            raise DownloadError("bağlantı hatası: %s" % exc.reason)
        status = getattr(resp, "status", 200) or 200
        if status not in (200, 206):
            raise DownloadError("HTTP %d: %s" % (status, item.url))
        if offset and status == 200:
            offset = 0
        total = item.size or 0
        if not total:
            total = offset + int(resp.headers.get("Content-Length", 0) or 0)
        mode = "ab" if offset else "wb"
        downloaded = offset
        start = time.time()
        with open(item.partial, mode) as f:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                speed = (downloaded - offset) / max(time.time() - start, 1e-6)
                self.progress.update(tid, downloaded, speed=speed, total=total)
        resp.close()

    # ------------------------------------------------------------------
    # Çoklu dosya (paralel)
    # ------------------------------------------------------------------

    def download_many(self, items, parallel=None):
        """
        Birden fazla dosyayı paralel indirir (her biri ayrı ilerleme çubuğu).
        Dönüş: {paket_adı: dosya_yolu}. Herhangi biri başarısız olursa
        DownloadError fırlatılır.
        """
        parallel = parallel or self.config.parallel_downloads
        results = {}
        errors = {}

        def _one(item):
            try:
                return item.name, self.download(item), None
            except Exception as exc:  # noqa: BLE001 - tüm hatalar toplanır
                return item.name, None, str(exc)

        if parallel <= 1 or len(items) <= 1:
            for item in items:
                name, path, err = _one(item)
                if err:
                    errors[name] = err
                else:
                    results[name] = path
        else:
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                for name, path, err in pool.map(_one, items):
                    if err:
                        errors[name] = err
                    else:
                        results[name] = path

        if errors:
            raise DownloadError("; ".join("%s: %s" % kv for kv in errors.items()))
        return results
