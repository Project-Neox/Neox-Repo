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
│   └── deox.db          ← SQLite veritabanı (repo_scanner ile otomatik üretilir)
└── samples/             ← örnek paket kaynakları (test/gösterim için)
```

İstemciler bu depoyu şöyle kullanır:

- `deox -Sy` → `<server>/db/deox.db` indirilir, yerel veritabanı güncellenir
- `deox -S htop` → `<server>/deoxpool/htop_3.2.1_amd64.deb` indirilir, checksum
  doğrulanır, bağımlılıklar çözülür ve `dpkg -i` ile kurulur

> Depo URL'si olarak GitHub "raw" adresi kullanılır:
> `https://raw.githubusercontent.com/<KULLANICI>/deox-repo/main/`

## Paket nasıl eklenir?

1. `.deb` dosyanızı `deoxpool/` dizinine atın.
   Dosya adı: `<paket>_<sürüm>_<mimari>.deb` (örn. `htop_3.2.1_amd64.deb`)
2. Veritabanını yeniden üretin (istemci dizininden):

   ```bash
   cd ../deox-client
   python3 -m src.repo_scanner --pool ../deox-repo/deoxpool --db ../deox-repo/db/deox.db
   ```

3. Değişiklikleri commit edip GitHub'a push edin:

   ```bash
   git add deoxpool/ db/deox.db
   git commit -m "paket güncellemesi"
   git push
   ```

> **Not:** Bu depoda `.gitattributes` gereği `*.deb` dosyaları Git LFS ile
> izlenir. `db/deox.db` normal dosya olarak commit edilir. LFS kurulu değilse
> `git lfs install` çalıştırın.

## repo_scanner ne yapar?

- `deoxpool/` altındaki tüm `.deb` dosyalarını tarar
- Her `.deb'in` metadata'sını `dpkg-deb --info` ile çıkarır
  (Package, Version, Architecture, Description, Depends, Maintainer vb.)
- SHA256 ve MD5 checksum'lerini hesaplar
- Tüm bilgileri `db/deox.db` SQLite veritabanına yazar
- Önceki taramadaki oy/indirme-sayısı/işaret bilgilerini paket adıyla taşır

## Örnek paket derleme

`samples/` dizininde iki örnek paket vardır (`deox-hello`, `deox-libcore`).
Derlemek için:

```bash
cd samples
./build.sh ../deoxpool
```

Ardından yukarıdaki 2. ve 3. adımları uygulayın.

## Güvenlik

İstemci tarafında her indirme sonrası **SHA256 checksum doğrulaması** yapılır;
uyuşmazlıkta dosya otomatik olarak 3 kez yeniden indirilir. Ayrıca her `.deb`
`dpkg-deb --info` ile bütünlük kontrolünden geçirilir. Depo sahibi olarak
paketlerinizi únicamente доверilir kaynaklardan derleyin.
