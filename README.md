# Neox-Repo — Debian APT Deposu

Bu GitHub deposu hem **GitHub Pages sitesi** hem de **imzasız Debian APT deposu** olarak yayınlanır. Paket metadata'sı GitHub Actions tarafından oluşturulur; APT deposu, yayın öncesinde izole bir ortamda test edilir.

🌐 **Site / depo adresi:** https://project-neox.github.io/Neox-Repo/

```text
https://project-neox.github.io/Neox-Repo/
├── index.html, style.css, app.js  ← depo sitesi
├── setup-repo.sh                  ← tek komutla kurulum scripti
├── auto-update.sh                 ← otomatik paket kur/güncelleme scripti
├── packages.json                  ← sitenin okuduğu paket listesi
├── pool/                          ← .deb dosyaları
└── dists/stable/
    ├── Release                    ← imzasız APT metadata'sı ve checksum'lar
    └── main/binary-amd64/
        └── Packages(.gz)          ← paket indexi
```

## 🚀 Hızlı kurulum (Debian/Ubuntu)

```bash
# Depo kaynağını ekler ve apt listelerini günceller:
curl -fsSL https://project-neox.github.io/Neox-Repo/setup-repo.sh | sudo bash

# Örnek paketi kur:
sudo apt install neox-repo-setup
```

Adım adım:

```bash
# 1) İmzasız depo kaynağını ekle
echo "deb [trusted=yes] https://project-neox.github.io/Neox-Repo stable main" \
  | sudo tee /etc/apt/sources.list.d/neox-repo.list

# 2) Paket listesini yenile ve paketi kur
sudo apt update
sudo apt install neox-repo-setup
```

> **Güvenlik:** `trusted=yes`, APT'ye bu imzasız kaynağa güvenmesini söyler. Yalnızca güvendiğiniz depolar için kullanın. GPG imzası olmadığından APT yayıncının kimliğini doğrulayamaz; HTTPS aktarımı korur, metadata checksum'ları ise dosyaların metadata ile tutarlılığını kontrol eder.

Önceden GPG imzalı kaynak satırını kullanan kurulumlarda geçiş için yeni `setup-repo.sh` scriptini çalıştırın. Script mevcut `neox-repo.list` dosyasını `[trusted=yes]` kaynağıyla yeniler ve artık kullanılmayan Neox keyring dosyasını kaldırır.

## 🔁 Otomatik güncelleme

Depoya yeni paket geldiğinde sistemin düzenli olarak güncellenmesini istiyorsanız:

```bash
# Scripti kur
curl -fsSL https://project-neox.github.io/Neox-Repo/auto-update.sh \
  | sudo tee /usr/local/bin/neox-repo-auto-update > /dev/null
sudo chmod +x /usr/local/bin/neox-repo-auto-update

# systemd timer ile her saat başı çalıştır (önerilen)
curl -fsSL https://project-neox.github.io/Neox-Repo/neox-repo-auto-update.service | sudo tee /etc/systemd/system/neox-repo-auto-update.service > /dev/null
curl -fsSL https://project-neox.github.io/Neox-Repo/neox-repo-auto-update.timer   | sudo tee /etc/systemd/system/neox-repo-auto-update.timer > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now neox-repo-auto-update.timer
```

Kurulum scripti timer'ı da kurabilir:

```bash
curl -fsSL https://project-neox.github.io/Neox-Repo/setup-repo.sh | sudo bash -s -- --enable-auto-update
```

`auto-update.sh` yalnızca Neox deposunun listesini yeniler, ardından depodaki paketleri kurar/günceller.

## 📦 Depoya paket yayınlama

Bir `.deb` dosyasını depoya eklemek için:

```bash
dpkg-deb --build my-package ./pool/my-package_1.0.0_amd64.deb
git add pool/my-package_1.0.0_amd64.deb
git commit -m "feat: my-package 1.0.0"
git push
```

GitHub Actions otomatik olarak:

1. `pool/` içindeki paketlerden `Packages`, `Packages.gz` ve `Release` metadata'sını üretir.
2. Depoyu `[trusted=yes]` kullanan izole bir APT ortamında test eder (`apt update` ve her paketi indirme — `scripts/selftest-apt-repo.sh`).
3. Test geçerse siteyi ve depoyu `gh-pages` dalına yayınlar.

## 🛠 Yerel geliştirme

```bash
# Örnek paket üret (pool/neox-repo-setup_1.0.1_all.deb)
bash scripts/build-sample-package.sh

# Depoyu derle (GPG veya özel anahtar gerekmez)
bash scripts/build-apt-repo.sh public

# APT ile uçtan uca test et
bash scripts/selftest-apt-repo.sh public
```

`apt-ftparchive` yoksa metadata üretimi için `dpkg-scanpackages` ve `scripts/make-release.py` kullanılır. CI, `apt-utils` ve `dpkg-dev` paketlerini kurar.

## 🔐 Güvenlik ve imzasız depo

- APT deposu GPG ile imzalanmaz; `InRelease`, `Release.gpg` ve GPG anahtarı yayınlanmaz.
- İstemci kaynak satırı `[trusted=yes]` kullanır. Bu, APT'nin imzasız depoyu kullanmasına izin verir; yayıncı doğrulaması sağlamaz.
- `Release` metadata'sındaki checksum'lar APT'nin indirilen index ve paketleri metadata ile karşılaştırmasını sağlar, ancak imzasız metadata'ya karşı kötü niyetli değişikliği engellemez.
- GitHub Actions yalnızca derleme ve APT tüketim testleri geçerse yayınlar. CI için GPG özel anahtarı veya `NEOX_GPG_PRIVATE_KEY` secret'ı gerekmez.

## 📁 Yapı

| Dizin / Dosya | Açıklama |
| --- | --- |
| `pool/` | Yayınlanacak `.deb` dosyaları |
| `dists/` | CI tarafından üretilen APT metadata'sı (commit'lenmez) |
| `index.html`, `style.css`, `app.js` | GitHub Pages sitesi |
| `scripts/build-apt-repo.sh` | İmzasız APT deposunu derleme scripti |
| `scripts/selftest-apt-repo.sh` | İzole APT uçtan uca testi |
| `scripts/setup-repo.sh` | Hedef sistemde depo kurulumu |
| `scripts/auto-update.sh` | Otomatik paket kur/güncelleme |
| `.github/workflows/apt-repo.yml` | Derleme, test ve yayın pipeline'ı |

## 🔮 DEOX — Topluluk Paket Yöneticisi (AUR benzeri)

Bu depo aynı zamanda **DEOX** paket yöneticisi için istemci ve paket havuzu
kodlarını içerir. DEOX; Debian tabanlı sistemler için AUR benzeri bir topluluk
paket yönetim sistemidir — **yalnızca hazır `.deb` dağıtımı** yapar, kaynak
koddan derleme yapmaz.

```text
├── deox-client/          ← kullanıcının bilgisayarındaki terminal istemcisi
│   ├── deox              ← çalıştırılabilir dosya (python3 ./deox --help)
│   ├── src/              ← main, database, downloader, installer, resolver, ...
│   ├── config/           ← deox.conf ve repos.conf şablonları
│   ├── install.sh        ← sistem geneline kurulum (sudo ./install.sh)
│   └── README.md         ← Türkçe kullanım kılavuzu
└── deox-repo/            ← paket havuzu (GitHub'daki depo yapısı)
    ├── deoxpool/         ← .deb dosyaları buraya atılır
    ├── db/deox.db        ← repo_scanner ile üretilen SQLite veritabanı
    └── samples/          ← örnek paketler (deox-hello, deox-libcore)
```

Hızlı başlangıç:

```bash
cd deox-client
sudo ./install.sh                 # sisteme kur
deox -Sy                          # depo veritabanını senkronize et
deox -Ss htop                     # paket ara
sudo deox -S htop                 # paket kur
```

Depo sahibi için paket ekleme:

```bash
cp paket_1.0_amd64.deb deox-repo/deoxpool/
cd deox-client
python3 -m src.repo_scanner --pool ../deox-repo/deoxpool --db ../deox-repo/db/deox.db
git add deox-repo/deoxpool deox-repo/db/deox.db && git commit -m "paket ekle" && git push
```

Tüm komutlar `--json` ile JSON çıktısı üretir; `sync` ve `local` SQLite
veritabanları ileride yapılacak GUI uygulaması tarafından doğrudan okunabilir.
Ayrıntılar için `deox-client/README.md` ve `deox-repo/README.md` dosyalarına
bakın.

## 📄 Lisans

MIT
