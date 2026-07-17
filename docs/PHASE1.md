# PHASE1.md — Satranç Hakem Agent, Faz 1 Bulguları

## Durum

Faz 1 mekanik olarak tamamlandı: model → tool-call → gerçek `python-chess` çalıştırma → sonucu modele geri verme → nihai cevap round-trip'i çalışır durumda, kendi fine-tune'lanmış `qwen-satrancprosu` modeli üzerinde (LM Studio, `localhost:1234`, OpenAI-uyumlu `/v1/chat/completions`).

Proje kararı: Claude API değil, **kendi fine-tune Qwen'i üzerine** kuruluyor (Berk'in tercihi — projenin amacı zaten fine-tune'lanmış LLM'in üstüne agent inşa etmek).

## Kurulum notları (tekrar keşfetmeye gerek yok)

- Ortam: PyCharm + venv, proje klasörü `satranc-hakem-agent`. Python 3.11.7 zaten kuruluydu.
- Terminal ≠ Python Console ayrımı netleşti — `pip install` gibi shell komutları Terminal'de, Python kodu Console/dosyada çalışır.
- `chess` kütüphanesi (`pip install chess`, v1.11.2) kuruldu, hem local hem referans ortamda.
- LM Studio'da yüklü modeller: `qwen-satrancprosu` (asıl fine-tune), `finetune_deneme` (eski deneme, henüz incelenmedi), `google/gemma-4-e4b`, embedding modeli.
- **Kural:** Modele gönderilen test query'leri her zaman İngilizce yazılacak (Türkçe sentez zayıf, CLAUDE.md bulgu #3/#5 ile tutarlı).

## `python-chess` temelleri (doğrulandı)

- `chess.Board()` → standart başlangıç, `board.legal_moves` generator (list() ile listeye çevrilir), başlangıçta 20 legal hamle.
- `board.push_uci("e2e4")` ile hamle oynatma çalışıyor.
- Terfi (promotion) doğru işleniyor: `a7a8q` gibi harf eklenmesi gerekiyor, eksik olursa (`a7a8`) `IllegalMoveError` fırlatıyor — hata mesajı hamle + FEN içeriyor, ileride model'e geri beslenebilir.

## Kritik bulgular — model davranışı

### 1. Tool-calling temel yeteneği fine-tune'dan sağ çıkmış
`qwen-satrancprosu`, doğal dil isteğini doğru şekilde tool-call'a çeviriyor (`finish_reason: tool_calls`, doğru fonksiyon adı, doğru JSON formatı). LoRA'nın "cerrahi" doğası (CLAUDE.md bulgu #6) burada da doğrulandı — chess-data fine-tune'u temel tool-calling yeteneğini bozmamış.

### 2. Belirsiz doğal dil hamlesi → model sessizce "düzeltiyor"
"Move knight from b1 to b3" (fiziksel olarak imkansız, at böyle gidemez) dendiğinde, model bunu açıkça geçersiz saymadı; sessizce `b2b3`'e (geçerli bir piyon hamlesi) çevirdi. Yani kullanıcının sorduğu soruyu **fark ettirmeden değiştirdi.**

**Karşı test:** Aynı hamle UCI notasyonuyla + "do not interpret, pass exactly as given" talimatıyla verildiğinde, model `b1b3`'ü değiştirmeden geçirdi.

**Ders:** Sorun modelin "aptallığı" değil, prompt'un belirsizliğiydi. Ama pratik sonuç aynı: **hamle bilgisi sisteme her zaman UCI formatında, tek anlamlı gelmeli** — modelin doğal dilden UCI'ye çeviri yapmasına asla izin verilmeyecek.

### 3. Model, FEN pozisyonunu hayal ediyor — açık talimata rağmen (en kritik bulgu)
İki ayrı testte doğrulandı:
- Test A: "standard starting position" dendiğinde, model kendi başına farklı bir FEN (1.e4 e5 2.Nf3 sonrası) uydurdu.
- Test B (daha ciddi): Sistem mesajında **birebir FEN verilip, "always use this exact FEN, never generate or guess" diye açıkça yazılmasına rağmen**, model yine farklı bir FEN uydurdu (hatta biraz bozuk bir en-passant alanıyla).

Test B, Test A'dan daha ağır bir bulgu çünkü model sadece "bilmediği bir şeyi tahmin etmiyor", **açıkça verilen bağlamı görmezden gelip yine de hayal ediyor.** Bu, CLAUDE.md bulgu #7'nin (uzamsal muhakemede genel zayıflık) tool-call parametre doldurma bağlamındaki somut kanıtı.

**Açık soru (araştırılmadı, ileride bakılabilir):** Bu davranış fine-tune'dan mı geliyor (chess_data formatı sistem mesajı kullanmıyor olabilir) yoksa base Qwen 2.5 7B'nin zaten sahip olduğu bir zayıflık mı? Ayırt etmenin yolu: aynı testi fine-tune'suz base model ile tekrarlamak.

## Mimari karar (Faz 1 sonucu, kalıcı kural)

**Model asla FEN üretmeyecek/görmeyecek sorumluluğunda olmayacak.** Tool şemasından `fen` parametresi kaldırılacak. Gerçek pozisyon durumu sunucu tarafında (`board` nesnesi, `board.fen()`) tutulacak ve tool çağrısına biz enjekte edeceğiz. Model sadece `move` (UCI) parametresini üretecek — bu, hem daha güvenli hem de modelin en zayıf olduğu göreve (uzamsal/durum hafızası) hiç ihtiyaç bırakmıyor.

## Sıradaki adım (Faz 1'in kapanışı için)

- Tool şemasından `fen`'i çıkarıp sadece `move` isteyen versiyonu test etmek (planlandı, henüz çalıştırılmadı).
- Ardından Faz 2'ye geçiş: agent loop — model, geçersiz hamle sonucunu görüp tekrar karar verme (düzeltme önerisi ya da Stockfish'e yönlendirme).
