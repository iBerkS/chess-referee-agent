# PHASE3.md — Satranç Hakem Agent, Faz 3a Bulguları (Stockfish Entegrasyonu)

## Kapsam kararı

CLAUDE.md'nin orijinal Faz 2 tanımı Stockfish yönlendirmesini de içeriyordu.
Bu, Faz 2'den çıkarılıp Faz 3'e taşındı (bkz. PHASE2.md), ve Faz 3'ün kendisi
ikiye bölündü — "çoklu araç" (Stockfish) ve "konuşma hafızası" birbirinden
bağımsız mimari değişiklikler, aynı anda yapılırsa hata ayıklama karışır:

- **Faz 3a — Stockfish entegrasyonu** (bu doküman)
- **Faz 3b — Konuşma hafızası** (henüz başlanmadı)

## Kurulum kararı: harici binary, ama PATH'e dokunmadan

Stockfish, pip ile birlikte gelen bir bağımlılık değil — `stockfish` ve
`pystockfish` PyPI paketlerinin ikisi de sadece UCI protokolü wrapper'ı,
binary'yi ayrıca sağlaman gerekiyor. Sistem PATH'ine dokunmaktan kaçınmak
için: binary [stockfishchess.org](https://stockfishchess.org/download/)'dan
indirilip proje altına (`bin/stockfish.exe`) yerleştirildi,
`chess.engine.SimpleEngine.popen_uci()`'ye **tam dosya yolu** verildi — bu,
hiçbir global sistem ayarı değiştirmeden çalışıyor. README'ye bu bağımlılık
açıkça not düşüldü (harici, pip dışı, zorunlu).

## Motor yaşam döngüsü kararı

Motor, `ChessAgent.__init__`'te bir kere açılıp nesne ömrü boyunca açık
tutuluyor (`self.engine`), her `evaluate_position` çağrısında yeniden
başlatılmıyor — motor stateless bir hesap makinesi gibi çalışıyor, board
zaten her seferinde biz veriyoruz. Temizlik için basit bir `close()` metodu
eklendi (`self.engine.quit()`), `__main__` sonunda elle çağrılıyor.
Context manager (`__enter__`/`__exit__`) şimdilik gereksiz karmaşıklık
olarak değerlendirildi, ihtiyaç çıkarsa sonra eklenir.

**Doğrulanan sızıntı riski:** Test sırasında Task Manager'da asılı kalan bir
`stockfish.exe` süreci görüldü — kaynağı `agent.py`'ın kendi `close()`'u
değil, PyCharm Python Console'da açık kalan ayrı bir `engine` session'ıydı.
`close()`'un kendisi doğrulandı: script tek başına çalıştırıldığında süreç
düzgün kapanıyor.

## `PovScore` normalizasyonu — iki tuzak, ikisi de test edilerek çözüldü

1. **Perspektif:** `.relative` sıraya göre işaret değiştiriyor (aynı
   pozisyon bir turda + bir turda - görünebilir), `.white()` sabit bir
   referans çerçevesi veriyor. `.white()` seçildi — modele tutarlı bir
   sinyal vermek için.
2. **Mat skorları:** `.mate()` metodu, kütüphanenin kendi dokümantasyonunun
   uyardığı bir davranışa sahip — "Mate(0) (kaybettik)" ile "MateGiven
   (kazandık)" durumlarını aynı `0` değerine düşürüyor, yön bilgisi
   kayboluyor. `.score(mate_score=100000)` kullanıldı, bu yöntem işareti
   koruyor (test edildi: `Mate(-0).score(mate_score=100000)` → `-100000`,
   doğru yön korunuyor).

## `evaluate_position` tool tasarımı

Argümansız bir tool — pozisyon zaten `self.board`'da, modelin hiçbir şey
belirtmesine gerek yok (Faz 1'deki "model FEN vermeyecek" kararıyla aynı
mantık). Sonuç üç alana indirgeniyor: `score_cp` (centipawn, mat
durumlarında da `mate_score` ile aynı alanda taşınıyor — modele iki farklı
format öğretmemek için), `is_mate` (bool), `best_move` (motorun `pv`
listesindeki ilk hamle, UCI string).

**Doğrulandı:** "e2e4 oyna, sonra kim daha iyi" senaryosunda model
`make_move` + `evaluate_position`'ı aynı turda paralel çağırdı, skoru
doğru yorumladı ("White is better by 35 centipawns"), `best_move`'u doğru
tarafa (siyaha) atfetti. Board durumuyla iddia birebir örtüştü.

## Bug: `reason` alanı başta yanlış uygulanmıştı

İlk `_execute_tool_call` implementasyonunda `"reason": "reason"` yazılmıştı
(değişken yerine düz metin sabit) — model illegal hamlelerde gerçek sebep
yerine kelimenin tam anlamıyla "reason" string'ini görüyordu. Bu, aşağıdaki
"sıra sende değil" bulgusunun kök nedeniydi. Düzeltildi, doğrulandı.

## Kritik bulgu: boş `legal_moves_for_piece`, "sıra sende değil" ile karışıyordu

**Senaryo:** İki tool aynı turda paralel çağrıldığında (örn.
`check_move_legality("b1b3")` + `make_move("d2d4")`), ikinci hamle
(alakasız ama legal) gerçekten oynanıyor ve sırayı değiştiriyordu. Sonraki
turda model hâlâ ilk (artık sırası geçmiş) taş için hamle önermeye
çalışınca, `legal_moves_for_piece` boş dönüyordu — ama bunun sebebi "o taş
için hiç legal hamle yok" değil, "sıra o oyuncuda değil" idi. Model bu
ayrımı hiç göremediği için (`reason` bug'ı yüzünden) kendi kafasından
hayali kurallar icat etti (örn. "piyonlar sadece ikinci sırada
oynayabilir" gibi var olmayan bir kural).

**Kök neden + düzeltme:** `_check_legality`, artık üç durumu ayırt ediyor
(`piece is None` → "kare boş", `piece.color != board.turn` → "sıra o
oyuncuda değil", aksi halde → "gerçekten illegal") ve bunu `reason` alanıyla
açıkça bildiriyor. `legal_moves_for_piece` ipucu artık sadece üçüncü
durumda (gerçekten "doğru taş, yanlış hedef") hesaplanıyor — "sıra sende
değil" durumunda ipucu hiç eklenmiyor, yanıltıcı boş liste yerine net bir
`reason` metni veriliyor.

**Doğrulanan etki:** Düzeltme sonrası 3 tekrar testte, önceki turlarda
görülen hayali kural icadı (uydurma satranç kuralları) bir daha
görülmedi — `reason` netliği, modelin belirsizlik karşısında hayal kurma
eğilimini büyük ölçüde bastırdı.

## Bilinen sınırlar — çözülmedi, düşük öncelikli olarak bırakılıyor

Reason netliği düzeltmesinden sonra bile, aşağıdaki iki davranış düşük
oranda (~1/3 test koşusunda) devam ediyor:

1. **"Niyet beyanı, icra yok":** Model bazen "b1'den c3'e taşıyacağım" gibi
   bir cümle kurup ilgili `make_move`'u hiç çağırmıyor, döngü `content`
   dolu olduğu için "final cevap" sanılıp bitiyor. Sistem mesajına açık
   talimat eklendi ("must call the tool, don't just describe it"), oranı
   azalttı ama tamamen ortadan kaldırmadı.
2. **Hamleyi yanlış tanımlama:** Model doğru UCI kodunu üretse bile,
   açıklama cümlesinde yanlış taş/kare adı kullanabiliyor (örn. `b8c6`—bir
   at hamlesi—"fil, c4'e" diye tanımlanması).

**Değerlendirme:** Bu ikisi, "kör retry" ve "reason netliği" gibi tek bir
mimari değişiklikle kapanan sorunlardan farklı — muhtemelen 7B parametreli
modelin kendi muhakeme kapasitesinin doğal bir sınırı (donanım/model
boyutu kısıtı), PHASE1.md bulgu #7'nin ("LLM'ler somut/uzamsal
muhakemede genel bir zayıflık taşıyor") bir başka yüzü. Daha fazla prompt
mühendisliğiyle kovalanmayacak, Faz 3a burada fonksiyonel olarak
kapatılıyor. İleride ayrı bir guardrail katmanı (örn. modelin content'inde
"I will/I'll" gibi niyet ifadeleri var ama tool_calls boşsa, otomatik bir
ek tur zorlamak) düşünülebilir, ama şimdilik kapsam dışı.

## Sıradaki adım

Faz 3a kapandı. Sırada Faz 3b — konuşma hafızası: `ask()` şu an her
çağrıldığında `messages`'ı sıfırdan kuruyor, board state (`self.board`)
kalıcı ama konuşma geçmişi değil.