# -*- coding: utf-8 -*-
"""
DEOX İstemci Paketi
===================

DEOX; Debian tabanlı sistemler için AUR (Arch User Repository) benzeri bir
topluluk paket yönetim sistemidir. Kaynak koddan derleme YAPMAZ; sadece hazır
.deb dosyalarının dağıtımını ve yönetimini yapar.

Modüller:
    main          — argparse tabanlı komut satırı arayüzü (giriş noktası)
    database      — SQLite veritabanı işlemleri (sync + local, aynı şema)
    downloader    — indirme motoru (progress bar, resume, paralel, retry)
    installer     — dpkg entegrasyonu (kurulum / kaldırma / geri alma)
    resolver      — bağımlılık çözücü
    searcher      — paket arama ve bilgi sorgulama
    updater       — depo senkronizasyonu ve güncelleme kontrolü
    ui            — terminal arayüzü (renkler, ilerleme çubuğu, spinner)
    cache         — önbellek yönetimi
    security      — checksum ve .deb bütünlük kontrolleri
    repo_scanner  — repo sahibi için deoxpool/ tarayıcı (db/deox.db üretir)
    utils         — her yerde kullanılan yardımcı fonksiyonlar
"""

__version__ = "1.0.0"
__app_name__ = "DEOX"
