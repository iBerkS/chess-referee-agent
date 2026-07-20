# PHASE2.md — Satranç Hakem Agent, Faz 2 Bulguları

## Durum

Faz 2'nin mekanik altyapısı kuruldu: `make_move` tool'u eklendi (`_check_legality`
helper'ı üzerinden, `check_move_legality` ile ortak kod), sabit iki-çağrılık
akış gerçek bir `for`/`MAX_TURNS=10` döngüsüne çevrildi, ve bir turda birden
fazla `tool_calls` gelme ihtimaline karşı (paralel tool call) tüm liste
işlenecek şekilde düzeltildi (ilk versiyon sadece `tool_calls[0]`'ı işliyordu,
bu ikinci bir tool_call'ı sessizce yok sayıp konuşma geçmişini bozuyordu).

## Kritik bulgu — "kör retry" gerçek bir düzeltme yeteneği değil

**Senaryo:** Modele bilerek imkansız bir hamle verildi (`b1b3`, at için
geometrik olarak imkansız) + "illegal ise legal bir at hamlesi bulup oyna"
talimatı.

**Gözlemlenen akış:**
1. `check_move_legality("b1b3")` → `{"legal": false}` (doğru)
2. `make_move("c6e5")` → `{"success": false, "reason": "illegal move"}` —
   ama bu hamle sadece illegal değil, **anlamsız**: c6 karesinde başlangıç
   pozisyonunda hiçbir taş yok. Model önceki turun sonucundan ("b1'deki at
   gidemiyor") gerçek bir çıkarım yapmadı, tamamen farklı ve tutarsız bir
   tahmin daha üretti.
3. Model üçüncü bir tool call denemek yerine pes edip düz metinle
   "bulamadım, onun yerine e2e4 oynayalım" dedi — ama bunu tool call'a hiç
   çevirmeden, sadece niyet olarak beyan etti.

**Sonuç:** Döngü mekanizması (retry etme imkanı) teknik olarak sorunsuz
çalışıyor — model istediği kadar tekrar deneyebiliyor. Ama modele "illegal,
tekrar dene" dışında hiçbir ek bilgi vermediğimiz için ikinci tahmin, birinciden
daha isabetli değil; rastgele üretimden ayırt edilemiyor. Bu, PHASE1.md
bulgu #3'ün (model FEN'i açık talimata rağmen hayal ediyor) aynı kökten farklı
bir belirtisi: model, tahtanın gerçek durumunu (bu sefer FEN'den değil, tool
sonucundan) satır satır çıkarım yaparak kullanamıyor.

**Önemli ayrım:** Bu, "agent loop çalışmıyor" demek değil — loop'un kendisi
(çoklu tur, tool sonucu bazlı devam/durma) tam istenen şekilde işliyor. Sorun
loop'un *içeriğinde*: model, verilen tool sonucundan yararlı bir sonraki-adım
çıkaramıyor.

## Mimari karar (Faz 1'deki FEN kararıyla tutarlı)

Faz 1'de "model FEN üretmeyecek/görmeyecek, biz enjekte edeceğiz" kararı
alınmıştı çünkü model bu görevde güvenilmezdi. Aynı mantık burada da geçerli:
**model, hangi hamlelerin legal olduğunu sıfırdan üretmeye çalışmayacak.**
`python-chess` zaten bu bilgiye sahip — motor neyi biliyorsa, modelin onu
tahmin etmesine izin vermiyoruz.

Karar: `_execute_tool_call`, bir hamle illegal çıktığında sonuca ilgili taş
için gerçekten oynanabilir hamlelerin listesini de ekleyecek (örn.
`{"legal": false, "legal_moves_for_piece": ["b1a3", "b1c3"]}`). Bu, modelin
"üretme" değil "seçme" görevi yapmasını sağlıyor — daha önce doğrulanmamış bir
hipotez: seçme, üretmeden daha güvenilir olmalı, bir sonraki testte bunu
ölçeceğiz.

## `legal_moves_for_piece` ipucu — sonuç doğrulandı

`_execute_tool_call`, illegal çıkan hamlenin kalkış karesine göre filtrelenmiş
gerçek legal hamle listesini (`m.from_square == move.from_square`) sonuca
eklendi. Aynı b1b3 senaryosu tekrar çalıştırıldı:

1. `check_move_legality("b1b3")` → `{"legal": false, "legal_moves_for_piece":
   ["b1c3", "b1a3"]}`
2. Model listeden doğrudan seçim yaptı (`make_move("b1c3")`), yeni bir tahmin
   **üretmedi** — önceki testteki anlamsız `c6e5` tahmini bir daha çıkmadı.
   `make_move` `success: true` döndü.
3. Modelin son cümlesi ("atı b1'den c3'e taşıdım") ile gerçek board durumu
   birebir örtüştü — önceki testte modelin gerçekleşmemiş bir hamleyi
   ("g8f7'ye taşıdım") başarılı gibi rapor ettiği yalan burada tekrarlanmadı.

**Hipotez doğrulandı: seçme, üretmeden daha güvenilir.** Model'e doğru
seçenekleri sunduğumuzda hem doğru seçim yapıyor hem de bulduktan sonraki
iddiası gerçekle tutarlı kalıyor — ikinci kazanç (iddia-gerçek tutarlılığı)
öngörülenden fazla, sadece doğru hamle bulma değil, raporlama güvenilirliği
de düzeldi.

**Açık soru (çözüldü):** İpucu hem `check_move_legality` hem `make_move`
sonucuna eklendi (ortak kod yolu üzerinden) — ayrım yapmaya gerek kalmadı.

## Sıradaki adım

- Faz 2'nin çekirdek döngüsü (retry + ipucu) işlevsel olarak tamamlandı,
  **Faz 2 burada kapanıyor.**
- Kapsam kararı: CLAUDE.md'nin orijinal Faz 2 tanımındaki Stockfish
  yönlendirmesi bu fazdan çıkarıldı, Faz 3'e taşındı. Faz 3'ün kendisi de
  ikiye bölündü, çünkü "çoklu araç" ve "konuşma hafızası" birbirinden
  bağımsız iki mimari değişiklik — aynı anda yapılırsa hata ayıklama
  karışır (Faz 2'de debug print eksikliğinden yanlış yorumlama örneği
  yaşandı, aynı riskin tekrarı istenmiyor):
  - **Faz 3a — Stockfish:** üçüncü tool, mevcut helper+dispatch pattern'ine
    (`_check_legality` / `_execute_tool_call`) oturtularak eklenecek. Legal
    hamlede pozisyon değerlendirmesine yönlendirme burada tamamlanacak.
  - **Faz 3b — Konuşma hafızası:** `ask()` şu an her çağrıldığında
    `messages`'ı sıfırdan kuruyor, board state (`self.board`) kalıcı ama
    konuşma geçmişi değil. Bu, yeni bir state-yönetim tasarımı gerektiriyor,
    Stockfish pattern'inden bağımsız — Faz 3a'dan sonra ele alınacak.