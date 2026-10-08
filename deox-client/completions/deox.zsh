#compdef deox
# DEOX zsh tab tamamlama
# Kurulum: /usr/share/zsh/site-functions/_deox (install.sh otomatik yapar)

_deox() {
    local -a opts
    opts=(
        '-S[Paket kur]'
        '-R[Paket kaldır]'
        '-Q[Kurulu paketleri sorgula]'
        '-U[Yerel .deb dosyasından kur]:deb dosyası:_files -/ *.deb(.)'
        '-Sy[Veritabanını senkronize et]'
        '-Su[Tüm paketleri güncelle]'
        '-Syu[Sync + update]'
        '-Syyu[Zorla sync + update]'
        '-Ss[Depoda ara]'
        '-Si[Paket detayları]'
        '-Qs[Kurulu paketlerde ara]'
        '-Qi[Kurulu paket bilgisi]'
        '-Ql[Paketin dosya listesi]'
        '-Qo[Dosya sahibini bul]'
        '-Sc[Eski önbelleği temizle]'
        '-Scc[Tüm önbelleği temizle]'
        '-Rs[Bağımlılıklarıyla kaldır]'
        '-Rns[Config ile birlikte kaldır]'
        '--history[İşlem geçmişi]'
        '--rollback[İşlemi geri al]:ID:'
        '--stats[İstatistikler]'
        '--doctor[Sistem bütünlüğü kontrolü]'
        '--export[Kurulu paketleri dışa aktar]:dosya:_files'
        '--import[Paket listesi içe aktar]:dosya:_files'
        '--clean-orphans[Yetim paketleri kaldır]'
        '--check-updates[Güncelleme kontrolü]'
        '--add-repo[Depo ekle]:isim: :url:'
        '--remove-repo[Depo kaldır]:isim:'
        '--list-repos[Depo listesi]'
        '--vote[Pakete oy ver]:paket:'
        '--snapshot[Snapshot yönetimi]:komut:(create restore list)'
        '--version[Sürüm bilgisi]'
        '--json[JSON çıktı]'
        '--verbose[Ayrıntılı çıktı]'
        '--debug[Hata ayıklama]'
        '--no-confirm[Onay sorma]'
        '--no-color[Renkleri kapat]'
        '--yes[Onay sorma]'
    )
    _arguments -s -S "${opts[@]}" '*:paket:'
}

_deox "$@"
