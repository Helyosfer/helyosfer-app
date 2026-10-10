<div align="center">

<img src="assets/icon.png" width="96" alt="Helyosfer">

# Helyosfer

Kişisel finans için bir masaüstü uygulaması. Kayıtlarınız kendi bilgisayarınızda durur.

[English](README.md) · **Türkçe**

[![Testler](https://github.com/Helyosfer/helyosfer-app/actions/workflows/tests.yml/badge.svg)](https://github.com/Helyosfer/helyosfer-app/actions/workflows/tests.yml)
![Lisans: Apache 2.0](https://img.shields.io/badge/lisans-Apache--2.0-5646d4)
![Python 3.12](https://img.shields.io/badge/python-3.12-5646d4)
![Windows 10 ve sonrası](https://img.shields.io/badge/platform-Windows%2010%2B-5646d4)

</div>

![Genel bakış ekranı](docs/images/tr/overview.png)

Helyosfer'i kendi hesaplarımı, kart borçlarımı ve birikimlerimi tek yerde görmek
için yazdım. Bankaya bağlanmıyor, bir hesap açmanızı istemiyor; ne girerseniz o
var. Veriler bilgisayarınızdaki şifreli bir dosyada duruyor ve internete yalnızca
hisse, altın ve döviz fiyatlarını almak için çıkıyor.

> [!NOTE]
> Bu ilk sürüm (0.1.0). Şimdiye kadar yalnızca ben kullandım, o da kısa bir
> süre. İki bilgisayarda kurup denedim, testleri geçiyor, ama gözümden kaçan
> şeyler mutlaka vardır. Önemli kayıtlarınız için ara sıra yedek alın
> (Ayarlar → Yedek oluştur). Bir sorun görürseniz
> [buradan](https://github.com/Helyosfer/helyosfer-app/issues) yazabilirsiniz.

## Ne işe yarıyor

- **Hesaplar ve kredi kartları.** Vadesiz hesaplarınızı ve kartlarınızı
  ekliyorsunuz, gelir ve giderleri giriyorsunuz. Kartın limiti, hesap kesim günü
  ve taksitli alışverişlerin kaçıncı taksitte olduğu kart ekranında görünüyor.
- **Borçlar.** Kredi gibi aylık taksitli borçları takip ediyor. Taksiti elle
  ödeyebilir ya da seçtiğiniz hesaptan her ay otomatik düşmesini
  söyleyebilirsiniz.
- **Abonelikler ve düzenli ödemeler.** Kira, fatura, maaş gibi tekrarlayan
  kalemler. Haftalıktan yıllığa kadar ayarlanabiliyor.
- **Birikim hedefleri.** Bir hedef koyup para ayırıyorsunuz; isterseniz her ay
  belirli bir tutar kendiliğinden aktarılıyor.
- **Yatırımlar.** Hisse, altın, döviz ve kripto. Güncel fiyatı çekip elinizdekinin
  lira karşılığını ve kâr-zararını gösteriyor.
- **Bütçe ve diğer araçlar.** Aylık bütçe planı, takvim, kredi ve mevduat
  hesaplayıcıları, harcamalarınıza dair bir özet ve "geçen ayın 15'inde ne kadar
  param vardı" sorusunun cevabı.

Tutarlar Türk lirası üzerinden. Arayüz Türkçe ve İngilizce, koyu ve açık tema var.

## Ekran görüntüleri

| Kartlar ve hesaplar | Yatırımlar |
| --- | --- |
| ![Hesaplar ve bir kredi kartı](docs/images/tr/accounts.png) | ![Varlıklar, güncel fiyat ve kâr-zarar](docs/images/tr/portfolio.png) |
| **Bütçe planı** | **Özet ve tahminler** |
| ![Aylık plana göre giderler](docs/images/tr/budget.png) | ![Finansal sağlık puanı ve ay sonu tahmini](docs/images/tr/insights.png) |
| **Birikim hedefleri** | **Açık tema** |
| ![İki birikim hedefi](docs/images/tr/savings.png) | ![Açık temada genel bakış](docs/images/tr/overview-light.png) |

## Bilmeye değer birkaç şey

Geçmişe dönük kayıt girebilirsiniz. Ocak ayındaki bir harcamayı bugün
girdiğinizde grafik ocaktan itibaren yeniden çizilir; bakiye geçmişi, kaydı
girdiğiniz güne değil işlemin tarihine bakar.

Uygulamayı her gün açmanız gerekmiyor. Bir ay açmasanız bile otomatik ödemeler,
taksitler ve birikim aktarımları, açtığınızda kendi günlerinin tarihiyle
kaydedilir.

Yanlış girdiğiniz her şeyi düzeltebilir ya da silebilirsiniz. Bir borç ödemesini
sildiğinizde taksit borca geri döner, bir varlık satışını sildiğinizde varlık
portföye geri gelir.

Okunamayan bir kayıt olursa uygulama onu sıfır sayıp toplamı yanlış göstermez;
toplamı hiç göstermez ve durumu söyler.

## Verileriniz

- Her şey bilgisayarınızda, Windows kullanıcı klasörünüzdeki bir veritabanında
  durur. Bir sunucuya gönderilmez.
- Tutarlar ve açıklamalar diskte şifreli tutulur (AES-256-GCM). Şifreleme
  anahtarını Windows korur (DPAPI).
- Uygulama bir şifreyle açılır. Şifrenin kendisi saklanmaz, yalnızca özeti
  (Argon2id) saklanır. Şifrenizi unutursanız kurtarmanın bir yolu yok.
- Yedek, ayrı bir şifreyle korunan tek bir dosyadır. Başka bir bilgisayara
  geçerken yedeği orada geri yüklemeniz yeterli.
- Kullanım verisi toplamıyor, reklam göstermiyor.

Daha fazlası için (İngilizce): [anahtar yönetimi](docs/KEY_MANAGEMENT.md),
[yedekleme ve kurtarma](docs/BACKUP_RECOVERY.md), [SECURITY.md](SECURITY.md).

## Kurulum

[Son sürüm sayfasından](https://github.com/Helyosfer/helyosfer-app/releases/latest)
`Helyosfer-<sürüm>-setup.exe` dosyasını indirip çalıştırın. Yönetici izni
istemez, bilgisayarda Python ya da başka bir şeyin kurulu olması gerekmez.
Windows 10 veya sonrası, 64 bit.

Dosya imzalı değil, bu yüzden Windows ilk çalıştırmada "bilinmeyen yayıncı"
uyarısı verir. **Ek bilgi**'ye, sonra **Yine de çalıştır**'a basarak geçebilirsiniz.
İndirdiğiniz dosyayı doğrulamak isterseniz SHA-256 değerleri sürüm sayfasında.

Kurmak istemiyorsanız aynı sayfadaki zip dosyasını bir klasöre açıp
`Helyosfer.exe`'yi çalıştırabilirsiniz; `_internal` klasörünü yanından ayırmayın.

İlk açılışta bir şifre belirleyip ilk hesabınızı ekliyorsunuz. Uygulama, Windows
Türkçe ise Türkçe, değilse İngilizce açılır; dili Ayarlar'dan değiştirebilirsiniz.

Programı kaldırmak ya da güncellemek kayıtlarınıza dokunmaz, onlar ayrı bir
klasörde durur.

## Kaynak koddan çalıştırmak

Python 3.12 gerekiyor.

```bash
python -m pip install -r requirements-runtime.txt
```

```bash
python -m app
```

Paketi kendiniz derlemek isterseniz:

```bash
python -m pip install pyinstaller
```

```bash
python scripts/build_windows.py --zip
```

Bu, `dist/` altına zip dosyasını yazar. Kurulum programı için
[Inno Setup 6](https://jrsoftware.org/isinfo.php) kurulu olmalı:

```bash
python scripts/build_windows.py --installer
```

## Geliştirenler için

Python 3.12, arayüzde PySide6 (Qt Quick), veritabanı olarak SQLite kullanıyor.

```text
app/         Arayüz: Qt Quick ekranları, denetleyiciler, Türkçe metinler
database/    SQLite şeması, geçişler ve bakiye defteri
services/    İş mantığı: işlemler, fiyatlar, bütçe, yedekleme
security/    Giriş, şifre kuralları, deneme sınırlaması
utils/       Para hesabı, şifreleme, anahtar saklama, dosya yolları
ui/          Servis iletilerinin İngilizce karşılıkları
tests/       Testler
scripts/     Derleme ve denetim betikleri
```

Geliştirme bağımlılıklarını kurup testleri çalıştırmak için:

```bash
python -m pip install -r requirements.txt
```

```bash
python run_tests.py
```

Testler her değişiklikte Linux ve Windows'ta çalışıyor. Mimari notları
[docs](docs/) klasöründe, katkı kuralları [CONTRIBUTING.md](CONTRIBUTING.md)
dosyasında (ikisi de İngilizce). Nelerin denenip denenmediği
[yol haritasında](docs/ROADMAP.md) yazıyor.

## Lisans

[Apache 2.0](LICENSE). Ayrıca [NOTICE](NOTICE) dosyasına bakın.
