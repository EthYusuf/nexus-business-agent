"""API anahtarı Ayarlar'a kaydedilene kadar bekler, sonra canlı testleri çalıştırır."""
import subprocess
import sys
import time

from app import db

db.init_db()
deadline = time.time() + 3 * 3600
while not db.get_setting("anthropic_api_key"):
    if time.time() > deadline:
        print("Zaman aşımı: API anahtarı girilmedi.")
        sys.exit(3)
    time.sleep(3)
print("API anahtarı algılandı, testler başlıyor...", flush=True)
sys.exit(subprocess.call([sys.executable, "-m", "tests.live_test"]))
