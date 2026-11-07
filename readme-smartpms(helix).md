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
├── docker-compose.yml       # Orkestrasi kontainer produksi di Tencent Cloud
├── nginx/
│   └── default.conf         # Konfigurasi reverse proxy SSL & routing API/WebSockets
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
* Node.js v18+ (untuk Next.js Dashboard)
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
* **Metode Otentikasi:** HTTP Basic Authentication.
* **Konfigurasi Kamera:** Masuk ke Web GUI Dahua -> **Setting > Network > Advanced Settings > HTTP Post** (atau **Alarm Server**). Aktifkan Auth, masukkan username dan password user Django yang valid.
* **Payload JSON:** Pastikan firmware kamera mengirim data dalam skema objek `PlateResult` berisi `plateNumber` dan `deviceID`.

### 2. Akses Kontrol Sonoff & Shelly (Cloud-to-Cloud)
* Pengaturan perangkat fisik di site wajib mengaktifkan mode **Inching / Auto-Off** (durasi 2-3 detik) di dalam aplikasi eWeLink atau Shelly Cloud.
* Django bertugas melempar instruksi `"on"` ke endpoint API *Cloud*, dan pemutusan arus dilakukan secara mandiri oleh relay fisik di gerbang kondo.

### 3. LiveKit Video Interkom
* Server Django bertugas memproduksi Short-Lived Access Token menggunakan API key dari LiveKit Cloud.
* Token ini dikirimkan via API ke **Tablet Kiosk** dan **Resident App** untuk menyambungkan ruang interkom (*room connection*) secara *peer-to-peer*.

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
1. Klon repositori proyek Anda ke dalam direktori `/opt/vms-project/`.
2. Letakkan sertifikat SSL Let's Encrypt Anda di direktori `./nginx/certs/`.
3. Jalankan seluruh orkestrasi kontainer di latar belakang:
   ```bash
   sudo docker compose up -d --build
   ```
4. Verifikasi status kontainer untuk memastikan seluruh layanan berjalan normal:
   ```bash
   sudo docker compose ps
   ```

---

## 📊 Manajemen Database & Monitoring
* **Akses Django Admin:** `https://api.domain-anda.com/v1/admin/` (Digunakan untuk mengonfigurasi `AccessGate`, token API kondo, dan pendaftaran `Condominium` baru).
* **Log Antrean Celery:** Anda dapat memeriksa aktivitas latar belakang pembukaan pintu via Docker log:
   ```bash
   sudo docker compose logs -f worker
   ```