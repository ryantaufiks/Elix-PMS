# Visitor Management & Access Control System (VMS)

Sistem Manajemen Pengunjung Multi-Kondominium terintegrasi dengan LiveKit Video Interkom dan Kamera LPR Dahua berbasis Headless Architecture.

## 🏛️ Arsitektur Proyek
Sistem ini menggunakan arsitektur terpisah (*Decoupled/Headless*):
* **Backend:** Django 5.x + Django Rest Framework (DRF) + Django Channels + Celery
* **Web Admin Dashboard:** Next.js + TypeScript
* **Resident App & Tablet Kiosk:** Flutter

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
* Flutter SDK v3.x (untuk Mobile/Tablet)

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