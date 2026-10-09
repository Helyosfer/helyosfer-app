"""The interface in Turkish: English text as written in the code -> Turkish.

`tests/test_interface_language.py` keeps this complete: every text the
interface passes to `say`, `later` or `qsTr` has an entry here, the entry
keeps the same placeholders, and nothing here is left over from text that no
longer exists.

Words that fill a blank in a sentence ("amount", "unit price") are written
so that they read correctly inside "Lütfen ... girin".
"""

TEXT = {
    # -- pieces joined to other text --------------------------------------
    " (Error: {0})": " (Hata: {0})",
    " from today": " (bugüne göre)",
    " since then": " (o günden beri)",
    ", left out {0} that were already in the account": "; zaten hesapta olan {0} işlem atlandı",
    ", skipped {0} rows that could not be read": "; okunamayan {0} satır atlandı",
    "{0}. Net effect on the balance: {1}{2} ₺.": "{0}. Bakiyeye net etkisi: {1}{2} ₺.",

    # -- counts and amounts -----------------------------------------------
    "%1 a month": "ayda %1",
    "%1 available": "%1 kullanılabilir",
    "%1 holdings have no current price and are counted at cost":
        "%1 varlığın güncel fiyatı yok; maliyetiyle sayılıyor",
    "1 holding has no current price and is counted at cost":
        "1 varlığın güncel fiyatı yok; maliyetiyle sayılıyor",
    "%1 installments": "%1 taksit",
    "%1 is taken for %2 each month.": "%2 için her ay %1 alınır.",
    "%1 left in %2 installments": "%2 taksitte %1 kaldı",
    "%1 left in 1 installment": "1 taksitte %1 kaldı",
    "%1 of %2": "%1 / %2",
    "%1 owed": "%1 borç",
    "%1 saved of %2": "%2 hedefin %1 kadarı birikti",
    "%1 to go": "%1 kaldı",
    "%1 will be taken from the account and the debt closed.":
        "Hesaptan %1 alınır ve borç kapatılır.",
    "%1, %2 transactions": "%1, %2 işlem",
    "1 day": "1 gün",
    "{0} days": "{0} gün",
    "1 month": "1 ay",
    "{0} months": "{0} ay",
    "1 year": "1 yıl",
    "3 months": "3 ay",
    "6 months": "6 ay",
    "1 day overdue": "1 gün gecikti",
    "{0} days overdue": "{0} gün gecikti",
    "in {0} days": "{0} gün sonra",
    "today": "bugün",
    "tomorrow": "yarın",
    "Today": "Bugün",
    "1W": "1H",
    "1M": "1A",
    "1Y": "1Y",
    "past week": "son bir hafta",
    "past month": "son bir ay",
    "past year": "son bir yıl",
    "1 entry": "1 kayıt",
    "{0} entries": "{0} kayıt",
    "{0} of {1} paid": "{1} taksitin {0} tanesi ödendi",
    "{0} ₺ a month": "ayda {0} ₺",
    "{0} ₺ a month reaches it in time": "ayda {0} ₺ ile zamanında tamamlanır",
    "{0} ₺ above the usual {1} ₺": "olağan {1} ₺ tutarın {0} ₺ üstünde",
    "{0} ₺ available": "{0} ₺ kullanılabilir",
    "{0} ₺ left": "{0} ₺ kaldı",
    "{0} ₺ over": "{0} ₺ aşıldı",
    "of %1": "/ %1",
    "owed of %1": "borç; limit %1",
    "out of 100": "100 üzerinden",
    "seen {0} times": "{0} kez görüldü",
    "by {0} {1}": "son tarih {0} {1}",
    "currently %1": "şu an %1",
    "Year {0}": "{0}. yıl",

    # -- words that fill a blank ------------------------------------------
    "amount": "tutar",
    "card limit": "kart limiti",
    "charge amount": "masraf tutarı",
    "current debt": "güncel borç",
    "deposit amount": "mevduat tutarı",
    "income change": "gelir değişimi",
    "loan amount": "kredi tutarı",
    "monthly contribution": "aylık katkı",
    "monthly interest rate": "aylık faiz oranı",
    "monthly payment": "aylık taksit",
    "number of days": "gün sayısı",
    "number of installments": "taksit sayısı",
    "number of months": "ay sayısı",
    "number of years": "yıl sayısı",
    "payment day": "ödeme günü",
    "regular amount": "düzenli tutar",
    "spending change": "gider değişimi",
    "starting amount": "başlangıç tutarı",
    "target amount": "hedef tutar",
    "unit price": "birim fiyat",
    "warning level": "uyarı eşiği",
    "yearly interest rate": "yıllık faiz oranı",
    "yearly return": "yıllık getiri",
    "Enter the {0}.": "Lütfen {0} girin.",
    "Enter a valid {0}, for example 1.250,50.": "Lütfen geçerli bir {0} girin; örneğin 1.250,50.",
    "Enter the {0} as a whole number.": "Lütfen {0} için tam sayı girin.",
    "Enter the {0}, for example 3,49.": "Lütfen {0} girin; örneğin 3,49.",
    "Enter the {0} as a percentage, for example 10 or -5.":
        "Lütfen {0} için yüzde girin; örneğin 10 veya -5.",
    "The {0} must be between {1} and {2}.": "Girilen {0}, {1} ile {2} arasında olmalı.",
    "The {0} must be between -100 and 1000.": "Girilen {0}, -100 ile 1000 arasında olmalı.",
    "The {0} must be greater than 0.": "Girilen {0}, 0'dan büyük olmalı.",

    # -- navigation and section titles ------------------------------------
    "Overview": "Genel bakış",
    "Assets": "Varlıklar",
    "Cards and accounts": "Kartlar ve hesaplar",
    "Debts and payments": "Borçlar ve ödemeler",
    "Subscriptions": "Abonelikler",
    "Savings goals": "Birikim hedefleri",
    "Tools": "Araçlar",
    "Settings": "Ayarlar",
    "Light theme": "Açık tema",
    "Dark theme": "Koyu tema",
    "Lock": "Kilitle",
    "Encrypted on this device": "Bu cihazda şifreli",
    "Budget plan": "Bütçe planı",
    "Calendar": "Takvim",
    "Calculators": "Hesaplayıcılar",
    "Insights": "İçgörüler",
    "What if": "Ya şöyle olursa",
    "Past balance": "Geçmiş bakiye",
    "This section is being built.": "Bu bölüm hazırlanıyor.",

    # -- buttons and states -----------------------------------------------
    "Add": "Ekle",
    "Done": "Tamamlandı",
    "Calculate": "Hesapla",
    "Cancel": "Vazgeç",
    "Choose": "Seç",
    "Close": "Kapat",
    "Compare": "Karşılaştır",
    "Continue": "Devam",
    "Delete": "Sil",
    "Delete for good": "Kalıcı olarak sil",
    "Edit": "Düzenle",
    "Export": "Dışa aktar",
    "Ignore": "Yok say",
    "Import": "İçe aktar",
    "Pay": "Öde",
    "Pay now": "Şimdi öde",
    "Pay off": "Borcu kapat",
    "Receive now": "Şimdi al",
    "Remove": "Kaldır",
    "Rename": "Yeniden adlandır",
    "Reschedule": "Tarihi değiştir",
    "Restore": "Geri yükle",
    "Save": "Kaydet",
    "Sell": "Sat",
    "Show": "Göster",
    "Skip next": "Sonrakini atla",
    "Stop": "Durdur",
    "Take back": "Geri al",
    "This is fine": "Sorun değil",
    "Track": "Takip et",
    "Turn on": "Aç",
    "Unlock": "Kilidi aç",
    "Checking…": "Denetleniyor…",
    "Creating…": "Oluşturuluyor…",
    "Deleting…": "Siliniyor…",
    "Importing…": "İçe aktarılıyor…",
    "Looking up…": "Fiyat aranıyor…",
    "Looking…": "Aranıyor…",
    "Paying…": "Ödeniyor…",
    "Saving…": "Kaydediliyor…",
    "Searching…": "Aranıyor…",
    "Selling…": "Satılıyor…",
    "Stopping…": "Durduruluyor…",
    "Updating prices…": "Fiyatlar güncelleniyor…",
    "Working…": "İşleniyor…",

    # -- sign-in and first run --------------------------------------------
    "Welcome back": "Tekrar hoş geldiniz",
    "Your records are encrypted on this device. Enter your password to open them.":
        "Kayıtlarınız bu cihazda şifreli duruyor. Açmak için şifrenizi girin.",
    "Password": "Şifre",
    "Create your password": "Şifrenizi oluşturun",
    "Choose a new password": "Yeni bir şifre belirleyin",
    "This password protects your records on this device. It is never sent anywhere, "
    "and it cannot be recovered if you forget it.":
        "Bu şifre kayıtlarınızı bu cihazda korur. Hiçbir yere gönderilmez; "
        "unutursanız kurtarılamaz.",
    "Your current password is older than today's rules. Set a stronger one to continue.":
        "Mevcut şifreniz bugünkü kurallardan eski. Devam etmek için daha güçlü bir şifre belirleyin.",
    "Repeat password": "Şifreyi yineleyin",
    "At least 12 characters, with upper and lower case letters, a digit and a symbol.":
        "En az 12 karakter; büyük ve küçük harf, rakam ve simge içermeli.",
    "Add your first account": "İlk hesabınızı ekleyin",
    "Start with the account you use most. You can add cards and other accounts later.":
        "En çok kullandığınız hesapla başlayın. Kartları ve diğer hesapları sonra ekleyebilirsiniz.",
    "Account name": "Hesap adı",
    "Main account": "Ana hesap",
    "Current balance (₺)": "Güncel bakiye (₺)",
    "Open Helyosfer": "Helyosfer'i aç",
    "Something went wrong. Try again.": "Bir sorun oluştu. Yeniden deneyin.",
    "Nothing was changed. Close this window when you are ready.":
        "Hiçbir şey değiştirilmedi. Hazır olduğunuzda bu pencereyi kapatın.",
    "Backup restored": "Yedek geri yüklendi",
    "Your records, encryption key and settings were replaced with the ones in the backup.":
        "Kayıtlarınız, şifreleme anahtarınız ve ayarlarınız yedektekilerle değiştirildi.",
    "Close Helyosfer and open it again to continue.":
        "Devam etmek için Helyosfer'i kapatıp yeniden açın.",

    # -- overview ----------------------------------------------------------
    "Search transactions, accounts and categories   Ctrl+K":
        "İşlem, hesap ve kategori ara   Ctrl+K",
    "Nothing matches.": "Eşleşen bir şey yok.",
    "Account": "Hesap",
    "Category": "Kategori",
    "Transaction": "İşlem",
    "Cash or checking": "Nakit veya vadesiz",
    "Credit card": "Kredi kartı",
    "Income category": "Gelir kategorisi",
    "Spending category": "Gider kategorisi",
    "Add transaction": "İşlem ekle",
    "Total balance": "Toplam bakiye",
    "No history for this period yet": "Bu dönem için henüz geçmiş yok",
    "Not enough history to draw yet": "Çizmek için henüz yeterli geçmiş yok",
    "Income": "Gelir",
    "Spending": "Gider",
    "Net": "Net",
    "Coming up": "Yaklaşanlar",
    "Pending transaction": "Bekleyen işlem",
    "Taken automatically": "Otomatik alınır",
    "Pay by hand": "Elle ödenir",
    "Recent transactions": "Son işlemler",
    "Transactions you add will appear here.": "Eklediğiniz işlemler burada görünür.",
    "Unreadable record": "Okunamayan kayıt",
    "The overview could not be loaded.": "Genel bakış yüklenemedi.",

    # -- transaction form --------------------------------------------------
    "Edit transaction": "İşlemi düzenle",
    "Amount (₺)": "Tutar (₺)",
    "Choose an account": "Hesap seçin",
    "Choose a category": "Kategori seçin",
    "Choose an account.": "Bir hesap seçin.",
    "Choose a category.": "Bir kategori seçin.",
    "Installments": "Taksit",
    "Single payment": "Tek çekim",
    "Description (optional)": "Açıklama (isteğe bağlı)",
    "Date": "Tarih",
    "DD.MM.YYYY": "GG.AA.YYYY",
    "A future date is saved as a pending transaction and applied on that day.":
        "İleri tarihli işlem bekleyen işlem olarak kaydedilir ve o gün uygulanır.",
    "Enter the date as DD.MM.YYYY, for example 08.10.2026.":
        "Tarihi GG.AA.YYYY biçiminde girin; örneğin 08.10.2026.",
    "This could not be saved. Check the values and try again.":
        "Kaydedilemedi. Değerleri kontrol edip yeniden deneyin.",

    # -- cards and accounts ------------------------------------------------
    "Cash and checking": "Nakit ve vadesiz",
    "Card debt": "Kart borcu",
    "Add account": "Hesap ekle",
    "No accounts yet. Add the account you use most to get started.":
        "Henüz hesap yok. Başlamak için en çok kullandığınız hesabı ekleyin.",
    "No transactions yet.": "Henüz işlem yok.",
    "Freeze": "Dondur",
    "Frozen": "Donduruldu",
    "Card limit": "Kart limiti",
    "Available": "Kullanılabilir",
    "Online payments": "İnternet alışverişi",
    "Pay debt": "Borç öde",
    "Delete card": "Kartı sil",
    "statement on day %1": "hesap kesim günü %1",
    "Accounts could not be loaded.": "Hesaplar yüklenemedi.",
    "Card name": "Kart adı",
    "Current debt (₺)": "Güncel borç (₺)",
    "Card limit (₺)": "Kart limiti (₺)",
    "Statement day": "Hesap kesim günü",
    "Card number (optional)": "Kart numarası (isteğe bağlı)",
    "Used only to show the last four digits": "Yalnızca son dört haneyi göstermek için",
    "Only the last four digits and the card network are kept. The full number is never stored.":
        "Yalnızca son dört hane ve kart ağı tutulur. Numaranın tamamı hiçbir zaman saklanmaz.",
    "Enter the full card number, or leave it empty.":
        "Kart numarasının tamamını girin ya da boş bırakın.",
    "Pay card debt": "Kart borcunu öde",
    "Pay from": "Ödenecek hesap",
    "Choose the account to pay from.": "Ödemenin yapılacağı hesabı seçin.",
    "The payment cannot exceed the current debt of {0} ₺.":
        "Ödeme, {0} ₺ olan güncel borcu aşamaz.",
    "Delete %1?": "%1 silinsin mi?",
    "The card, its transactions and its installment plans are removed. This cannot be undone.":
        "Kart, işlemleri ve taksit planları silinir. Bu işlem geri alınamaz.",

    # -- debts and payments --------------------------------------------------
    "Total owed": "Toplam borç",
    "Due each month": "Aylık ödeme",
    "Add debt": "Borç ekle",
    "Debts": "Borçlar",
    "No active debts. Loans and installment debts you add appear here.":
        "Etkin borç yok. Eklediğiniz krediler ve taksitli borçlar burada görünür.",
    "automatic on day %1": "her ayın %1. günü otomatik",
    "Pay automatically": "Otomatik öde",
    "Automatic: on": "Otomatik: açık",
    "Automatic: off": "Otomatik: kapalı",
    "Pending transactions": "Bekleyen işlemler",
    "Nothing is waiting. Transactions saved with a future date appear here until that day.":
        "Bekleyen bir şey yok. İleri tarihli kaydedilen işlemler o güne kadar burada görünür.",
    "This list could not be loaded.": "Liste yüklenemedi.",
    "A loan or any debt paid in fixed monthly installments.":
        "Sabit aylık taksitlerle ödenen bir kredi ya da herhangi bir borç.",
    "Name": "Ad",
    "Car loan": "Taşıt kredisi",
    "Monthly payment (₺)": "Aylık taksit (₺)",
    "Months": "Ay",
    "Pay automatically each month": "Her ay otomatik öde",
    "On day": "Ayın günü",
    "Automatic installments are taken from your first account when you open Helyosfer "
    "on or after that day.":
        "Otomatik taksitler, o gün ya da sonrasında Helyosfer'i açtığınızda ilk hesabınızdan alınır.",
    "Pay installments": "Taksit öde",
    "Pay off this debt": "Bu borcu kapat",
    "Installments to pay (1–%1)": "Ödenecek taksit sayısı (1–%1)",
    "Each installment is %1.": "Her taksit %1.",
    "Enter how many installments to pay.": "Kaç taksit ödeneceğini girin.",
    "Installments left": "Kalan taksit",
    "Day of the month (1–31)": "Ayın günü (1–31)",
    "New date": "Yeni tarih",
    "Choose a date after today.": "Bugünden sonraki bir tarih seçin.",

    # -- subscriptions ------------------------------------------------------
    "Recurring cost per month": "Aylık tekrarlayan gider",
    "Active": "Etkin",
    "Add recurring payment": "Tekrarlayan ödeme ekle",
    "Subscriptions and recurring payments": "Abonelikler ve tekrarlayan ödemeler",
    "Nothing recurring yet. Subscriptions are also picked up automatically from card spending.":
        "Henüz tekrarlayan bir şey yok. Abonelikler kart harcamalarından da kendiliğinden yakalanır.",
    "automatic": "otomatik",
    "manual": "elle",
    "Change amount": "Tutarı değiştir",
    "New amount (₺)": "Yeni tutar (₺)",
    "Payment": "Ödeme",
    "Music subscription": "Müzik aboneliği",
    "Salary": "Maaş",
    "Repeats": "Tekrar",
    "Weekly": "Haftalık",
    "Every two weeks": "İki haftada bir",
    "Monthly": "Aylık",
    "Every three months": "Üç ayda bir",
    "Yearly": "Yıllık",
    "Irregular": "Düzensiz",
    "Next due": "Sonraki vade",
    "Add to the account automatically when due": "Vadesi gelince hesaba otomatik ekle",
    "Take from the account automatically when due": "Vadesi gelince hesaptan otomatik al",
    "Enter a name.": "Bir ad girin.",
    "This payment is no longer active.": "Bu ödeme artık etkin değil.",
    "Stop %1?": "%1 durdurulsun mu?",
    "It will no longer be charged or shown here. Past transactions stay as they are.":
        "Artık tahsil edilmez ve burada görünmez. Geçmiş işlemler olduğu gibi kalır.",
    "Add this month's %1 back to the account": "Bu ayın %1 tutarını hesaba geri ekle",

    # -- savings goals --------------------------------------------------------
    "Saved in goals": "Hedeflerde biriken",
    "Total target": "Toplam hedef",
    "New goal": "Yeni hedef",
    "Money you move into a goal is set aside from your accounts until you take it back.":
        "Bir hedefe aktardığınız para, geri alana kadar hesaplarınızdan ayrı tutulur.",
    "No goals yet. Create one to set money aside for something specific.":
        "Henüz hedef yok. Belirli bir şey için para ayırmak üzere bir hedef oluşturun.",
    "Reached": "Tamamlandı",
    "Nothing left to save.": "Biriktirilecek bir şey kalmadı.",
    "Add money": "Para ekle",
    "Save automatically": "Otomatik biriktir",
    "Change automatic saving": "Otomatik birikimi değiştir",
    "Automatic: %1": "Otomatik: %1",
    "{0} ₺ on day {1} of each month, from {2}": "her ayın {1}. günü {0} ₺, {2} hesabından",
    "Save for %1 automatically": "%1 için otomatik biriktir",
    "The amount moves from the account into the goal once a month, the next time you open "
    "Helyosfer on or after that day. A month the account cannot cover is skipped.":
        "Tutar ayda bir kez, o gün ya da sonrasında Helyosfer'i ilk açtığınızda hesaptan hedefe "
        "aktarılır. Hesabın karşılayamadığı ay atlanır.",
    "Amount each month (₺)": "Aylık tutar (₺)",
    "Turn off": "Otomatiği kapat",
    "day of the month": "ayın günü",
    "Delete goal": "Hedefi sil",
    "The target date has passed": "Hedef tarihi geçti",
    "New savings goal": "Yeni birikim hedefi",
    "Holiday fund": "Tatil birikimi",
    "Target amount (₺)": "Hedef tutar (₺)",
    "Target date (optional)": "Hedef tarihi (isteğe bağlı)",
    "Create goal": "Hedef oluştur",
    "Enter a name for the goal.": "Hedef için bir ad girin.",
    "Choose a target date after today.": "Bugünden sonraki bir hedef tarihi seçin.",
    "Add to %1": "%1 hedefine ekle",
    "Take from %1": "%1 hedefinden al",
    "The %1 saved in it goes back to the account you choose.":
        "İçinde biriken %1, seçtiğiniz hesaba geri döner.",
    "This goal holds no money. Deleting it cannot be undone.":
        "Bu hedefte para yok. Silme işlemi geri alınamaz.",
    "Take from": "Alınacak hesap",
    "Return to": "Geri dönecek hesap",
    "Add the money to": "Paranın ekleneceği hesap",
    "Choose the account that receives the saved money.":
        "Biriken paranın döneceği hesabı seçin.",

    # -- assets -----------------------------------------------------------------
    "Portfolio value": "Portföy değeri",
    "Cost": "Maliyet",
    "Profit or loss": "Kâr veya zarar",
    "Add asset": "Varlık ekle",
    "Refresh prices": "Fiyatları yenile",
    "Holding": "Varlık",
    "Quantity": "Adet",
    "Unit cost": "Birim maliyet",
    "Price": "Fiyat",
    "Value": "Değer",
    "No assets yet. Add shares, gold, currency or crypto to follow their value.":
        "Henüz varlık yok. Değerini izlemek için hisse, altın, döviz ya da kripto ekleyin.",
    "No price": "Fiyat yok",
    "Purchases and sales": "Alımlar ve satışlar",
    "Your assets could not be loaded.": "Varlıklarınız yüklenemedi.",
    "Record something you bought. Prices are entered and shown in lira.":
        "Satın aldığınız bir şeyi kaydedin. Fiyatlar lira olarak girilir ve gösterilir.",
    "Kind": "Tür",
    "Symbol": "Sembol",
    "Type of gold": "Altın türü",
    "Gram gold": "Gram altın",
    "Quarter gold coin": "Çeyrek altın",
    "Half gold coin": "Yarım altın",
    "Full gold coin": "Tam altın",
    "Ounce of gold": "Ons altın",
    "Name (optional)": "Ad (isteğe bağlı)",
    "Shown in your list instead of the symbol": "Listenizde sembol yerine gösterilir",
    "Unit price (₺)": "Birim fiyat (₺)",
    "Current price": "Güncel fiyat",
    "Take the cost from an account": "Tutarı bir hesaptan düş",
    "Enter a symbol first.": "Önce bir sembol girin.",
    "No price was found for this symbol. You can still enter one yourself.":
        "Bu sembol için fiyat bulunamadı. Fiyatı kendiniz de girebilirsiniz.",
    "Choose the kind of asset.": "Varlık türünü seçin.",
    "Enter the symbol.": "Sembolü girin.",
    "Enter a valid quantity, for example 2 or 0,5.": "Geçerli bir adet girin; örneğin 2 veya 0,5.",
    "The quantity must be greater than 0.": "Adet 0'dan büyük olmalı.",
    "Sell %1": "%1 sat",
    "You hold %1, bought at %2 each.": "Elinizde %1 var; birim maliyeti %2.",
    "Quantity to sell": "Satılacak adet",
    "Add to account": "Eklenecek hesap",
    "Choose the account that receives the money.": "Paranın ekleneceği hesabı seçin.",

    # -- budget plan --------------------------------------------------------------
    "Previous month": "Önceki ay",
    "Next month": "Sonraki ay",
    "Copy to the rest of the year": "Yılın kalanına kopyala",
    "Add plan item": "Plan kalemi ekle",
    "Edit plan item": "Plan kalemini düzenle",
    "Planned income": "Planlanan gelir",
    "Planned spending": "Planlanan gider",
    "Reserved for recurring payments": "Tekrarlayan ödemelere ayrılan",
    "Left to plan": "Planlanabilir kalan",
    "Spending against the plan": "Plana göre giderler",
    "Plan items": "Plan kalemleri",
    "Nothing planned for this month. Add your expected income and the spending you want to cap.":
        "Bu ay için plan yok. Beklediğiniz geliri ve sınırlamak istediğiniz harcamaları ekleyin.",
    "No category": "Kategorisiz",
    "every month": "her ay",
    "carries over": "devreder",
    "carried over": "devredildi",
    "overspent last month": "geçen ay aşıldı",
    "Copied {0} items to the rest of {1}.": "{0} kalem {1} yılının kalanına kopyalandı.",
    "The rest of the year already has these items.": "Yılın kalanında bu kalemler zaten var.",
    "This item repeats every month. Your change applies to %1 only.":
        "Bu kalem her ay tekrarlanıyor. Değişikliğiniz yalnızca %1 için geçerli olur.",
    "For %1. Give spending a category to track it against what you actually spend.":
        "%1 için. Harcamayı gerçek harcamanızla karşılaştırmak için bir kategori verin.",
    "Groceries": "Market",
    "Category (optional)": "Kategori (isteğe bağlı)",
    "Use this for every month": "Her ay için kullan",
    "Change the following months as well": "Sonraki ayları da değiştir",
    "This item repeats every month. Your change applies from %1 on.":
        "Bu kalem her ay tekrarlanıyor. Değişikliğiniz %1 ve sonraki aylar için geçerli olur.",
    "Carry what is left into next month": "Kalanı sonraki aya devret",
    "Warn at (%)": "Uyarı eşiği (%)",

    # -- calendar -------------------------------------------------------------------
    "Mon": "Pzt",
    "Tue": "Sal",
    "Wed": "Çar",
    "Thu": "Per",
    "Fri": "Cum",
    "Sat": "Cmt",
    "Sun": "Paz",
    "The small number is how many transactions that day has.":
        "Küçük sayı, o gündeki işlem sayısıdır.",
    "No transactions on this day.": "Bu günde işlem yok.",

    # -- calculators -------------------------------------------------------------------
    "Loan": "Kredi",
    "Deposit interest": "Mevduat faizi",
    "Compound growth": "Bileşik getiri",
    "Time to a goal": "Hedefe kalan süre",
    "Calculator": "Hesap makinesi",
    "Monthly installment and total cost of a fixed-rate loan.":
        "Sabit faizli bir kredinin aylık taksiti ve toplam maliyeti.",
    "Loan amount (₺)": "Kredi tutarı (₺)",
    "Monthly interest (%)": "Aylık faiz (%)",
    "Include KKDF and BSMV (15 % each on the interest)":
        "KKDF ve BSMV dahil (faizin %15'i kadar her biri)",
    "Include bank fees and my own charges": "Banka masraflarını ve kendi masraflarımı dahil et",
    "Kind of loan": "Kredi türü",
    "Consumer (up to 36 months)": "İhtiyaç (en çok 36 ay)",
    "Vehicle (up to 48 months)": "Taşıt (en çok 48 ay)",
    "Housing (up to 120 months)": "Konut (en çok 120 ay)",
    "An allocation fee (0,5 % plus tax) and life insurance (about 0,8 %) are deducted up front. "
    "Add anything else the bank charges below.":
        "Tahsis ücreti (%0,5 ve vergisi) ile hayat sigortası (yaklaşık %0,8) peşin kesilir. "
        "Bankanın aldığı diğer masrafları aşağıya ekleyin.",
    "Charge": "Masraf",
    "Appraisal fee": "Ekspertiz ücreti",
    "Spread over months": "Aylara yayılsın",
    "Add charge": "Masraf ekle",
    "once, up front": "bir kez, peşin",
    "spread over {0} months": "{0} aya yayılmış",
    "Enter a name for the charge.": "Masraf için bir ad girin.",
    "Monthly installment": "Aylık taksit",
    "Total repaid": "Toplam geri ödeme",
    "Cost of borrowing": "Kredinin maliyeti",
    "Cost with all charges": "Tüm masraflarla maliyet",
    "Cash you receive": "Elinize geçen tutar",
    "Deducted up front": "Peşin kesilenler",
    "Allocation fee (with tax)": "Tahsis ücreti (vergi dahil)",
    "Life insurance (estimate)": "Hayat sigortası (tahmini)",
    "Add this loan to your debts as": "Bu krediyi borçlarınıza şu adla ekleyin",
    "Add to debts": "Borçlara ekle",
    "Save schedule as PDF": "Planı PDF olarak kaydet",
    "Save repayment schedule": "Ödeme planını kaydet",
    "Enter a name for the debt.": "Borç için bir ad girin.",
    "Added to your debts.": "Borçlarınıza eklendi.",
    "Saved {0}.": "{0} kaydedildi.",
    "Repayment schedule": "Ödeme planı",
    "Loan repayment schedule": "Kredi ödeme planı",
    "Loan amount": "Kredi tutarı",
    "Total deducted": "Toplam kesinti",
    "Month": "Ay",
    "Installment": "Taksit",
    "Extra charges": "Ek masraflar",
    "Total": "Toplam",
    "Principal": "Anapara",
    "Interest and tax": "Faiz ve vergi",
    "Remaining": "Kalan",
    "What a term deposit pays after the 5 % withholding tax.":
        "Vadeli mevduatın %5 stopaj sonrası getirisi.",
    "Deposit (₺)": "Mevduat (₺)",
    "Yearly interest (%)": "Yıllık faiz (%)",
    "Days": "Gün",
    "Interest after tax": "Vergi sonrası faiz",
    "At maturity": "Vade sonunda",
    "Withholding tax (5 %)": "Stopaj (%5)",
    "How a starting amount grows at a yearly return, with an optional monthly contribution.":
        "Bir başlangıç tutarının yıllık getiriyle, isteğe bağlı aylık katkıyla nasıl büyüdüğü.",
    "Starting amount (₺)": "Başlangıç tutarı (₺)",
    "Yearly return (%)": "Yıllık getiri (%)",
    "Years": "Yıl",
    "Monthly contribution (₺, optional)": "Aylık katkı (₺, isteğe bağlı)",
    "You put in": "Yatırdığınız",
    "Growth": "Getiri",
    "Final value": "Son değer",
    "How long regular saving takes to reach an amount. The result can become a savings goal.":
        "Düzenli birikimle bir tutara ne kadar sürede ulaşılır. Sonuç bir birikim hedefine dönüştürülebilir.",
    "Amount saved each time (₺)": "Her seferinde biriktirilen tutar (₺)",
    "Every month": "Her ay",
    "Every day": "Her gün",
    "Time needed": "Gereken süre",
    "Reached around": "Yaklaşık ulaşma tarihi",
    "Create a savings goal named": "Şu adla bir birikim hedefi oluştur",
    "Added to your savings goals.": "Birikim hedeflerinize eklendi.",
    "Type an expression and press Enter. You can use + − × ÷, brackets, ^ for powers, and sqrt( ).":
        "Bir ifade yazıp Enter'a basın. + − × ÷, parantez, üs için ^ ve sqrt( ) kullanabilirsiniz.",
    "Expression": "İfade",
    "This cannot be calculated. Check the expression.": "Bu hesaplanamıyor. İfadeyi kontrol edin.",

    # -- insights ------------------------------------------------------------------------
    "Financial health": "Finansal sağlık",
    "Not enough income and spending recorded yet to score your finances.":
        "Puan vermek için henüz yeterli gelir ve harcama kaydı yok.",
    "Based on the last {0} days.": "Son {0} güne göre.",
    "Savings rate": "Birikim oranı",
    "half of the score": "puanın yarısı",
    "Debt payments to income": "Borç ödemelerinin gelire oranı",
    "30 % of the score": "puanın %30'u",
    "Spending volatility": "Harcama dalgalanması",
    "20 % of the score": "puanın %20'si",
    "Month-end forecast": "Ay sonu tahmini",
    "A month-end forecast needs about three months of history; {0} days are recorded so far.":
        "Ay sonu tahmini için yaklaşık üç aylık geçmiş gerekir; şu ana kadar {0} gün kayıtlı.",
    "{0} days left in the month, at your average daily income and spending.":
        "Ayın bitmesine {0} gün var; ortalama günlük gelir ve harcamanıza göre.",
    "Unusual spending": "Olağandışı harcama",
    "Nothing stands out from your usual spending in the last 90 days.":
        "Son 90 günde olağan harcamanızdan sapan bir şey yok.",
    "Payments that look recurring": "Tekrarlıyor gibi görünen ödemeler",
    "No repeating payments were found that you are not already tracking.":
        "Henüz takip etmediğiniz tekrarlayan bir ödeme bulunamadı.",
    "Add an account first.": "Önce bir hesap ekleyin.",
    "This pattern is no longer detected.": "Bu düzen artık algılanmıyor.",

    # -- what if --------------------------------------------------------------------------
    "Compare where your balance is heading with a change you are considering. Nothing here is saved.":
        "Bakiyenizin gidişini düşündüğünüz bir değişiklikle karşılaştırın. Burada hiçbir şey kaydedilmez.",
    "Income change (%)": "Gelir değişimi (%)",
    "Spending change (%)": "Gider değişimi (%)",
    "One-time amount (₺, minus to spend)": "Tek seferlik tutar (₺, harcama için eksi)",
    "Over": "Süre",
    "As things are": "Mevcut gidiş",
    "With the change": "Değişiklikle",
    "Difference": "Fark",
    "The brighter line is the change; the fainter one is how things are now.":
        "Parlak çizgi değişikliği, soluk çizgi mevcut gidişi gösterir.",
    "With this change the balance drops below zero at some point in the period.":
        "Bu değişiklikle bakiye dönem içinde bir noktada sıfırın altına düşüyor.",
    "Based on your last 30 days: about {0} ₺ in and {1} ₺ out a month.":
        "Son 30 gününüze göre: ayda yaklaşık {0} ₺ giriş ve {1} ₺ çıkış.",
    "Enter a valid one-time amount, for example 5.000 or -2.500.":
        "Geçerli bir tek seferlik tutar girin; örneğin 5.000 veya -2.500.",

    # -- past balance -----------------------------------------------------------------------
    "What your accounts held at the end of a past day, and what has moved the balance since.":
        "Geçmiş bir günün sonunda hesaplarınızda ne vardı ve o günden beri bakiyeyi ne değiştirdi.",
    "In accounts on %1": "%1 tarihinde hesaplarda",
    "In savings goals": "Birikim hedeflerinde",
    "Nothing has moved the balance since that day.": "O günden beri bakiyeyi değiştiren bir şey olmadı.",
    "Choose today or an earlier date.": "Bugünü ya da daha önceki bir tarihi seçin.",
    "There are no records that far back. Balances are known from the day your first "
    "account was added.":
        "O kadar geriye ait kayıt yok. Bakiyeler ilk hesabınızın eklendiği günden itibaren bilinir.",
    "Transactions": "İşlemler",
    "Opening balances": "Açılış bakiyeleri",
    "Card payments": "Kart ödemeleri",
    "Debt payments": "Borç ödemeleri",
    "Moved into savings goals": "Birikim hedeflerine aktarılan",
    "Taken back from savings goals": "Birikim hedeflerinden geri alınan",
    "Savings goals opened": "Açılan birikim hedefleri",
    "Asset purchases": "Varlık alımları",
    "Asset sales": "Varlık satışları",

    # -- settings ---------------------------------------------------------------------------
    "Appearance": "Görünüm",
    "Applies immediately and is remembered on this device.":
        "Hemen uygulanır ve bu cihazda hatırlanır.",
    "Language": "Dil",
    "Animations": "Animasyonlar",
    "Turn off to make every change immediate.": "Kapatınca her değişiklik anında olur.",
    "Amounts and dates are written the same way in both.":
        "Tutarlar ve tarihler iki dilde de aynı biçimde yazılır.",
    "Security": "Güvenlik",
    "You will be asked to sign in again after changing it.":
        "Değiştirdikten sonra yeniden giriş yapmanız istenir.",
    "Change password": "Şifreyi değiştir",
    "Current password": "Mevcut şifre",
    "New password": "Yeni şifre",
    "Repeat new password": "Yeni şifreyi yineleyin",
    "Encryption key": "Şifreleme anahtarı",
    "Protected by %1.": "%1 ile korunuyor.",
    "Backup": "Yedek",
    "Create a backup": "Yedek oluştur",
    "One encrypted file with your records, the encryption key and your settings. "
    "It is protected by a separate backup password.":
        "Kayıtlarınızı, şifreleme anahtarını ve ayarlarınızı içeren tek bir şifreli dosya. "
        "Ayrı bir yedek şifresiyle korunur.",
    "Create backup": "Yedek oluştur",
    "Choose a password for this backup file. It is separate from your sign-in password "
    "and cannot be recovered.":
        "Bu yedek dosyası için bir şifre belirleyin. Giriş şifrenizden ayrıdır ve kurtarılamaz.",
    "Backup password (at least 12 characters)": "Yedek şifresi (en az 12 karakter)",
    "Repeat backup password": "Yedek şifresini yineleyin",
    "Choose where to save": "Kaydedilecek yeri seç",
    "Save backup": "Yedeği kaydet",
    "Helyosfer backup": "Helyosfer yedeği",
    "All files": "Tüm dosyalar",
    "The backup password must be at least 12 characters.": "Yedek şifresi en az 12 karakter olmalı.",
    "The two backup passwords do not match.": "İki yedek şifresi aynı değil.",
    "Backup saved to {0}. Keep its password safe: without it the backup cannot be opened.":
        "Yedek {0} dosyasına kaydedildi. Şifresini iyi saklayın: onsuz yedek açılamaz.",
    "Restore from a backup": "Yedekten geri yükle",
    "Replaces everything on this device with the backup's contents. A safety copy of the "
    "current state is kept next to your data.":
        "Bu cihazdaki her şeyi yedeğin içeriğiyle değiştirir. Mevcut durumun bir güvenlik "
        "kopyası verilerinizin yanında tutulur.",
    "Choose a backup to restore": "Geri yüklenecek yedeği seçin",
    "Restore this backup?": "Bu yedek geri yüklensin mi?",
    "Everything on this device is replaced, then Helyosfer closes so it can start from "
    "the restored data.":
        "Bu cihazdaki her şey değiştirilir; ardından Helyosfer, geri yüklenen veriyle "
        "başlayabilmek için kapanır.",
    "Backup password": "Yedek şifresi",
    "This backup could not be restored. Check the backup password and that the file is a "
    "Helyosfer backup.":
        "Bu yedek geri yüklenemedi. Yedek şifresini ve dosyanın bir Helyosfer yedeği olduğunu "
        "kontrol edin.",
    "Import and export": "İçe ve dışa aktarma",
    "Export to CSV": "CSV'ye aktar",
    "Transactions, assets, debts and recurring payments in one spreadsheet file. "
    "The file is not encrypted.":
        "İşlemler, varlıklar, borçlar ve tekrarlayan ödemeler tek bir tablo dosyasında. "
        "Dosya şifreli değildir.",
    "Exported {0} rows to {1}. The file is not encrypted; store it carefully.":
        "{0} satır {1} dosyasına aktarıldı. Dosya şifreli değil; dikkatle saklayın.",
    "Import transactions from CSV": "CSV'den işlem aktar",
    "Adds the transactions in a CSV file to one of your accounts. Rows that cannot be read "
    "are skipped.":
        "Bir CSV dosyasındaki işlemleri hesaplarınızdan birine ekler. Okunamayan satırlar atlanır.",
    "Choose a CSV file": "Bir CSV dosyası seçin",
    "Import transactions": "İşlemleri içe aktar",
    "Each row is added as a transaction with its original date and changes the account's balance.":
        "Her satır kendi tarihiyle bir işlem olarak eklenir ve hesabın bakiyesini değiştirir.",
    "Choose the account the transactions belong to.": "İşlemlerin ait olduğu hesabı seçin.",
    "Imported {0} transactions": "{0} işlem içe aktarıldı",
    "This file could not be read. Choose a CSV file exported from Helyosfer.":
        "Bu dosya okunamadı. Helyosfer'den dışa aktarılmış bir CSV dosyası seçin.",
    "The file could not be saved there. Choose another location.":
        "Dosya oraya kaydedilemedi. Başka bir konum seçin.",
    "Choose a file first.": "Önce bir dosya seçin.",
    "Categories": "Kategoriler",
    "Essential categories are counted as needs in summaries and the health score; "
    "the rest as extras.":
        "Temel kategoriler özetlerde ve sağlık puanında ihtiyaç sayılır; diğerleri ek harcama.",
    "Essential": "Temel",
    "New spending category": "Yeni gider kategorisi",
    "New income category": "Yeni gelir kategorisi",
    "Add category": "Kategori ekle",
    "Rename category": "Kategoriyi yeniden adlandır",
    "Remove %1?": "%1 kaldırılsın mı?",
    "Transactions, plan items and recurring payments are filed under it. Choose the category "
    "that takes them over.":
        "Altında işlemler, plan kalemleri ve tekrarlayan ödemeler var. Bunları devralacak "
        "kategoriyi seçin.",
    "Move its records to": "Kayıtların taşınacağı kategori",
    "Move and remove": "Taşı ve kaldır",
    "Choose the category that takes over its records.":
        "Kayıtları devralacak kategoriyi seçin.",
    "Everything filed under it moves to the new name.":
        "Altındaki her şey yeni ada taşınır.",
    "Danger zone": "Tehlikeli bölge",
    "Delete all data": "Tüm verileri sil",
    "Erases every account, transaction, debt and setting, and your password. "
    "This cannot be undone; create a backup first.":
        "Tüm hesapları, işlemleri, borçları, ayarları ve şifrenizi siler. "
        "Geri alınamaz; önce bir yedek oluşturun.",
    "Delete everything": "Her şeyi sil",
    "Delete all data?": "Tüm veriler silinsin mi?",
    "Every account, transaction, debt, recurring payment and your password are erased "
    "from this device. This cannot be undone.":
        "Tüm hesaplar, işlemler, borçlar, tekrarlayan ödemeler ve şifreniz bu cihazdan silinir. "
        "Bu işlem geri alınamaz.",
    "Type %1 to confirm": "Onaylamak için %1 yazın",
    "Type {0} to confirm.": "Onaylamak için {0} yazın.",
    "DELETE": "SİL",
    "About": "Hakkında",
    "Questions, feedback and bug reports: %1": "Sorular, geri bildirim ve hata bildirimleri: %1",
    "Where your data is kept": "Verilerinizin tutulduğu yer",
}
