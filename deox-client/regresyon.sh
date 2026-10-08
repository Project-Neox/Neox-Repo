#!/usr/bin/env bash
# DEOX uçtan uca regresyon testi (izole DEOX_ROOT + yerel HTTP depo)
# Kullanım: ./regresyon.sh   (deox-client dizininden, depo sunucusu 8765'te)
set -u
cd "$(dirname "$0")"
export DEOX_ROOT="${DEOX_ROOT:-/tmp/deox-regress}"

rm -rf "$DEOX_ROOT" && mkdir -p "$DEOX_ROOT/etc/deox"
sed 's|https://raw.githubusercontent.com/KULLANICI/deox-repo/main/|http://127.0.0.1:8765/|' \
    config/repos.conf > "$DEOX_ROOT/etc/deox/repos.conf"
cp config/deox.conf "$DEOX_ROOT/etc/deox/deox.conf"

pass=0; fail=0
ok()   { pass=$((pass+1)); echo "✓ $1"; }
bad()  { fail=$((fail+1)); echo "✗ $1"; tail -4 /tmp/out.log; }
run()  { "$@" >/tmp/out.log 2>&1; }
expect()    { local n="$1" p="$2"; shift 2; run "$@"; grep -qF "$p" /tmp/out.log && ok "$n" || bad "$n (beklenen: $p)"; }
expect2()   { local n="$1" p1="$2" p2="$3"; shift 3; run "$@"; if grep -qF "$p1" /tmp/out.log && grep -qF "$p2" /tmp/out.log; then ok "$n"; else bad "$n"; fi; }
expect_rc() { local n="$1" rc_want="$2"; shift 2; run "$@"; [ $? -eq $rc_want ] && ok "$n" || bad "$n (exit code hatalı)"; }
expect_no() { local n="$1" p="$2"; shift 2; run "$@"; grep -qF "$p" /tmp/out.log && bad "$n (istenmeyen: $p)" || ok "$n"; }

expect_rc "version exit=0"          0 ./deox --version
expect "-Sy"                        "deox-core: 2 paket" ./deox -Sy
expect "-Ss başlık+sonuç"           "'deox' araması (2 sonuç):" ./deox -Ss deox
expect "-Ss sonuç satırı"           "deox-core/deox-hello 1.1.0-1 [utils]" ./deox -Ss deox
expect "-Si"                        "SHA256" ./deox -Si deox-hello
expect2 "-S kurulum + bağımlılık"   "✅ deox-hello 1.1.0 başarıyla kuruldu" "✅ deox-libcore 1.0.0 başarıyla kuruldu" ./deox -S deox-hello --no-confirm
expect "-S tekrar (zaten kurulu)"   "zaten kurulu" ./deox -S deox-hello --no-confirm
expect "-Q başlık+satır"            "deox-libcore                 1.0.0  (bağımlılık)" ./deox -Q
expect "--json -Q (kurulu varken)"  '"install_reason": "dependency"' ./deox -Q --json
expect "-Qs başlık"                 "Kurulu paketlerde 'hello' araması (1 sonuç):" ./deox -Qs hello
expect "-Ql başlık"                 "deox-hello dosya listesi:" ./deox -Ql deox-hello
expect "-Ql dosya"                  "/usr/bin/deox-hello" ./deox -Ql deox-hello
expect "-Qo sahip"                  "→ deox-hello" ./deox -Qo /usr/bin/deox-hello
expect "-Qi kurulu etiketi"         "[kurulu] 1.1.0" ./deox -Qi deox-hello
expect "--check-updates güncel"     "Tüm paketler güncel" ./deox --check-updates
expect "--history tablo"            "install" ./deox --history
expect "--stats başlık"             "En çok indirilenler" ./deox --stats
expect_no "--stats None satırı yok" "None" ./deox --stats
expect "--doctor 11/11"             "11/11 kontrol başarılı" ./deox --doctor
expect_no "--doctor None satırı yok" "None" ./deox --doctor
expect "--export dosya"             "aktarıldı" ./deox --export /tmp/deox-regress/liste.txt
expect "--snapshot create"          "snapshot'ı oluşturuldu" ./deox --snapshot create s1
expect "--snapshot list"            "s1" ./deox --snapshot list
expect "--vote"                     "oy verdiniz" ./deox --vote deox-hello
expect "--add-repo"                 "deposu eklendi" ./deox --add-repo test http://127.0.0.1:8765/
expect "--list-repos"               "test" ./deox --list-repos
expect "--remove-repo"              "deposu kaldırıldı" ./deox --remove-repo test
expect "-Sc"                        "Önbellek temizleniyor (eski dosyalar)" ./deox -Sc
expect "-Scc"                       "Önbellek temizleniyor (tümü)" ./deox -Scc
expect "-R (bağımlılık kalır)"      "deox-hello kaldırıldı" ./deox -R deox-hello --no-confirm
expect "--clean-orphans kaldırır"   "deox-libcore kaldırıldı" ./deox --clean-orphans --no-confirm
expect "-Q boş başlık"              "Kurulu paketler (0):" ./deox -Q
expect "-w downloadonly"            "kurulum yapılmadı" ./deox -S deox-hello -w --no-confirm
expect "önbellekten kurulum"        "✅ deox-hello 1.1.0 başarıyla kuruldu" ./deox -S deox-hello --no-confirm
expect "-Rs hepsini kaldırır"       "deox-libcore kaldırıldı" ./deox -Rs deox-hello --no-confirm
expect "-S yeniden kur"             "✅ deox-hello 1.1.0" ./deox -S deox-hello --no-confirm
expect "-Rns purge"                 "deox-hello kaldırıldı" ./deox -Rns deox-hello --no-confirm
expect "-U yerel deb"               "✅ deox-libcore 1.0.0 başarıyla kuruldu" ./deox -U ../deox-repo/deoxpool/deox-libcore_1.0.0_amd64.deb
expect "-R temizle"                 "kaldırıldı" ./deox -R deox-libcore --no-confirm
expect "--import"                   "✅ deox-hello 1.1.0 başarıyla kuruldu" ./deox --import /tmp/deox-regress/liste.txt --no-confirm
expect "-R temizle (import sonrası)" "kaldırıldı" ./deox -R deox-hello deox-libcore --no-confirm
expect "--snapshot restore"         "✅ deox-hello 1.1.0 başarıyla kuruldu" ./deox --snapshot restore s1 --no-confirm
HID=$(./deox --history --json | python3 -c "import json,sys; d=json.load(sys.stdin); print([h['id'] for h in d['history'] if h['action']=='install' and h['package_name']=='deox-libcore'][0])")
expect "--rollback (bağımlıyla birlikte)" "deox-hello, deox-libcore kaldırılacak" ./deox --rollback "$HID" --no-confirm
expect "--rollback sonrası -Q boş"   "Kurulu paketler (0):" ./deox -Q
expect "--json -Ss"                  '"count": 2' ./deox -Ss deox --json
expect "--json --stats"             '"total_downloads"' ./deox --stats --json
expect "--json --doctor"            '"passed": 11' ./deox --doctor --json
expect "--json --snapshot list"     '"name": "s1"' ./deox --snapshot list --json
expect "--json --check-updates"     '"updates"' ./deox --check-updates --json
expect_rc "hata: paket yok (exit 1)"  1 ./deox -S bu-paket-yok
expect_rc "hata: rollback yok (exit 1)" 1 ./deox --rollback 99999
expect_rc "hata: import dosya yok"    1 ./deox --import /tmp/yok.txt
expect_rc "hata: snapshot yok"        1 ./deox --snapshot restore yok
expect_rc "hata: add-repo url"        1 ./deox --add-repo x ftp://x

echo
echo "SONUÇ: $pass geçti, $fail failed"
[ "$fail" -eq 0 ]
