# PHASE3B.md — Satranç Hakem Agent, Faz 3b Bulguları (Konuşma Hafızası)

## Sorun

`ask()`, her çağrıldığında `messages`'ı sıfırdan kuruyordu — board state
(`self.board`) kalıcıydı ama konuşma geçmişi değildi. İki ayrı `ask()`
çağrısı arasında model önceki adımı hiç bilmiyordu (örn. "hangi hamleyi
oynadık" gibi bir soruya, board FEN'i bu bilgiyi taşımadığı için cevap
veremiyordu).

## Tasarım kararı: system message hiç saklanmıyor, her çağrıda taze üretiliyor

`self.messages` listesi `__init__`'te başlatılıp nesne ömrü boyunca
yaşıyor (board state ile aynı mantık), ama içinde **sadece** `user`,
`assistant`, `tool` rolündeki turlar birikiyor. `system` mesajı bu listeye
hiç girmiyor — her `ask()` turunda `[self._system_message()] + self.messages`
şeklinde, güncel FEN'i içeren taze bir system message ile birleştirilip
modele öyle gönderiliyor.

**Gerekçe:** Board her hamlede değiştiği için system message'ın FEN
bilgisi de değişmesi gerekiyor. Sabit bir kopyayı saklayıp güncellemek
yerine, hiç saklamamak ve her çağrıda taze üretmek, "unutup güncellemeyi
atlama" riskini mimari olarak ortadan kaldırıyor.

## Doğrulama testi — birikimli hafıza gerçekten çalışıyor

5 ardışık `ask()` çağrısı test edildi:
1. "Play e2e4." → `make_move` çağrıldı, oynandı
2. "Now play e7e5 for black." → `make_move` çağrıldı, oynandı
3. "Which move did we just play?" → **tool çağırmadan**, doğrudan "e7e5
   for black" cevabı — bir önceki turu doğru hatırladı
4. "What was the very first move of this game?" → **iki tur öncesine**
   kadar geri giderek "e2e4, played by white" cevabı — en zorlayıcı test,
   çünkü bu bilgi board'un güncel FEN'inden çıkarılamaz (FEN sadece "şu an
   ne var" der, "kim, ne zaman oynadı" demez), sadece konuşma geçmişinden
   gelebilirdi
5. "Who's better right now, and by how much?" → `evaluate_position`
   doğru çağrıldı, sonuç doğru yorumlandı, uzun geçmiş (5. çağrı) bu
   tool'un çalışmasını bozmadı

**Sonuç:** Hafıza mekanizması hem kısa vadeli (bir önceki tur) hem de
birikimli (oyunun başına kadar) sorulara doğru cevap verebiliyor,
board state'ten değil gerçekten konuşma geçmişinden okuyarak.

## Payload büyüme ölçümü

Her turda yaklaşık karakter/token sayısı ölçüldü (`len(json.dumps(m))`
toplamı, kaba `~4 karakter = 1 token` tahminiyle):

| Çağrı | Tur | Payload (karakter) | ~token |
|---|---|---|---|
| 1 | 1 | 395 | 98 |
| 1 | 2 | 788 | 197 |
| 2 | 1 | 1036 | 259 |
| 2 | 2 | 1431 | 357 |
| 3 | 1 | 1695 | 423 |
| 4 | 1 | 1877 | 469 |
| 5 | 1 | 2086 | 521 |
| 5 | 2 | 2435 | 608 |

Tool-call içeren turlar (~150-160 token/tur) saf metin turlarından
(~50 token/tur) daha ağır — beklenen, çünkü tool şeması + JSON sonuçları
düz metinden daha hacimli.

**Context penceresi:** LM Studio'da model 8192 token context ile
çalışıyor. 5 çağrı/8 tur sonunda 608 token'a ulaşıldı (~%7.4 kullanım).
Ölçülen büyüme oranıyla ekstrapolasyon: limite ulaşmak için yaklaşık
75-80 çağrılık ek bir tampon var — hobi projesi ölçeğinde gerçekçi tek
oturumluk kullanımın oldukça üzerinde.

**Karar:** Şimdilik mesaj budama/özetleme eklenmiyor — henüz karşılaşılmamış
bir sorunu erken çözmek yerine (CLAUDE.md prensibi), ölçülmüş veriyle
"yeterli marj var" sonucuna varıldı. İleride gerçekten çok uzun bir analiz
oturumu (onlarca hamle + sürekli soru-cevap) senaryosu ortaya çıkarsa,
o zaman ele alınacak bilinen bir gelecek iş olarak not düşülüyor.

## Bug (kod kalitesi, davranış değil): debug print'i yanlış döngüde

İlk implementasyonda payload boyutu debug satırı, asıl işlevsel
`for tur in range(MAX_TURNS):` döngüsünden **ayrı**, hiçbir state
değiştirmeyen boş bir ikinci döngüde duruyordu — bu yüzden her `ask()`
çağrısında aynı sayı 10 kere gereksiz basılıyordu. Fonksiyonel bir hataya
yol açmadı (ölçümler zaten doğruydu, sadece log kirliydi), debug satırı
asıl döngünün içine taşınarak düzeltildi.

## Sıradaki adım

CLAUDE.md'nin orijinal 3 fazlık planı burada tamamlanıyor (Faz 1, Faz 2,
Faz 3a, Faz 3b — hepsi doğrulandı). Proje bir sonraki aşamaya karar
vermeyi gerektiriyor; olası yönler ayrı bir tartışma konusu.