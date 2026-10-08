# DEOX Depo (deox-repo)

Bu depo, **DEOX** topluluk paket yöneticisinin paket havuzudur. AUR benzeri
çalışır: paketler **hazır `.deb` dosyaları** olarak dağıtılır, kaynak koddan
derleme **yapılmaz**.

## Depo yapısı

```text
deox-repo/
├── deoxpool/            ← tüm .deb paket dosyaları burada
│   ├── htop_3.2.1_amd64.deb
│   ├── neofetch_7.1.0_all.deb
│   └── ...
├── db/
│   └── deox.db          ← deoxpool/ dosya adlarından üretilen SQLite veritabanı
└── samples/             ← örnek paket kaynakları (test/gösterim için)
```

İstemciler bu depoyu şöyle kullanır:

- `deox -Sy` → `<server>/db/deox.db` indirilir, yerel veritabanı güncellenir
- `deox -S htop` → `<server>/deoxpool/htop_3.2.1_amd64.deb` indirilir, checksum
  doğrulanır, bağımlılıklar çözülür ve `dpkg -i` ile kurulur

> Depo URL'si olarak GitHub "raw" adresi kullanılır:
> `https://raw.githubusercontent.com/<KULLANICI>/deox-repo/main/`

## Paket nasıl eklenir?

1. `.deb` dosyanızı `deoxpool/` dizinine koyun. Dosya adı şu biçimde olmalıdır:
   `<paket>_<sürüm>_<mimari>.deb` (ör. `htop_3.2.1_amd64.deb`). Veritabanındaki
   paket adı, sürüm ve mimari bu dosya adından alınır.
2. `deox-repo/deoxpool/` değişikliğini push edin. GitHub Actions `db/deox.db`
   dosyasını otomatik üretip aynı dala commit eder. İstemcinin paket listesini
   görebilmesi için bu veritabanı depo içinde izlenen normal bir dosyadır.

Veritabanını yerel olarak hemen üretmek/test etmek isterseniz depo kökünden:

```bash
cd deox-client
python3 -m src.repo_scanner --pool ../deox-repo/deoxpool --db ../deox-repo/db/deox.db
cd ..
git add deox-repo/deoxpool/ deox-repo/db/deox.db
git commit -m "paket güncellemesi"
git push
```

> `.deb` dosyaları `.gitattributes` gereği Git LFS ile izlenir. `db/deox.db`
> normal dosya olarak commit edilir. LFS kurulu değilse `git lfs install`
> çalıştırın. Tarayıcı, checkout sırasında görünen LFS pointer'ından gerçek
> paketin boyutunu ve SHA256 checksum'ını da okuyabilir.

## repo_scanner ne yapar?

- `deoxpool/` altındaki tüm `.deb` dosyalarını tarar.
- `<paket>_<sürüm>_<mimari>.deb` adından paket adı, sürüm ve mimariyi alır;
  bu üç alan dosya adını esas alır. Biçime uymayan dosyalar atlanır.
- Dosyanın içeriği erişilebilirse açıklama, bağımlılık, maintainer gibi ek
  metadata alanlarını `dpkg-deb` ile okur. İçerik okunamasa bile dosya adından
  temel paket kaydı oluşturulur.
- SHA256/MD5 checksum ve dosya boyutunu kaydeder. Git LFS pointer'ı varsa
  gerçek `.deb` nesnesinin SHA256 ve boyutu kullanılır; pointer'dan MD5
  alınamadığı için bu alan boş kalır.
- Tüm bilgileri `db/deox.db` SQLite veritabanına yazar; yeniden taramada oy,
  indirme sayısı ve işaret bilgilerini paket adıyla korur.

## Internet Archive'a yedekleme

`deoxpool/` içindeki `.deb` dosyaları `main` dalına push edildiğinde GitHub
Actions bunları Internet Archive item'ına yükler. GitHub Pages'teki yükleme rehberi:
`https://project-neox.github.io/Neox-Repo/archive-upload.html`.

Action'ı kullanmadan önce GitHub repository Settings → Secrets and variables →
Actions bölümünde şu değerleri ekleyin:

- **Repository secrets:** `IA_S3_ACCESS_KEY`, `IA_S3_SECRET_KEY` (Archive.org S3
  anahtarları: <https://archive.org/account/s3.php>)
- **Repository variable:** `IA_IDENTIFIER` (Archive.org item ID)

İlk yüklemede veya tüm paketleri yeniden göndermek için GitHub Actions içinden
`DEOX .deb dosyalarını Internet Archive'a yükle` workflow'unu elle çalıştırın.
Bu workflow `.deb` dosyalarını `deox-repo/deoxpool/` içinden okur; Archive.org'daki
item herkese açık olacağından yalnızca yayınlanması uygun paketleri ekleyin.
**Anahtarları HTML'e, Git'e veya Pages'e koymayın.**

## Örnek paket derleme

`samples/` dizininde iki örnek paket vardır (`deox-hello`, `deox-libcore`).
Derlemek için:

```bash
cd samples
./build.sh ../deoxpool
```

Ardından üstteki `repo_scanner` komutuyla veritabanını yerel olarak üretin
veya değişiklikleri push edip GitHub Actions'ın üretmesini bekleyin.

## Güvenlik

İstemci tarafında her indirme sonrası **SHA256 checksum doğrulaması** yapılır;
uyuşmazlıkta dosya otomatik olarak 3 kez yeniden indirilir. Paket kurulmadan
önce `.deb` arşiv biçimi ve `dpkg-deb --info` ile kontrol edilir. Depo sahibi
olarak paketlerinizi yalnızca güvenilir kaynaklardan derleyin.
