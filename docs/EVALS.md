# EVALS.md — Satranç Hakem Agent, Eval Sistemi (v1)

## Amaç ve kapsam

Oğuz'un (mentör) Slack'te önerdiği yeni görev kapsamında: agent'ın
davranışını tek seferlik elle test etmek yerine, tekrarlanabilir ve
istatistiksel olarak ölçülebilir bir eval sistemi kuruldu.

**Unit test ile eval arasındaki ayrım** (Oğuz'un çerçevesi): unit testler
kodun doğruluğunu deterministik olarak (geç/kal) ölçer; evaller ise LLM'in
bir görevde ne sıklıkla doğru davrandığını, çok sayıda tekrar üzerinden
istatistiksel olarak ölçer. Bu proje her ikisini de kullanıyor -
`_check_legality` gibi deterministik kod parçaları için klasik unit test
uygundur, ama "model doğru tool'u çağırıyor mu" gibi sorular için eval
gerekir. Bu doküman sadece eval tarafını kapsıyor.

## Mimari

```
tests/evals/
├── checks.py       # isimli kontrol fonksiyonları
├── scenarios.py     # senaryo verisi (prompt + hangi kontroller uygulanacak)
└── run_evals.py     # runner - her senaryoyu N kere çalıştırıp istatistik üretir
```

**Senaryo formatı:** her senaryo bir `user_prompt` (tekil) ya da
`user_prompts` (liste - ardışık `ask()` çağrıları, konuşma hafızası gibi
çok-turlu davranışları test etmek için) ve bir `check_fns` sözlüğü taşır.
`check_fns` sözlük olduğu için, aynı gerçek konuşma (`ask()` çağrısı) birden
fazla açıdan (örn. hem "doğru tool çağrıldı mı" hem "iddia gerçekle
tutarlı mı") değerlendirilebiliyor - tek bir olayı birden fazla kez
çalıştırıp karşılaştırmaya çalışmak yerine.

**Kontrol fonksiyonu sözleşmesi:** her fonksiyon `(status, detail)` döner.
`status` üç değerden biri:
- `PASSED` - test edildi, model doğru davrandı
- `FAILED` - test edildi, model yanlış davrandı
- `INVALID` - senaryo, test etmesi gereken davranışı hiç tetiklemedi (bu,
  "model başarısız oldu" demek değildir)

Bu üçlü ayrım, ilk versiyonda (`passed: bool`) yoktu - bir senaryo hiç
illegal hamle tetiklemediğinde bu yanlışlıkla "KALDI" sayılıyordu. Ayrım
eklendikten sonra, "gerçek başarısızlık" ile "test edilemedi" birbirinden
netleşti.

## Tekrar sayısı ve istatistik (kritik karar)

İlk versiyonlarda her senaryo **1 kere** çalıştırılıp kesin bir
PASSED/FAILED/INVALID veriliyordu. Bu yanıltıcı çıktı: aynı senaryo, aynı
prompt, ardışık koşumlarda tamamen farklı sonuçlar üretti (bazen ipucu
listesinden doğru seçim, bazen tamamen alakasız bir kare, bazen niyet
beyanı ama icra yok). Model temperature sampling ile çalışan 7B parametreli
bir LLM olduğu için, bu beklenen bir davranış - tek koşum istatistiksel
olarak anlamsız.

**Çözüm:** `run_evals.py`, her senaryoyu `REPEAT_COUNT` (varsayılan 5) kere
çalıştırıp her `(scenario_id, check_name)` çifti için oranlı bir sonuç
üretiyor: `X/N GEÇTİ, Y/N KALDI, Z/N GEÇERSİZ`. PASSED oranı, INVALID
koşumlar paydan çıkarılarak hesaplanıyor (`passed / (n - invalid)`) - çünkü
INVALID "test edilemedi" demek, "başarısız" demek değil; hepsini paydaya
dahil etmek oranı yapay olarak düşürürdü.

## v1 sonuçları (N=5, 3 senaryo, 14 kontrol kombinasyonu)

| Kontrol | Senaryo | Oran | Not |
|---|---|---|---|
| used_legal_hint | knight (b1b3) | 3/5 (%60) | |
| used_legal_hint | bishop (c1a3) | 1/5 (%20) | En zayıf, çeviri hatasıyla birleşiyor |
| intent_action_consistency | knight | 0/1 (%0) | Az veri ama düşük |
| intent_action_consistency | bishop | 1/3 (%33) | |
| no_invented_rules | knight, bishop | 5/5 (%100) | |
| move_description_accuracy | knight | N/A | Hiç tetiklenmedi |
| move_description_accuracy | bishop | 0/1 (%0) | İlk gerçek sinyal: knight hamlesi "bishop" diye tanımlandı |
| turn_efficiency | knight, bishop | 5/5 (%100) | |
| input_square_translation | bishop | 5/5 (%100) | |
| no_irrelevant_moves | bishop | 1/3 (%33) | |
| no_false_claims | bishop | N/A | Hiç tetiklenmedi |
| recalls_first_move | memory | 3/5 (%60) | |

**Genel dağılım:** 14 kombinasyondan 5'i %80+ (güvenilir), 2'si %50-80
(orta), 5'i %50 altı (zayıf), 2'si N/A (senaryo bu sinyali hiç
tetiklemedi).

## En zayıf üç nokta (v1 itibarıyla)

1. **`intent_action_consistency` (%0-33)** - PHASE3.md'de "bilinen sınır"
   olarak kapsam dışı bıraktığımız niyet-icra kopukluğu, artık kesin bir
   sayıyla doğrulandı.
2. **`move_description_accuracy` (%0, ilk gerçek örnek)** - model başarıyla
   oynanan bir at hamlesini "bishop" diye tanımladı. Önceki turlarda
   tekrar tekrar gözlemlediğimiz "hamleyi yanlış tanımlama" davranışının
   ilk sayısal kanıtı.
3. **`used_legal_hint` (bishop, %20)** - Faz 2'nin çekirdek bulgusu (kör
   retry, ipucu ile düzeltildi) bishop senaryosunda hâlâ düşük - muhtemelen
   kare-çevirisi zayıflığıyla (c1 → b1 kayması, ayrı bir bulgu) birleşip
   compound bir zayıflık oluşturuyor.

## Bilinen sınırlar (eval sisteminin kendisi)

- `intent_phrases` ve uydurma-kural kalıpları gibi bazı kontroller kaba
  keyword-heuristic kullanıyor - yanlış pozitif/negatif riski var (örn.
  "I will not..." gibi olumsuz cümleler de "i will" içerir).
  `_extract_tool_calls`'daki pozisyonel `zip` eşleştirmesi kırılgan,
  yeni tool'lar eklenince gözden geçirilmeli.
- N=5 hâlâ küçük bir örneklem - gerçek oranlar muhtemelen daha fazla
  tekrarla (N=20-50) stabilize olur, ama LM Studio üzerinden yerel
  çıkarımın süresi göz önüne alınarak şimdilik 5 ile sınırlı tutuldu.
- `move_description_accuracy` ve `no_false_claims` gibi bazı kontroller
  mevcut senaryolarda nadiren tetikleniyor (yüksek INVALID oranı) -
  bu sinyalleri daha güvenilir tetikleyecek yeni senaryolar eklemek
  gelecekteki bir iyileştirme.

## Sıradaki adım

Eval seti v1 olarak burada bırakılıyor. Olası genişletmeler: REPEAT_COUNT'u
artırmak, yeni senaryolar eklemek (özellikle move_description_accuracy ve
no_false_claims için), ya da tespit edilen zayıf noktalardan birini (örn.
niyet-icra kopukluğu için bir guardrail mekanizması) mitigasyon hedefi
olarak ele almak.
