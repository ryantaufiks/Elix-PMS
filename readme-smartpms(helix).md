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
├── docker-compose.yml       # Layanan dasar (db, redis, web, worker, beat)
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
* **Check out di kiosk** (aktif/nonaktif per site: *Offer self check-out at the kiosk*): scan QR slip/screenshot atau ketik PIN di keypad. PIN unik di antara tamu yang sedang di dalam, hanya berlaku selama tamu on site, dan kiosk menolak PIN selama 1 menit setelah 5 kali salah. Check-out dengan wajah direncanakan (dicocokkan di PC kiosk, bisa dinonaktifkan). PIN juga disiapkan untuk sub access control unit.
* **Call a resident:** setelah penghuni membuka gerbang, kiosk menampilkan pass tamu (nomor pass, QR dan PIN di bawahnya) dengan pemberitahuan agar difoto/di-screenshot untuk check-out, plus tombol *Print slip* jika kiosk punya printer. Layar pass kembali ke awal setelah 25 detik agar tidak terbaca tamu berikutnya.
* **Visitor list (officer):** semua tamu tercatat sebagai *visit* dengan nomor pass harian yang sama: walk-in kiosk, walk-in yang didaftarkan guard (*Register visitor*, foto webcam opsional), check-in invitation (QR atau plat LPR; kamera exit otomatis check-out), dan gerbang yang dibuka lewat intercom. Officer bisa melihat jam check-in/check-out, *Print slip* dari printer pos jaga, *Edit* catatan, dan *Check out* satu per satu atau bulk. PIN tamu on site tampil di bawah nomor pass. Halaman **Visitor records** menampilkan check-in dan check-out terakhir tiap orang, dan tombol *Visits* membuka riwayat lengkapnya.
* Printer: jadikan printer 58 mm sebagai default printer di PC kiosk (ukuran kertas roll 58 mm) dan jalankan Chrome dengan `--kiosk --kiosk-printing` agar slip langsung tercetak tanpa dialog. Kiosk tanpa printer: hilangkan centang *Receipt printer connected* di *Gates & devices → Kiosks*, maka nomor pass dan QR ditampilkan di layar.

### 5. Report Center
* Menu **Operations → Reports** untuk semua staff (termasuk guard). Officer hanya melihat site/kondo masing-masing; super admin bisa memilih beberapa site atau *All sites* untuk laporan gabungan (konsolidasi).
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
* **Akses Django Admin:** `https://api.domain-anda.com/v1/admin/` (Digunakan untuk mengonfigurasi `AccessGate`, token API kondo, dan pendaftaran `Condominium` baru).
* **Log Antrean Celery:** Anda dapat memeriksa aktivitas latar belakang pembukaan pintu via Docker log:
   ```bash
   sudo docker compose logs -f worker
   ```