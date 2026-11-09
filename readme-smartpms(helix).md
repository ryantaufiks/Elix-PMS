# Visitor Management & Access Control System (VMS)

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
* **Metode Otentikasi:** HTTP Basic Authentication dengan kredensial **khusus per kamera** (dashboard → Gates & devices → LPR cameras → *Webhook username/password*), bukan akun user Django.
* **Konfigurasi Kamera:** Masuk ke Web GUI Dahua -> **Setting > Network > Advanced Settings > HTTP Post** (atau **Alarm Server**). Aktifkan Auth, masukkan username dan password webhook kamera tersebut.
* **Aktifkan per site:** dashboard → Site settings → *Licence-plate recognition enabled* (default mati). Selama mati, payload hanya disimpan dan bisa dilihat di Gates & devices → LPR cameras → *Setup info*.
* **Payload JSON:** Plat dideteksi otomatis dari format Dahua umum (`PlateNumber`, `plateNumber`, dll.), atau atur *Plate field* (mis. `Picture.Plate.PlateNumber`) bila firmware memakai skema lain.

### 2. Akses Kontrol Sonoff & Shelly (Cloud-to-Cloud)
* Kredensial cloud diisi per site di dashboard → Gates & devices → *Cloud accounts*; tiap relay di tab *Relays* (mode Cloud, LAN, atau LAN lalu fallback ke Cloud). Uji dengan tombol *Test*.
* **Shelly:** server mengirim `on` dengan `toggle_after` = *pulse seconds*, sehingga relay mati sendiri walau Auto-Off belum diatur.
* **Sonoff (eWeLink):** perangkat wajib mengaktifkan mode **Inching / Auto-Off** (2-3 detik) di aplikasi eWeLink; Django hanya mengirim `"on"`.
* **Mode LAN** hanya bisa dipakai jika server dapat menjangkau jaringan site (mis. Tailscale subnet router di site).

### 3. LiveKit Video Interkom
* Server Django bertugas memproduksi Short-Lived Access Token (default 10 menit, satu token per room) menggunakan API key dari LiveKit Cloud. Isi URL, API key dan secret LiveKit di dashboard **Platform → System settings**, lalu tekan *Save & test connection* (alternatif: `LIVEKIT_*` di `.env` sebagai cadangan).
* Token ini dikirimkan via API ke **Tablet Kiosk** (saat memanggil unit) dan **Resident App** (saat menjawab) untuk bergabung ke room interkom. Media dialirkan melalui server SFU LiveKit Cloud (bukan *peer-to-peer*).
* **Alur utama:** tamu memilih unit di kiosk → HP penghuni berdering (push FCM + WebSocket) → penghuni menjawab video → **swipe to unlock** → gerbang kiosk terbuka dan tercatat di log akses.

### 4. Walk In & Printer Slip 58 mm
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
* **Site admin** (*Site setup → AI Assistant*): aktif/nonaktif, nama, salam, bahasa, panduan tambahan, API key OpenAI milik site (opsional), **materi pengetahuan** (teks: arah, fasilitas, aturan, kontak, akses MRT/taksi), **denah/peta** (gambar), dan *Try it* untuk menguji jawaban.
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
* Kiosk juga menampilkan suhu dan prakiraan cuaca di bawah tanggal.
* Home APK berisi 4 menu card (ikon sederhana) di atas *Recent activity* (maksimal 5; *See all* untuk semua riwayat).
* **Access:** buka gerbang dari jarak jauh dengan *swipe to open*. Hanya gate yang dicentang *Residents can open this gate from the app* (Gates & devices) yang muncul; setiap pembukaan tercatat (metode *App*, nama resident, unit).
* **Facility:** fasilitas dikonfigurasi admin di **Setup → Facilities & payments** (jam buka, hari buka, durasi slot, maks. slot per booking, booking per slot, kapasitas, harga per slot, deposit, berapa hari ke depan, batas booking per unit, batas waktu cancel, aturan, foto). Fasilitas gratis langsung confirmed. Fasilitas berbayar memakai **HitPay** milik kondo (PayNow, kartu, dll.) di dalam aplikasi: slot ditahan selama pembayaran (default 15 menit) dan booking hanya dikonfirmasi setelah API HitPay menyatakan pembayaran *completed* (halaman return dan webhook bertanda tangan hanya memicu pengecekan itu). Booking yang tidak dibayar otomatis dilepas. Refund dilakukan di dashboard HitPay lalu dicatat di menu **Bookings**.
* **Visitor:** daftar tamu unit, tab *On going* dan *History*, dengan jam check-in dan check-out.
* **Feedback:** resident memberi rating 1–5 bintang per kategori + komentar; Site admin atau Staff membalas di menu **Feedback** (rata-rata dan distribusi rating), balasan tampil di aplikasi.
* Setup HitPay: isi API key dan salt (terenkripsi) di *Online payments*; biarkan *Sandbox* tercentang untuk uji coba, hilangkan centang untuk live.

### 6. Sidebar & notifikasi dashboard
* Grup menu sidebar (Operations, Community, Site setup, Platform) bisa dibuka-tutup seperti dropdown dengan klik judul grupnya; pilihan diingat per browser, dan grup halaman yang sedang dibuka selalu terbuka.
* **Bell notifikasi** di top bar menampilkan aktivitas baru secara realtime untuk site yang dipilih: tamu masuk/keluar, panggilan intercom dan hasilnya, gerbang terbuka/ditolak, booking dan feedback baru. Badge merah menunjukkan jumlah yang belum dibaca; 50 notifikasi terakhir disimpan di browser.

### 7. Role user
| Role | Cakupan |
|---|---|
| **Platform admin** (super admin, Smart City) | Semua site: condominium, System settings, semua user |
| **Site admin** | Site sendiri: semua menu termasuk Site setup, Gates & devices, Facilities & payments, dan akun Staff/Officer di menu **Staff** |
| **Staff** (kantor manajemen) | Site sendiri: residents & akun app-nya, dokumen resident, vehicles, invitations, bookings (batal/refund), balas feedback, plus semua tugas officer. Tidak bisa Site setup dan akun staff |
| **Officer** (guard) | Site sendiri: buka gerbang, Visitor list, intercom, block tamu, reports; residents/vehicles hanya lihat |

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