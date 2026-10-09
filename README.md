# Kasir Offline Pro (Android)

Aplikasi kasir offline sederhana menggunakan Python + Kivy + SQLite.
Semua transaksi dan data produk tersimpan di database lokal `kasir_offline.db`.

## Fitur
- Produk: tambah, edit, hapus, stok, harga modal dan harga jual
- Kasir: keranjang, kuantitas, diskon persen, pembayaran tunai dan kembalian
- Transaksi: stok otomatis berkurang setelah transaksi tersimpan
- Laporan: omzet, modal barang terjual, laba kotor, jumlah transaksi
- Modal/pengeluaran: saldo modal awal dan pencatatan pengeluaran
- Struk: lihat transaksi terakhir dan simpan struk sebagai teks
- Backup/restore database dari/ke lokasi file yang dipilih

## Jalankan di komputer Linux (untuk uji coba)
```bash
python -m venv .venv
source .venv/bin/activate
pip install kivy
python main.py
```

## Build APK
Buildozer biasanya paling stabil di Linux desktop/VM, bukan langsung di Android/Termux.
```bash
pip install buildozer
buildozer android debug
```
Hasil APK biasanya muncul di folder `bin/`.

## Catatan Android
Aplikasi menyimpan database di direktori data privat aplikasi Android agar tidak hilang ketika layar ditutup. Gunakan menu Backup untuk mengekspor salinan database. Restore akan mengganti database aktif; lakukan hanya dengan file backup aplikasi ini.

## Keterbatasan versi awal
- Pembayaran saat ini tunai.
- Struk disimpan sebagai file teks; printer Bluetooth/thermal belum diintegrasikan.
- Tidak ada sinkronisasi cloud, agar tetap sepenuhnya offline.

## Build lewat GitHub Actions (alternatif jika build langsung di Termux gagal)
1. Buat repository GitHub baru lalu unggah semua isi folder proyek ini.
2. Buka tab **Actions** dan izinkan workflow bila diminta.
3. Pilih workflow **Build Android APK**, tekan **Run workflow**.
4. Setelah selesai, unduh artifact `KasirOfflinePro-debug-apk`; ZIP artifact berisi APK.

Build pertama memerlukan internet untuk mengunduh Android SDK/NDK dan dependensi. Setelah APK terpasang, transaksi aplikasi tetap offline.
