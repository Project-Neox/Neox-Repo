# DEOX İstemci — Debian Topluluk Paket Yöneticisi

🔮 **DEOX**, Debian tabanlı sistemler için **AUR (Arch User Repository)
benzeri** bir topluluk paket yönetim sistemidir. **Kaynak koddan derleme
yapmaz**; sadece hazır `.deb` dosyalarının dağıtımını ve yönetimini yapar.

Tümüyle **Python 3** ile yazılmıştır ve **tamamen terminal tabanlıdır**.

```text
deox-client/
├── config/
│   ├── deox.conf          ← ana yapılandırma
│   └── repos.conf         ← depo URL listesi
├── src/
│   ├── __init__.py
│   ├── main.py            ← ana giriş, argparse CLI
│   ├── database.py        ← SQLite veritabanı işlemleri
│   ├── downloader.py      ← indirme motoru + animasyon
│   ├── installer.py       ← dpkg entegrasyonu, kurulum/kaldırma
│   ├── resolver.py        ← bağımlılık çözücü
│   ├── searcher.py        ← paket arama
│   ├── updater.py         ← veritabanı ve paket güncelleme
│   ├── ui.py              ← terminal UI (renkler, progress bar)
│   ├── cache.py           ← önbellek yönetimi
│   ├── security.py        ← checksum kontrolü
│   ├── repo_scanner.py    ← deoxpool/ tarayıp db oluşturan script
│   └── utils.py           ← yardımcı fonksiyonlar
├── completions/           ← bash/zsh tab tamamlama
├── deox                   ← çalıştırılabilir dosya
├── install.sh             ← sistem geneline kurulum
├── uninstall.sh           ← kaldırma
├── requirements.txt
└── README.md
```

## Özellikler

- 📦 Hazır `.deb` paketlerinin kurulumu/kaldırılması (dpkg entegrasyonu)
- 🔍 Otomatik bağımlılık çözümü (alternatifler `foo | bar`, sürüm kısıtları,
  `conflicts`, sanal paketler/`provides`)
- ⬇️ Animasyonlu indirme: ilerleme çubuğu, hız, ETA, paralel indirme
- ▶️ Kaldığı yerden devam (HTTP Range ile resume)
- 🔒 SHA256/MD5 checksum doğrulaması + bozuk `.deb` tespiti + 3 deneme
- 🗄️ Çift veritabanı: `sync` (uzak) ve `local` (yerel) — aynı şema, GUI uyumlu
- 🧩 Çoklu depo desteği (`--add-repo` / `--remove-repo` / `--list-repos`)
- 🧭 Çoklu mimari: amd64, arm64, armhf, i386
- 🕘 İşlem geçmişi ve geri alma (`--history`, `--rollback`)
- 📸 Snapshot sistemi (`--snapshot create/restore/list`)
- 📤 Dışa/içe aktarma (`--export`, `--import`)
- 🧹 Önbellek temizliği (`-Sc`, `-Scc`), yetim paket temizliği (`--clean-orphans`)
- 🩺 Sistem kontrolü (`--doctor`), istatistikler (`--stats`)
- 🗳️ Paket oylama (`--vote`)
- 🪝 Pre/post install/remove hook sistemi (`/etc/deox/hooks.d`)
- 📋 Bash/Zsh tab tamamlama
- 🤖 Tüm komutlar `--json` ile JSON çıktısı verir (GUI uyumu)
- 🐞 `--verbose` / `--debug` modları, log dosyası (`/var/log/deox.log`)

## Kurulum

### Gereksinimler

- Python 3.8+
- `dpkg` / `dpkg-deb` (Debian tabanlı sistem)
- (önerilir) `requests` ve `rich` — `pip install -r requirements.txt`
  *(kod bu paketler olmadan da çalışır; yerleşik urllib/ANSI yedekleri vardır)*

### Sistem geneline kurulum

```bash
cd deox-client
sudo ./install.sh
```

Bu script:
- istemciyi `/usr/lib/deox` üzerine kurar,
- `/usr/local/bin/deox` çalıştırıcısını oluşturur,
- `/etc/deox/deox.conf` ve `/etc/deox/repos.conf` dosyalarını kurar,
- bash/zsh tab tamamlamayı kurar,
- `pip` ile bağımlılıkları kurmayı dener.

Kaldırmak için: `sudo ./uninstall.sh` (veriyi de silmek için `--purge`).

### Doğrudan çalıştırma (kurulum gerekmez)

```bash
cd deox-client
./deox --help
```

### Depo URL'sini ayarlama

`/etc/deox/repos.conf` dosyasını düzenleyin (veya komutla ekleyin):

```bash
sudo deox --add-repo deox-core https://raw.githubusercontent.com/KULLANICI/deox-repo/main/
```

## Kullanım

### Temel işlemler

```bash
deox -Sy                  # depo veritabanını senkronize et
deox -S htop              # paket kur (bağımlılıklarıyla)
deox -S htop btop         # birden fazla paket kur
deox -R htop              # paket kaldır
deox -Rs htop             # paket + kullanılmayan bağımlılıkları kaldır
deox -Rns htop            # paket + bağımlılıklar + config dosyaları kaldır
deox -U ./paket.deb       # yerel .deb dosyasından kur
deox -Q                   # tüm kurulu paketleri listele
deox -Qi htop             # kurulu paket bilgisi
deox -Ql htop             # paketin dosya listesi
deox -Qo /usr/bin/htop    # dosyanın hangi pakete ait olduğunu bul
```

### Arama ve bilgi

```bash
deox -Ss htop             # depoda paket ara
deox -Si htop             # paket detayları
deox -Qs htop             # kurulu paketlerde ara
```

Örnek arama çıktısı:

```text
'deox' araması (2 sonuç):
deox/deox-hello 1.0.0-1 [utils] [kurulu]
    DEOX için örnek paket
deox/deox-libcore 1.0.0-1 [libs]
    DEOX örnek çekirdek kitaplığı
```

### Güncelleme

```bash
deox -Sy                  # veritabanını senkronize et
deox -Su                  # tüm paketleri güncelle
deox -Syu                 # sync + update
deox -Syyu                # zorla sync + update
deox --check-updates      # güncelleme kontrolü (kurulum yapmaz)
```

### Önbellek

```bash
deox -Sc                  # eski önbelleği temizle (.part + 30 günden eski)
deox -Scc                 # tüm önbelleği temizle
```

### Geçmiş, snapshot, dışa/içe aktarma

```bash
deox --history            # işlem geçmişi
deox --rollback 3         # 3 numaralı işlemi geri al
deox --snapshot create onceki   # mevcut kurulu paketlerin snapshot'ı
deox --snapshot list           # snapshot listesi
deox --snapshot restore onceki # snapshot'ı geri yükle
deox --export             # kurulu paketleri stdout'a yaz (name=version)
deox --export liste.txt   # dosyaya yaz
deox --import liste.txt   # listedeki paketleri toplu kur
```

### Depolar

```bash
deox --add-repo deox-community https://raw.githubusercontent.com/KULLANICI/deox-community/main/
deox --remove-repo deox-community
deox --list-repos
```

### Ek komutlar

```bash
deox --stats              # istatistikler (en çok indirilen, son eklenen...)
deox --doctor             # sistem bütünlüğü kontrolü
deox --clean-orphans      # yetim (gereksiz) paketleri kaldır
deox --vote htop          # pakete oy ver (+1)
deox --version            # sürüm bilgisi
deox --help               # yardım
```

### JSON çıktısı (GUI uyumu)

Tüm komutlar `--json` ile makine tarafından okunabilir çıktı üretir:

```bash
deox -Ss htop --json
deox -Q --json
deox --stats --json
deox --check-updates --json
```

Örnek:

```json
{
  "keyword": "htop",
  "count": 1,
  "results": [
    {"name": "htop", "version": "3.2.1", "architecture": "amd64", "...": "..."}
  ]
}
```

### Onay ve seçenekler

```bash
deox -S htop --no-confirm   # onay sormadan kur (NoConfirm=true ile de ayarlanabilir)
deox -S htop -w             # sadece indir, kurma (downloadonly)
deox -S htop --no-color     # renkleri kapat
deox -S htop --arch arm64   # farklı mimari için çöz
deox -S htop -v             # ayrıntılı çıktı
deox -S htop -d             # hata ayıklama (debug)
```

## Yapılandırma

`/etc/deox/deox.conf`:

```ini
[general]
CacheDir = /var/cache/deox/
DBPath = /var/lib/deox/
LogFile = /var/log/deox.log
Architecture = auto
Color = true
ParallelDownloads = 5
DownloadTimeout = 30
NoConfirm = false
Proxy =
```

`/etc/deox/repos.conf`:

```ini
[deox-core]
Server = https://raw.githubusercontent.com/KULLANICI/deox-repo/main/
Enabled = true
Priority = 100
```

Kullanıcı düzeyinde geçersiz kılma: `~/.config/deox/deox.conf`

## Dosya konumları

| Yol | Açıklama |
|---|---|
| `/etc/deox/deox.conf` | ana yapılandırma |
| `/etc/deox/repos.conf` | depo listesi |
| `/etc/deox/hooks.d/` | pre/post install/remove hook scriptleri |
| `/var/lib/deox/sync/deox.db` | uzak (sync) veritabanı — depodaki tüm paketler |
| `/var/lib/deox/local/deox.db` | yerel veritabanı — kurulu paketler, geçmiş, depolar |
| `/var/lib/deox/snapshots/` | snapshot dosyaları |
| `/var/lib/deox/votes.json` | çevrimdışı oy kuyruğu |
| `/var/cache/deox/pkg/` | indirilen .deb önbelleği |
| `/var/log/deox.log` | log dosyası |

## Hook sistemi

`/etc/deox/hooks.d/` dizinine çalıştırılabilir scriptler koyun:

- `pre-install`, `post-install` — kurulum öncesi/sonrası
- `pre-remove`, `post-remove` — kaldırma öncesi/sonrası
- `pre-upgrade`, `post-upgrade` — güncelleme öncesi/sonrası
- `.sh` uzantısı da desteklenir; aynı isimli bir **dizin** varsa içindeki
  tüm çalıştırılabilirler sırayla koşulur.

Scriptlere şu ortam değişkenleri aktarılır:
`DEOX_PHASE`, `DEOX_ACTION`, `DEOX_PACKAGE`, `DEOX_VERSION`

## Çift veritabanı yapısı

1. **Uzak (sync)**: GitHub'dan indirilen, tüm paketlerin bilgisi
   → `/var/lib/deox/sync/deox.db`
2. **Yerel (local)**: kurulu paketler, geçmiş, depo kayıtları
   → `/var/lib/deox/local/deox.db`

İkisi de **aynı şema**yı kullanır; ileride yapılacak GUI uygulaması ikisini
de doğrudan okuyabilir.

## Test / geliştirme (root olmadan)

`DEOX_ROOT` ortam değişkeni ile tüm yollar bir önekin altına taşınır ve
kurulum/kaldırma işlemleri `dpkg --root <rootfs> --force-not-root` ile hedef
rootfs'e yapılır — sisteme dokunmadan uçtan uca test:

```bash
export DEOX_ROOT=/tmp/deox-test
mkdir -p $DEOX_ROOT/etc/deox
cp config/*.conf $DEOX_ROOT/etc/deox/
./deox -Sy
./deox -S deox-hello --no-confirm
./deox -Q
```

### Otomatik regresyon testi

`regresyon.sh`, 54 uçtan uca kontrolü izole bir ortamda çalıştırır
(sync, kurulum, bağımlılık çözümü, güncelleme, kaldırma, rollback,
snapshot, JSON çıktılar, hata durumları vb.). Yerel bir depo sunucusu ve
`../deox-repo` içinde üretilmiş paketler gerekir:

```bash
# 1) örnek paketleri derle + veritabanını üret (deox-repo'dan)
cd ../deox-repo/samples && ./build.sh ../deoxpool && cd ../../deox-client
python3 -m src.repo_scanner --pool ../deox-repo/deoxpool --db ../deox-repo/db/deox.db
# 2) depoyu yerel HTTP ile servis et
cd ../deox-repo && python3 -m http.server 8765 &
# 3) regresyonu çalıştır
cd ../deox-client && ./regresyon.sh
```

## Depo sahibi misiniz?

Paket havuzu ve `repo_scanner` kullanımı için bkz: `../deox-repo/README.md`

## Lisans

MIT
