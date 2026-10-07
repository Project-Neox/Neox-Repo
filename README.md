# Neox-Repo — Debian APT Deposu

Bu GitHub deposu aynı zamanda **canlı bir Debian APT deposu**dur. GitHub Pages üzerinden
hem güzel bir web sitesi olarak hem de `apt` tarafından tüketilebilen bir paket deposu
olarak yayınlanır.

🌐 **Site / depo adresi:** https://project-neox.github.io/Neox-Repo/

```
https://project-neox.github.io/Neox-Repo/
├── index.html                  ← bu sitenin kendisi
├── setup-repo.sh               ← tek komutla kurulum scripti
├── auto-update.sh              ← otomatik paket kur/güncelleme scripti
├── neox-repo.gpg / .asc        ← GPG imza anahtarı (binary + armored)
├── packages.json               ← sitenin okuduğu paket listesi
├── pool/                       ← .deb dosyaları (buraya at, push'la → yayınlanır)
└── dists/stable/
    ├── InRelease               ← GPG clearsigned Release
    ├── Release + Release.gpg   ← Release ve detached imza
    └── main/binary-amd64/
        ├── Packages(.gz)       ← paket indexi
```

## 🚀 Hızlı kurulum (Debian/Ubuntu)

```bash
# Tek komut — anahtar + depo girdisi + apt update, hepsi bir arada:
curl -fsSL https://project-neox.github.io/Neox-Repo/setup-repo.sh | sudo bash
```

Adım adım:

```bash
# 1) GPG anahtarını kur
curl -fsSL https://project-neox.github.io/Neox-Repo/neox-repo.gpg \
  | sudo tee /usr/share/keyrings/neox-repo.gpg > /dev/null

# 2) Depoyu ekle
echo "deb [signed-by=/usr/share/keyrings/neox-repo.gpg] https://project-neox.github.io/Neox-Repo stable main" \
  | sudo tee /etc/apt/sources.list.d/neox-repo.list

# 3) Güncelle ve paket kur
sudo apt update
sudo apt install neox-repo-setup
```

## 🔁 Otomatik güncelleme (yeni paketler sisteme otomatik geçsin)

Depoya yeni bir `.deb` yayınlandığında sistemin haberi olsun istiyorsan:

```bash
# Otomatik güncelleme scriptini kur
curl -fsSL https://project-neox.github.io/Neox-Repo/auto-update.sh \
  | sudo tee /usr/local/bin/neox-repo-auto-update > /dev/null
sudo chmod +x /usr/local/bin/neox-repo-auto-update

# systemd timer ile her saat başı otomatik çalıştır (önerilen)
curl -fsSL https://project-neox.github.io/Neox-Repo/neox-repo-auto-update.service | sudo tee /etc/systemd/system/neox-repo-auto-update.service > /dev/null
curl -fsSL https://project-neox.github.io/Neox-Repo/neox-repo-auto-update.timer   | sudo tee /etc/systemd/system/neox-repo-auto-update.timer > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now neox-repo-auto-update.timer
```

Veya kurulum scriptiyle tek seferde:

```bash
curl -fsSL https://project-neox.github.io/Neox-Repo/setup-repo.sh | sudo bash -s -- --enable-auto-update
```

`auto-update.sh` şunları yapar:

1. **Sadece** Neox deposunun listesini yeniler (`apt update` tüm sistemi yormaz)
2. Depodaki **tüm paketleri kurar** — yeni paketler otomatik sisteme geçer, kurulu olanlar güncellenir

## 📦 Depoya paket yayınlama

Bir `.deb` dosyasını depoya eklemek için:

```bash
dpkg-deb --build my-package ./pool/my-package_1.0.0_amd64.deb
git add pool/my-package_1.0.0_amd64.deb
git commit -m "feat: my-package 1.0.0"
git push
```

**GitHub Actions otomatik olarak:**

1. `pool/` içindeki tüm `.deb`'lerden `dists/stable` metadata'sini üretir (`Packages`, `Packages.gz`, `Release`)
2. GPG ile imzalar (`InRelease` + `Release.gpg`)
3. Depoyu uçtan uca test eder (imza doğrulaması + `apt update` + paket indirme — `scripts/selftest-apt-repo.sh`)
4. Test geçerse her şeyi `gh-pages` dalına yayınlar → site ve depo anında güncellenir

## 🛠 Yerel geliştirme

Depoyu kendi makinenizde derlemek ve test etmek için:

```bash
# 1) Örnek paketi üret (pool/neox-repo-setup_1.0.0_all.deb)
bash scripts/build-sample-package.sh

# 2) Depoyu derle + imzala (imza anahtarı: keys/ veya NEOX_GPG_PRIVATE_KEY env)
bash scripts/build-apt-repo.sh public

# 3) Uçtan uca test (imza + apt update + indirme)
bash scripts/selftest-apt-repo.sh public
```

> Not: Yerelde `gpg` yoksa imzalama için `pgpy` (pip), `apt-ftparchive` yoksa
> `dpkg-scanpackages` + `scripts/make-release.py` kullanılır. CI'da (ubuntu-latest)
> tüm araçlar hazırdır.

## 🔐 Güvenlik

- Depo **GPG ile imzalanır**; `apt` imzasız/bozuk depoyu reddeder.
- İmza anahtarı: `keys/neox-repo-key.asc` (parmak izi `620FCA4444B9A764E38692378A600E629DEB4D5E`)
- **Özel anahtar** GitHub Actions secret'ı olarak saklanır (`NEOX_GPG_PRIVATE_KEY`) — depoya asla commit'lemeyin.
- Bir güncelleme **yalnızca CI testleri geçerse** yayınlanır.

## 📁 Yapı

| Dizin / Dosya | Açıklama |
| --- | --- |
| `pool/` | Yayınlanacak `.deb` dosyaları (push → otomatik yayın) |
| `dists/` | CI tarafından üretilen APT metadata (commit'lenmez) |
| `site/` | GitHub Pages sitesi (index.html, style.css, app.js) |
| `scripts/build-apt-repo.sh` | Depo derleme + imzalama scripti |
| `scripts/selftest-apt-repo.sh` | Uçtan uca depo testi |
| `scripts/setup-repo.sh` | Hedef sistemde depo kurulumu |
| `scripts/auto-update.sh` | Otomatik paket kur/güncelleme |
| `keys/` | GPG public key |
| `.github/workflows/apt-repo.yml` | Yayınlama pipeline'ı |

## 📄 Lisans

MIT
