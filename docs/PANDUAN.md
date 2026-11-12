# Elix-PMS · Panduan (Bahasa Indonesia)

Sistem Manajemen Pengunjung Multi-Kondominium terintegrasi dengan LiveKit Video Interkom dan Kamera LPR Dahua berbasis Headless Architecture.

## 🏛️ Arsitektur Proyek
Sistem ini menggunakan arsitektur terpisah (*Decoupled/Headless*):
* **Backend:** Django 5.x + Django Rest Framework (DRF) + Django Channels + Celery
* **Web Admin Dashboard:** Next.js + TypeScript
* **Resident App:** Flutter (Android dulu; `mobile/resident/`)
* **Tablet Kiosk:** web kiosk layar penuh di `/kiosk/` (Next.js), bisa dibuka di tablet apa saja

---

## 📂 Struktur Repositori Utama
```text
/opt/vms-project/
├── docker-compose.yml       # Layanan dasar (db, redis, web, worker + jadwal beat)
├── docker-compose.prod.yml  # Produksi: gateway di 127.0.0.1:8000 untuk Cloudflare Tunnel
├── frontend/                # Dashboard staf Next.js + TypeScript; Dockerfile + nginx.conf = gateway
└── backend/
    ├── Dockerfile           # Blueprint kontainerisasi Django Engine
    ├── requirements.txt     # Dependensi library Python
    ├── myproject/           # Konfigurasi Core App (Django Settings, ASGI, WSGI)
    └── core/                # Modul Utama (Models, Views, Tasks untuk VMS & LPR)
```

---

## ⚙️ Persiapan Lingkungan Pengembangan Lokal (Local Development)

### 1. Prasyarat Sistem
Pastikan perangkat lokal Anda telah terinstal:
* Python 3.11+
* Docker Desktop & Docker Compose
* Node.js 22 (untuk Next.js Dashboard; di server cukup lewat Docker `node:22-alpine`)
* Flutter 3.44 (untuk aplikasi penghuni; APK dibangun otomatis di GitHub Actions, bukan di server)

### 2. Setup Back-End (Django)
1. Masuk ke direktori backend dan buat virtual environment:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # Untuk Linux/macOS
   # venv\Scripts\activate  # Untuk Windows
   ```
2. Instal seluruh dependensi:
   ```bash
   pip install -r requirements.txt
   ```
3. Salin file `.env.example` menjadi `.env` dan sesuaikan kredensial database lokal serta token pihak ketiga.
4. Jalankan migrasi basis data awal:
   ```bash
   python manage.py migrate
   ```
5. Buat akun Administrator utama:
   ```bash
   python manage.py createsuperuser
   ```
6. Jalankan server lokal:
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```

---

## 🛡️ Integrasi Perangkat IoT & Pihak Ketiga

### 1. Kamera LPR Dahua (Skenario A)
* **Endpoint API:** `https://api.domain-anda.com/v1/lpr-webhook/`
* **Metode Otentikasi:** HTTP Basic Authentication dengan kredensial **khusus per kamera** (dashboard → Gates & devices → Plate cameras → *Add plate camera* → *Webhook username/password*), bukan akun user Django.
* **Konfigurasi Kamera:** Masuk ke Web GUI Dahua -> **Setting > Network > Advanced Settings > HTTP Post** (atau **Alarm Server**). Aktifkan Auth, masukkan username dan password webhook kamera tersebut.
* **Aktifkan per site:** dashboard → Site settings → *Licence-plate recognition enabled* (default mati). Selama mati, payload hanya disimpan dan bisa dilihat di Gates & devices → Plate cameras → *Setup info*.
* **Payload JSON:** Plat dideteksi otomatis dari format Dahua umum (`PlateNumber`, `plateNumber`, dll.), atau atur *Plate field* (mis. `Picture.Plate.PlateNumber`) bila firmware memakai skema lain.

### 2. Akses Kontrol Sonoff & Shelly (Cloud-to-Cloud)
* Kredensial cloud diisi per site di dashboard → Gates & devices → *Cloud accounts*; tiap relay ditambahkan di Gates & devices → Relays → *Add relay* (mode Cloud, LAN, atau LAN lalu fallback ke Cloud). Uji dengan tombol *Test*.
* **Shelly:** server mengirim `on` dengan `toggle_after` = *pulse seconds*, sehingga relay mati sendiri walau Auto-Off belum diatur.
* **Sonoff (eWeLink):** perangkat wajib mengaktifkan mode **Inching / Auto-Off** (2-3 detik) di aplikasi eWeLink; Django hanya mengirim `"on"`.
* **Mode LAN** hanya bisa dipakai jika server dapat menjangkau jaringan site (mis. Tailscale subnet router di site).

### 3. LiveKit Video Interkom
* Server Django bertugas memproduksi Short-Lived Access Token (default 10 menit, satu token per room) menggunakan API key dari LiveKit Cloud. Isi URL, API key dan secret LiveKit di dashboard **Platform → System settings**, lalu tekan *Save & test connection* (alternatif: `LIVEKIT_*` di `.env` sebagai cadangan).
* Token ini dikirimkan via API ke **Tablet Kiosk** (saat memanggil unit) dan **Resident App** (saat menjawab) untuk bergabung ke room interkom. Media dialirkan melalui server SFU LiveKit Cloud (bukan *peer-to-peer*).
* **Alur utama:** tamu memilih unit di kiosk → HP penghuni berdering (push FCM + WebSocket) → penghuni menjawab video → **swipe to unlock** → gerbang kiosk terbuka dan tercatat di log akses.

### 4. Walk In & Printer Slip 58 mm
* Di kiosk, unit dipilih dengan **keypad angka di layar** (kalau site punya beberapa blok, pilih bloknya dulu; unit yang cocok muncul saat angka diketik; unit berhuruf lewat *Use keyboard*), jadi keyboard tablet tidak pernah menutupi layar. Setiap layar setelah *Welcome* menampilkan label alur dan langkahnya (misal *Walk in · Step 2 of 3*) dengan warna berbeda per alur; di tablet portrait konten dimulai dari atas.
* Tombol **Walk in** di kiosk (aktif/nonaktif per site di *Site settings → Offer walk-in registration*) untuk tamu umum: pilih unit tujuan (wajib), isi data seperti saat *Call a resident*, foto (bisa dinonaktifkan: *Take the walk-in visitor's photo*), setujui privacy notice.
* Kiosk mencetak slip berisi **nomor pass**, **PIN 4 digit** dan QR check-out. Nomor di-reset setiap hari per site, satu seri per kategori: **V**001 Visitor, **D** Parcel, **F** Food, **C** Contractor, **P** Pick-up, **O** Other.
* Gerbang **tidak** terbuka otomatis: tamu menunjukkan slip ke guard. Saat keluar, tamu memakai tombol **Check out** di kiosk, atau guard menekan *Check out* di halaman **Visitor list** dashboard.
* **Check out di kiosk** (aktif/nonaktif per site: *Offer self check-out at the kiosk*): scan QR slip/screenshot atau ketik PIN di keypad. PIN unik di antara tamu yang sedang di dalam, hanya berlaku selama tamu on site, dan kiosk menolak PIN selama 1 menit setelah 5 kali salah. QR invitation juga bisa dipakai untuk check-out tamu undangan. PIN juga disiapkan untuk sub access control unit.
* **Check out dengan wajah** (per site: *Allow check-out by face*, default **nonaktif**): saat kiosk mengambil foto tamu (walk-in, call, atau invitation dengan face check), PC kiosk membuat *face template* (face-api.js, 128 angka); tamu diberi tahu sebelum foto dan melihat status "Face check-out ready". Saat keluar: *Check out → Check out with my face*. Server hanya membandingkan dengan tamu yang sedang on site di site itu; jarak harus < 0.45 dan jelas lebih dekat (0.06) dari kandidat kedua, jika ragu tamu diminta pakai QR/PIN. Template dihapus saat check-out dan oleh purge harian setelah pass berakhir; foto tidak dikirim untuk pencocokan. Tidak ada liveness check (foto cetak bisa dipakai untuk check-out, tidak pernah membuka gerbang). Jarak kecocokan dicatat di log `core.visits` untuk kalibrasi di kamera asli.
* **Call a resident:** setelah penghuni membuka gerbang, kiosk menampilkan pass tamu (nomor pass, QR dan PIN di bawahnya) dengan pemberitahuan agar difoto/di-screenshot untuk check-out, plus tombol *Print slip* jika kiosk punya printer. Layar pass kembali ke awal setelah 25 detik agar tidak terbaca tamu berikutnya.
* **Visitor list (officer):** semua tamu tercatat sebagai *visit* dengan nomor pass harian yang sama: walk-in kiosk, walk-in yang didaftarkan guard (*Register visitor*, foto webcam opsional), check-in invitation (QR atau plat LPR; kamera exit otomatis check-out), dan gerbang yang dibuka lewat intercom. Officer bisa melihat jam check-in/check-out, *Print slip* dari printer pos jaga, *Edit* catatan, dan *Check out* satu per satu atau bulk. PIN tamu on site tampil di bawah nomor pass. Dari baris yang sama officer bisa *Block/Unblock* tamu, dan admin bisa *Erase data* untuk permintaan penghapusan PDPA.
* Printer: jadikan printer 58 mm sebagai default printer di PC kiosk (ukuran kertas roll 58 mm) dan jalankan Chrome dengan `--kiosk --kiosk-printing` agar slip langsung tercetak tanpa dialog. Kiosk tanpa printer: hilangkan centang *Receipt printer connected* di *Gates & devices → Kiosks*, maka nomor pass dan QR ditampilkan di layar.

### 4b. AI Assistant di kiosk (OpenAI)
* Tombol **Ask <nama asisten>** di kiosk: tamu bisa bicara (atau mengetik) untuk menanyakan arah dan lokasi (AI bisa menampilkan denah/peta di layar), fasilitas dan jam buka, aturan, pengiriman paket, dan **bantuan registrasi**: AI menanyakan unit, nama dan tujuan lewat suara, lalu membuka form Walk-in yang sudah terisi (foto, persetujuan dan unit tetap dikonfirmasi tamu di layar). AI juga bisa membuka layar panggil unit, scan QR undangan, dan check-out.
* AI hanya membahas seputar condo dan tidak pernah menyebut atau mengonfirmasi data penghuni. AI menjawab dalam bahasa tamu.
* **Mode** (diatur Platform admin di *System settings → Kiosk AI assistant*): *Speech to text* (default: suara → teks → jawaban → suara, lebih hemat, ada jeda singkat; teks jawaban langsung tampil dan suaranya di-stream sehingga mulai terdengar sebelum selesai dibuat) atau *Realtime* (percakapan suara langsung dua arah, lebih natural, lebih mahal). Di sana juga OpenAI API key, suara, model, durasi maksimal percakapan (180 detik) dan jumlah percakapan per kiosk per hari (100).
* **Site admin** (*Site setup → AI Assistant*, tampil sebagai ringkasan status dan 4 card: *Assistant* → *Change* membuka pengaturan, *Knowledge*, *Maps & floor plans* dan *Try it* → *Open*): aktif/nonaktif, nama, salam, bahasa, panduan tambahan, API key OpenAI milik site (opsional), **materi pengetahuan** (teks: arah, fasilitas, aturan, kontak, akses MRT/taksi), **denah/peta** (gambar), dan *Try it* untuk menguji jawaban.
* **Privasi:** percakapan tidak disimpan; server hanya menghitung jumlah percakapan untuk batas biaya. API key tidak pernah dikirim ke kiosk. Kiosk memberi tahu tamu bahwa suaranya diproses oleh OpenAI.

### 5. Menu APK resident: Access, Facility, Visitor, Feedback
* Saat aplikasi dibuka muncul **splash screen**: logo ELIX di tengah latar navy dengan cahaya biru yang berdenyut, lalu masuk ke login atau Home.
* Header Home menampilkan **nama condo** (dari pengaturan Site) sebagai pengganti logo.
* Halaman login memakai latar cahaya biru yang bergerak, kartu login *glassmorphism* (blur transparan) dengan tombol gradasi biru, dan teks *Engage Link Identified Experience* dan "© 2026 ELIX. All rights reserved.".
* Header Home: **cuaca** (suhu dan prakiraan 2 jam dari NEA/data.gov.sg, stasiun terdekat dengan kode pos condo) di kanan nama (tanpa latar, ukuran besar), dan **bell notifikasi** dengan jumlah yang belum dibaca. Notifikasi berisi semua aktivitas baru 30 hari terakhir: tamu datang/pulang, gerbang terbuka/ditolak, panggilan tak terjawab, status booking, dan balasan feedback.
* **Dokumen** di *Profile → Documents*: file kepemilikan/kontrak sewa milik resident yang di-upload manajemen (*Residents → Documents*), biasanya sebelum akun dibuat. Resident hanya melihat dokumennya sendiri; PDF dibuka di viewer HP, foto di dalam aplikasi.
* **Tema** dipilih di *Profile → Theme*: *Auto* (ikut HP), *Light* atau *Dark*; tersimpan di HP.
* Semua list di APK memakai pagination (maksimal 9 per halaman, *‹ Page 2 of 5 · 41 items ›*).
* Tombol unduh APK (*Residents → Resident app (Android)*) selalu menuju build terbaru: link-nya berisi versi (`elix-resident.apk?v=<versi>`, ditulis `scripts/fetch-resident-apk.sh` ke `downloads/elix-resident.json`), jadi cache HP atau Cloudflare tidak memberi APK lama.
* **Kebijakan privasi** (`/privacy/`) dan **hapus akun** (`/account-deletion/`) adalah halaman publik di web, dibuka dari link di halaman login dan *Profile* APK. **Kebijakan keamanan siber** (`/security/`) juga halaman publik; halaman login dashboard menampilkan link ke kebijakan privasi dan kebijakan keamanan siber (bisa dipakai saat mengisi kuesioner keamanan vendor). Alamat email kontaknya ada di `PRIVACY_EMAIL` (`frontend/src/lib/legal.ts`).
* **Google Play:** workflow GitHub Actions juga membuat `elix-resident.aab` (artifact *elix-resident-aab*) untuk di-upload ke Play Console, dan mengecek kesiapan 16 KB page size. Saat setup di Play Console pilih *Use existing app signing key* (upload `elix-release.jks`) agar HP yang memakai APK dari link bisa update ke versi Play Store. Permission galeri foto/video dan `READ_EXTERNAL_STORAGE` dari plugin dihapus karena tidak dipakai. Detail deklarasi ada di `docs/TECHNICAL.md` (bagian *Google Play*).
* Kiosk juga menampilkan suhu dan prakiraan cuaca di bawah tanggal.
* Home APK berisi 4 menu card (ikon sederhana) di atas *Recent activity* (maksimal 5; *See all* untuk semua riwayat).
* **Gates & devices** tampil seperti System settings: ringkasan berapa perangkat yang perlu dicek, lalu **card per jenis** (Gates, Relays, Plate cameras, Kiosks, Cloud accounts, serta Face terminals dan On-site link yang *coming soon*) dengan status (*2 gates*, *1 problem*, *1 offline*, …). Tombol **Open** menampilkan daftarnya (dengan *Test open*, *Check*, *Setup info*, *New sign-in code*, *Edit*, *Delete*) dan **← All devices** untuk kembali.
* **Access:** buka gerbang dari jarak jauh dengan *swipe to open*. Hanya gate yang dicentang *Residents can open this gate from the app* (Gates & devices) yang muncul; setiap pembukaan tercatat (metode *App*, nama resident, unit).
* **Facility:** fasilitas dikonfigurasi admin di **Setup → Facilities & payments** (jam buka, hari buka, durasi slot, maks. slot per booking, booking per slot, kapasitas, harga per slot, deposit, berapa hari ke depan, batas booking per unit, batas waktu cancel, aturan, foto). Fasilitas gratis langsung confirmed. Fasilitas berbayar memakai **HitPay** milik kondo (PayNow, kartu, dll.) di dalam aplikasi: slot ditahan selama pembayaran (default 15 menit) dan booking hanya dikonfirmasi setelah API HitPay menyatakan pembayaran *completed* (halaman return dan webhook bertanda tangan hanya memicu pengecekan itu). Booking yang tidak dibayar otomatis dilepas. Refund dilakukan di dashboard HitPay lalu dicatat di menu **Bookings**.
* **Visitor:** daftar tamu unit, tab *On going* dan *History*, dengan jam check-in dan check-out.
* **Feedback:** resident memberi rating 1–5 bintang per kategori + komentar; Site admin atau Staff membalas di menu **Feedback** (rata-rata dan distribusi rating), balasan tampil di aplikasi.
* Setup HitPay: isi API key dan salt (terenkripsi) di *Online payments*; salt wajib diisi, karena webhook tanpa tanda tangan yang valid ditolak; biarkan *Sandbox* tercentang untuk uji coba, hilangkan centang untuk live.

* **Paket dan modul (SaaS):** Elix dijual per site dalam bentuk modul: Core (selalu ada), Resident app, Video intercom, Facilities & payments, LPR, Face check (kiosk), AI concierge, Advanced reports (export dan cetak/PDF), serta On-site devices, LPR whitelist dan Face terminals (segera; integrasi hardware ditunda). Modul *Coming soon* belum berfungsi: di *Gates & devices* ada card **Face terminals** dan **On-site link** (*Learn more*) yang menjelaskan fitur yang akan datang, di *Your plan* ditandai *coming soon*, dan di *Plans* / *Subscription* checkbox-nya tidak bisa dicentang sampai fiturnya siap. Super admin mengatur paket di **Platform → Plans** (isi modul dan batas: unit, kiosk, gerbang, kamera LPR, akun staff) dan langganan tiap site di **Platform → Condominiums → Subscription** (paket, add-on, modul yang dimatikan, pengecualian batas, status trial/active/grace/suspended/cancelled, tanggal, kontak penagihan, catatan internal, riwayat perubahan). Site baru otomatis trial 30 hari pada paket yang dipilih saat dibuat. Site lama otomatis di paket **Full** (semua modul). Saat *Suspended*, hanya Core dan LPR yang tetap berjalan (akses fisik tidak pernah berhenti). Menu modul yang tidak dibeli tetap tampil dengan **gembok** dan keterangan paket yang membukanya; site admin melihat paket, modul dan pemakaian batas di **Site settings → Your plan**. Di APK, menu *Facility* disembunyikan bila paket tidak memuat Facilities.
* **Siklus langganan otomatis** (setiap hari pukul 08:05): trial habis → *Active* bila tanggal *Paid until* masih ke depan, selain itu → *Grace* 14 hari; *Paid until* lewat → *Grace*; grace habis → *Suspended*. Saat suspended: modul premium mati, menu *Site setup* dikunci (super admin tetap bisa), laporan tetap bisa diexport, gerbang/LPR/kiosk dasar tetap jalan. *Cancelled*: site tertutup untuk staff-nya. Email otomatis ke site admin, billing email dan super admin: trial berakhir 7 hari dan 1 hari lagi, grace dimulai, suspended, aktif kembali (masing-masing sekali). Site admin melihat banner di dashboard. Mengubah status ke *Grace* secara manual tanpa tanggal otomatis memberi 14 hari dari hari itu.
* **Pemakaian (usage):** menit video intercom (dihitung dari panggilan yang dijawab) dan percakapan AI dicatat per site per bulan, beserta token AI. Kuota bulanan di paket (*Video intercom minutes*, *AI conversations*) **tidak menghentikan fitur**: kelebihannya dicatat dan ditagih sesuai tarif per paket (*Platform → Plans → Overage prices*). Email peringatan otomatis di 80% dan 100% ke site admin, billing email dan super admin. Laporan bulanan per site di **Platform → Usage** (pilih bulan, *Export CSV* untuk invoice), termasuk perkiraan biaya AI bila tarif token diisi di *System settings*. Percakapan AI dengan API key milik site sendiri dicatat terpisah dan tidak dihitung sebagai kelebihan. Untuk menghentikan fitur, matikan modulnya di *Subscription*.
* **Site tanpa aplikasi penghuni:** paket tanpa modul *Resident app* (atau super admin mematikannya di *Subscription*). Site itu lalu hanya memakai **Kiosk + dashboard Management**: resident di site itu tidak bisa masuk ke APK (muncul pesan *Your condominium does not use the Elix app*), tombol *Call a resident* di kiosk hilang dan AI assistant tidak menawarkan panggilan, tombol unduh APK di halaman Residents disembunyikan. Walk in, *I have an invitation* dan *Check out* tetap berjalan.

### 5b. Email (SMTP)
* Diatur super admin di **Platform → System settings → card Email → Set up / Change**: host, port, keamanan (STARTTLS/SSL/none), username, password (terenkripsi), alamat dan nama pengirim, reply-to. Bisa juga lewat `.env` (`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_SECURITY`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_FROM_ADDRESS`, `EMAIL_FROM_NAME`, `EMAIL_REPLY_TO`).
* Tombol *Save & send test email* langsung mengirim email uji (ke alamat yang diketik, atau email akun super admin).
* Tombol **Email log** di card Email menampilkan semua email 30 hari terakhir (terkirim, gagal beserta alasannya, antre). Email yang gagal karena jaringan atau server sibuk dicoba ulang otomatis sampai 3 kali.
* Untuk Microsoft 365 / Gmail dengan verifikasi dua langkah, gunakan *app password*.

### 5c. Landing page
* Alamat utama (`https://elixsmart.cloud/`) sekarang halaman produk: fitur, diagram alur 3D interaktif (tamu memanggil penghuni, tamu undangan, mobil di barrier; bisa diputar dan diklik per langkah), paket Basic/Standard/Premium tanpa harga (*Contact for quote*), PDPA, teknologi dan keamanan.
* Dashboard pindah ke **`/dashboard/`**; setelah login otomatis ke sana. Kalau browser sudah login, tombol di landing berubah jadi *Open dashboard*.
* Tombol *Request a demo* dan *Contact for quote* membuka email ke services@smartcitytechnologies.com.sg dengan template terisi (nama condo, jumlah unit, jumlah gerbang, kontak).
* Isi paket di landing mengikuti modul paket di sistem; kalau isi paket diubah di *Platform → Plans*, teks di `frontend/src/components/landing/Landing.tsx` perlu disesuaikan juga.

### 6. Sidebar & notifikasi dashboard
* Di tabel (Residents, Staff, Blocks & units, Condominiums) setiap baris punya satu tombol utama dan menu **⋯** untuk aksi lainnya; aksi hapus/remove ada paling bawah, berwarna merah, supaya tidak terklik tanpa sengaja. Di layar HP tabel berubah menjadi daftar kartu.
* *Access log* punya pilihan periode cepat (*Today / 7 days / 30 days*) dan *Custom* untuk rentang tanggal sendiri; semua waktu di dashboard ditampilkan dengan satu format (`09 Nov, 17:23`, tahun hanya kalau bukan tahun ini). Grafik *Traffic today* menampilkan pesan kosong sampai ada keputusan gerbang pertama hari itu, dan tombol *Open* di kartu Gates nonaktif selama gerbang belum punya relay.
* Top bar hanya menampilkan jejak lokasi kecil (*Operations › Invitations*); judul halaman ada di badan halaman saja. Daftar yang masih kosong menampilkan ikon, judul, penjelasan singkat, dan tombol tambah (misal *New invitation*, *Add vehicle*, *Register visitor*).
* Dropdown memakai gaya yang sama dengan kolom isian di sebelahnya; sidebar menampilkan bayangan dan panah di bawah kalau masih ada menu di luar layar (tablet); nama site yang panjang tampil dua baris; di *Gates & devices* angka *N need attention* bisa diklik untuk membuka jenis perangkat yang bermasalah; halaman login menuliskan bahwa password baru diminta ke site admin.
* *Site settings* dibagi per kartu (Condominium, Access policy, Visitor kiosk, PDPA). Tombol **Save changes** ada di bar yang selalu terlihat di bawah layar; saat ada perubahan yang belum disimpan, bar-nya menyala kuning dengan tombol *Discard*, dan browser mengingatkan kalau halaman ditutup sebelum disimpan. Ringkasan paket ada di baris *Your plan* paling atas (klik *Plan details* untuk modul dan limit).
* Grup menu sidebar (Operations, Community, Site setup, Platform) bisa dibuka-tutup seperti dropdown dengan klik judul grupnya; pilihan diingat per browser, dan grup halaman yang sedang dibuka selalu terbuka.
* **Bell notifikasi** di top bar menampilkan aktivitas baru secara realtime untuk site yang dipilih: tamu masuk/keluar, panggilan intercom dan hasilnya, gerbang terbuka/ditolak, booking dan feedback baru. Badge merah menunjukkan jumlah yang belum dibaca; 50 notifikasi terakhir disimpan di browser.

### 7. Role user
| Role | Cakupan |
|---|---|
| **Platform admin** (super admin, Smart City) | Semua site: condominium, System settings, semua user |
| **Site admin** | Site sendiri: semua menu termasuk Site setup, Gates & devices, Facilities & payments, dan akun Staff/Officer di menu **Staff** |
| **Staff** (kantor manajemen) | Site sendiri: residents & akun app-nya, dokumen resident, vehicles, invitations, bookings (batal/refund), balas feedback, plus semua tugas officer. Tidak bisa Site setup dan akun staff |
| **Officer** (guard) | Site sendiri: buka gerbang, Visitor list, intercom, block tamu, reports; residents/vehicles hanya lihat |

**Membuat site admin untuk sebuah site:** super admin membuka *Platform → Condominiums* → **Add site admin** di baris site itu (role *Site admin* sudah terpilih), atau memilih site di sidebar lalu *Community → Staff → Add staff*. Kolom *Site admins* di daftar Condominiums menunjukkan siapa admin tiap site (*None yet* bila belum ada). Akun itu hanya bisa membuka site-nya sendiri; satu orang bisa menjadi admin di beberapa site. Site admin lalu membuat akun Staff/Officer timnya sendiri (dalam batas paket).

### 8. Keamanan
* Login dashboard, APK dan Django admin dibatasi percobaannya (per IP dan per username); webhook kamera LPR juga dibatasi dan terkunci 5 menit setelah 20 password salah.
* Logout, ganti password atau menonaktifkan akun langsung mencabut semua sesi orang tersebut di semua perangkat.
* Site admin/Staff hanya bisa menautkan orang yang sudah terdaftar di site-nya; orang baru dibuat lewat *Add staff* / *Add resident*.
* Dokumen resident (PDF/JPG/PNG maks. 8 MB, dicek dari isi file) disimpan dengan nama acak dan hanya bisa diunduh lewat API: Site admin/Staff site itu dan resident pemiliknya saja, Officer tidak bisa. File ikut terhapus saat dokumen atau residentnya dihapus.
* Semua kolom rahasia (API key, password perangkat, HitPay, OpenAI) disimpan terenkripsi dan tidak pernah ditampilkan lagi. Kalau sudah tersimpan, muncul label *Saved* dengan tombol **Remove** untuk menghapusnya (bisa *Undo* sebelum Save); kolom yang dikosongkan tetap menyimpan nilai lama.
* Export Excel/CSV aman dari *formula injection*; HSTS aktif; log server tidak menyimpan token; dokumentasi API hanya untuk Platform admin.

### 9. Report Center
* Menu **Operations → Reports** untuk semua staff (Site admin, Staff dan Officer). Officer hanya melihat site/kondo masing-masing; super admin bisa memilih beberapa site atau *All sites* untuk laporan gabungan (konsolidasi).
* Jenis laporan: *Consolidated summary* (per site per hari), *Visitor*, *Access*, *Vehicle* (LPR), *Intercom*, *Invitation*. Masing-masing punya angka kunci, grafik tren harian, breakdown, dan tabel detail.
* Filter periode (Today, Yesterday, 7/30 hari, bulan ini/lalu, tahun ini, custom maks. 366 hari), filter per laporan, dan **smart search**: kata bebas mencari di semua kolom teks, token `key:value` untuk satu kolom, contoh `unit:05-12 plate:SGX1234 status:denied "Ace Aircon"`.
* **Print / PDF:** layout A4 landscape profesional (kop, periode, site, filter, angka kunci, tren, breakdown, semua baris s/d 5.000, nomor halaman, kolom tanda tangan Prepared/Reviewed/Approved). Pilih *Save as PDF* di dialog print.
* **Excel / CSV:** semua baris (s/d 50.000); Excel berisi sheet *Summary* dan *Details*.

---

## 🚀 Panduan Deployment Produksi (Tencent Cloud Debian)

### 1. Inisialisasi Server Awal
Setelah membeli paket Lighthouse Linux 2vCPUs/4GB RAM (Region Singapore/Debian OS), lakukan instalasi Docker pada mesin virtual:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
```

### 2. Menjalankan Kluster Aplikasi
1. Klon repositori proyek, lalu buat `.env.prod` dari `.env.example` (`DJANGO_DEBUG=false`, hostname publik, secret baru).
2. Publikasikan lewat **Cloudflare Tunnel**: di Zero Trust → Networks → Tunnels → *Public hostname*, arahkan hostname ke `HTTP` `localhost:8000`. Tidak ada port masuk yang perlu dibuka; HTTPS dan WebSocket ditangani Cloudflare. (Tanpa Cloudflare: jalankan dengan `--profile nginx` dan taruh sertifikat SSL di `./nginx/certs/`.)
3. Jalankan stack produksi di latar belakang:
   ```bash
   ENV_FILE=.env.prod docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```
4. Verifikasi status kontainer untuk memastikan seluruh layanan berjalan normal:
   ```bash
   ENV_FILE=.env.prod docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
   ```

---

## 📊 Manajemen Database & Monitoring
* **Sumber daya server (4 GB, 2 vCPU):** swap 2 GB (`swappiness=10`) sebagai bantalan saat RAM penuh; jadwal Celery (beat) berjalan di dalam worker (hemat ±100 MB); batas memori per container prod (web 512 MB, worker 768 MB, db 512 MB, redis 256 MB, gateway 128 MB) agar satu komponen yang bermasalah di-restart sendiri tanpa membuat server hang; log container dibatasi 3 × 10 MB; stack dev dimatikan saat tidak dipakai.
* **Server web:** Uvicorn 2 proses (satu per vCPU) dengan *connection pool* database; akses `http://` dialihkan ke `https://`. Patch keamanan Debian terpasang otomatis tiap hari (`unattended-upgrades`, tanpa reboot otomatis).
* **Kapasitas terukur** (uji beban Nov 2026, 1 site 300 unit): sekitar 45 request/detik; sampai ±50 orang beraktivitas bersamaan respons < 0,5 detik, 100–300 orang melambat 2–5 detik tanpa error, error mulai di atas ±400. 1.000 aplikasi terbuka (WebSocket) hampir tanpa beban. Batasnya CPU 2 vCPU; naik ke 4 vCPU bila banyak site ramai di satu server.
* **Backups** (menu *Platform → Backups*, khusus Platform admin):
  * *Platform backup*: seluruh database + semua file upload dalam satu arsip. Otomatis tiap malam jam 02:45 dan lewat tombol *Backup now*, disimpan 14 hari. Inilah yang dipakai untuk restore (langkahnya di README bagian *Backups*).
  * *Site export*: data satu site (JSON dan CSV yang bisa dibuka di Excel) beserta dokumen dan fotonya, untuk serah terima, audit, atau permintaan PDPA. Disimpan 7 hari, bukan untuk restore.
  * Password, kredensial perangkat/pembayaran, token pass dan template wajah tidak pernah ikut. Setiap unduhan tercatat (siapa, kapan, IP). Arsip ada di disk server: sesekali unduh platform backup dan simpan salinannya di tempat lain.
* **Akses Django Admin:** `https://api.domain-anda.com/v1/admin/` (Digunakan untuk mengonfigurasi `AccessGate`, token API kondo, dan pendaftaran `Condominium` baru).
* **Log Antrean Celery:** Anda dapat memeriksa aktivitas latar belakang pembukaan pintu via Docker log:
   ```bash
   sudo docker compose logs -f worker
   ```