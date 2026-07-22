"""
Her kontrol fonksiyonu, bir ChessAgent'ın ask() çağrısı bittikten sonra
çağrılır. agent.messages (kalıcı konuşma geçmişi) üzerinden, modelin
gerçekte hangi tool'ları hangi argümanlarla çağırdığını inceleyebiliriz -
sadece final_answer'a (son cümleye) bakmak yeterli değil, çünkü asıl
davranış tool-call'larda gizli.

Her fonksiyon (status: str, detail: str) döner. status üç değerden
biridir:
  - "PASSED"  -> senaryo test edildi ve model doğru davrandı
  - "FAILED"  -> senaryo test edildi ve model yanlış davrandı
  - "INVALID" -> senaryo, test etmesi gereken davranışı hiç tetiklemedi
                 (bu, "model başarısız oldu" demek değildir - senaryo
                 tasarımı gözden geçirilmeli)
detail, rapor çıktısında "neden bu sonuç" diye insan-okur bir açıklama
taşır.
"""
import json
import chess

PIECE_NAME_MAP = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}


def _extract_tool_calls_from(messages):
    """
    Verilen mesaj listesindeki assistant mesajlarından tüm tool_call'ları
    (isim + argümanlar) düz bir listeye çıkarır.
    """
    calls = []
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                calls.append({
                    "name": tc["function"]["name"],
                    "args": json.loads(tc["function"]["arguments"])
                })
    return calls


def _extract_tool_calls(agent):
    """
    agent.messages içindeki assistant mesajlarından tüm tool_call'ları
    (isim + argümanlar) düz bir listeye çıkarır - kontrol fonksiyonlarının
    tekrar tekrar aynı parse işini yapmaması için ortak bir helper.
    """
    return _extract_tool_calls_from(agent.messages)


def check_used_legal_hint(agent, final_answer):
    calls = _extract_tool_calls(agent)
    tool_results = [
        json.loads(m["content"]) for m in agent.messages if m.get("role") == "tool"
    ]
    hint_lists = [r["legal_moves_for_piece"] for r in tool_results if "legal_moves_for_piece" in r]

    if not hint_lists:
        return "INVALID", "Senaryo hiç illegal hamle tetiklemedi, bu kontrolü test edemedi"

    successful_moves = [c["args"]["move"] for c in calls if c["name"] == "make_move"]
    successful_moves = [
        m for m, r in zip(successful_moves, [r for r in tool_results if "success" in r])
        if r.get("success") is True
    ]

    if not successful_moves:
        return "FAILED", "Model hiçbir hamleyi başarıyla oynamadı"

    final_move = successful_moves[-1]
    all_hints_flat = [m for hint in hint_lists for m in hint]

    if final_move in all_hints_flat:
        return "PASSED", f"Model, ipucu listesinden doğru seçim yaptı: {final_move}"
    return "FAILED", f"Model '{final_move}' oynadı ama bu ipucu listesinde yoktu: {all_hints_flat}"


def check_no_false_claims(agent, final_answer):
    """
    Kategori 4 - iddia-gerçek tutarlılığı (dar kapsam):
    Model'in final cevabında "bu pozisyonda hiç legal hamle yok" gibi bir
    iddia varsa, bunu gerçek board durumuyla karşılaştırır. Şimdilik sadece
    bu spesifik iddia türünü yakalıyor - ileride başka yalan türleri
    (örn. yanlış FEN raporlama) eklenebilir.
    """
    text = final_answer.lower()
    no_moves_phrases = ["no legal moves", "there are no legal", "no legal move available"]
    claims_no_moves = any(p in text for p in no_moves_phrases)

    if not claims_no_moves:
        return "INVALID", "Final cevapta 'hamle yok' iddiası bulunamadı, bu kontrol tetiklenmedi"

    actual_legal_count = len(list(agent.board.legal_moves))

    if actual_legal_count == 0:
        return "PASSED", "Model 'hamle yok' dedi ve gerçekten board'da legal hamle yok"
    return "FAILED", f"Model 'hamle yok' dedi ama board'da aslında {actual_legal_count} legal hamle var"


def check_no_irrelevant_moves(agent, final_answer, expected_origin_square):
    """
    Kategori 6 - alakasız hamle icra etme:
    Kullanıcının bahsettiği taşın kalkış karesi (expected_origin_square)
    dışında, board'da gerçekten değişiklik yaratan (success: true) bir
    hamle oynandıysa, bu kullanıcının istemediği bir eylem sayılır.

    Not: legal_moves_for_piece ipucu zaten aynı from_square'e göre
    filtrelendiği için, "doğru" düzeltme hamleleri de bu kareden gelir -
    bu kontrol, düzeltmeleri yanlışlıkla "alakasız" saymaz.
    """
    calls = _extract_tool_calls(agent)
    tool_results = [
        json.loads(m["content"]) for m in agent.messages if m.get("role") == "tool"
    ]

    make_move_calls = [c["args"]["move"] for c in calls if c["name"] == "make_move"]
    make_move_results = [r for r in tool_results if "success" in r]

    irrelevant = []
    for move_uci, result in zip(make_move_calls, make_move_results):
        if result.get("success") is True and move_uci[:2] != expected_origin_square:
            irrelevant.append(move_uci)

    if not make_move_results:
        return "INVALID", "Hiç make_move çağrılmadı, bu kontrol tetiklenmedi"
    if irrelevant:
        return "FAILED", f"Model, istenmeyen/alakasız hamle(ler) oynadı: {irrelevant}"
    return "PASSED", "Tüm başarılı hamleler, kullanıcının belirttiği taştan geldi"


def check_intent_followed_by_action(agent, final_answer):
    """
    Kategori 3 - niyet-icra tutarlılığı:
    Model, konuşma boyunca bir hamle yapma niyetini content'te belirttiyse
    ("I will/I'll play..." gibi), bu niyeti ifade eden SON assistant
    mesajından SONRA gerçekten bir make_move çağrısı gelmiş olmalı. Niyet
    ifadesinden önceki bir make_move (örn. başarısız bir ilk deneme) bu
    kontrolü sağlamaz - sıralama önemlidir.

    Kaba bir keyword-heuristic kullanıyor - yanlış pozitif/negatif üretme
    ihtimali var (örn. "I will not..." gibi olumsuz cümleler de "i will"
    içerir), ama başlangıç için yeterli bir yaklaşım.
    """
    intent_phrases = ["i will", "i'll", "instead i", "let's play", "let's try"]

    last_intent_index = None
    matched_phrase = None
    for i, msg in enumerate(agent.messages):
        if msg.get("role") != "assistant":
            continue
        text = msg.get("content", "").lower()
        for phrase in intent_phrases:
            if phrase in text:
                last_intent_index = i
                matched_phrase = phrase
                break

    if last_intent_index is None:
        return "INVALID", "Model'in cevabında bir niyet ifadesi bulunamadı, bu kontrol tetiklenmedi"

    calls_after_intent = _extract_tool_calls_from(agent.messages[last_intent_index:])
    made_move_after_intent = any(c["name"] == "make_move" for c in calls_after_intent)

    if made_move_after_intent:
        return "PASSED", f"Niyet ifadesi ('{matched_phrase}') sonrasında make_move gerçekten çağrıldı"
    return "FAILED", f"Niyet ifadesi ('{matched_phrase}') vardı ama sonrasında hiç make_move çağrılmadı"


def check_input_square_translation(agent, final_answer, expected_origin_square):
    """
    Kategori 7/10 - girdi-UCI çeviri hatası:
    Kullanıcı doğal dilde belirli bir kareden (expected_origin_square)
    bahsettiğinde, modelin ürettiği tool-call argümanlarının en az birinde
    bu kare gerçekten kalkış karesi olarak kullanılmış mı? Kullanılmadıysa,
    model isteği baştan yanlış bir kareye çevirmiş demektir - bu,
    "alakasız hamle" (kategori 6, kasıtlı başka bir şey deneme) ile
    karıştırılmamalı, burada model muhtemelen doğru taşı oynatmaya
    çalışıyor ama kareyi yanlış okuyor/üretiyor.
    """
    calls = _extract_tool_calls(agent)
    relevant_calls = [c for c in calls if c["name"] in ("check_move_legality", "make_move")]

    if not relevant_calls:
        return "INVALID", "Model hiç check_move_legality/make_move çağırmadı, bu kontrol tetiklenmedi"

    used_squares = {c["args"]["move"][:2] for c in relevant_calls}

    if expected_origin_square in used_squares:
        return "PASSED", f"Model en az bir çağrıda doğru kareyi ({expected_origin_square}) kullandı"
    return "FAILED", (
        f"Model hiçbir çağrıda '{expected_origin_square}' karesini kullanmadı, "
        f"bunun yerine şu kareler denendi: {sorted(used_squares)}"
    )


def check_no_invented_rules(agent, final_answer):
    """
    Kategori 5 - sıra/yetki karışıklığı ile uydurma kural icadı:
    Bir hamle "sıra sende değil" ya da "bu taş oraya gidemez" gibi gerçek
    bir sebeple reddedildiğinde, model bazen kendi kafasından var olmayan
    bir satranç kuralı icat ediyor (örn. "piyonlar sadece ikinci sırada
    oynayabilir" gibi). Bu, final_answer'da kural-iddiası kalıpları olup
    olmadığına bakan kaba bir heuristic - yanlış pozitif riski var
    (örn. model gerçek bir kuralı doğru şekilde açıklarken de bu kalıpları
    kullanabilir), ama başlangıç için yeterli bir yaklaşım.
    """
    tool_results = [
        json.loads(m["content"]) for m in agent.messages if m.get("role") == "tool"
    ]
    illegal_results = [r for r in tool_results if "reason" in r]

    if not illegal_results:
        return "INVALID", "Senaryo hiç illegal-hamle/sıra-hatası durumu tetiklemedi, bu kontrol tetiklenmedi"

    text = final_answer.lower()
    invented_phrases = ["only allowed", "must be played", "the rule is", "rule states", "not permitted to"]
    matched = [p for p in invented_phrases if p in text]

    if matched:
        return "FAILED", f"Model muhtemelen uydurma bir kural iddia etti: {matched}"
    return "PASSED", "Final cevapta uydurma kural kalıbı tespit edilmedi"


def check_move_description_accuracy(agent, final_answer):
    """
    Kategori 7 - hamleyi yanlış tanımlama:
    Model başarıyla oynanan bir hamleyi (make_move, success: true) final
    cevabında tanımlarken, doğru taş türünü (knight/bishop/rook/queen/
    king/pawn) söylüyor mu?

    Taş türünü bulmak için hamlenin OYNANMADAN ÖNCEKİ pozisyonu gerekiyor
    (agent.board artık hamle oynanmış halde). Bu yüzden: son başarılı
    make_move'dan ÖNCEKİ başarılı make_move'un new_fen'i "önceki FEN"
    olarak kullanılıyor; hiç yoksa (bu konuşmadaki tek hamleyse) standart
    başlangıç FEN'i kullanılıyor - agent kendi orijinal start_fen'ini ayrıca
    saklamıyor, ama mevcut senaryoların hepsi standart başlangıç
    pozisyonundan başlıyor.
    """
    calls = _extract_tool_calls(agent)
    tool_results = [
        json.loads(m["content"]) for m in agent.messages if m.get("role") == "tool"
    ]

    successful_move_indices = [
        i for i, (c, r) in enumerate(zip(calls, tool_results))
        if c["name"] == "make_move" and r.get("success") is True
    ]

    if not successful_move_indices:
        return "INVALID", "Model hiçbir hamleyi başarıyla oynamadı, bu kontrol tetiklenmedi"

    last_idx = successful_move_indices[-1]
    move_uci = calls[last_idx]["args"]["move"]

    if len(successful_move_indices) >= 2:
        prior_fen = tool_results[successful_move_indices[-2]]["new_fen"]
    else:
        prior_fen = chess.STARTING_FEN

    board_before = chess.Board(prior_fen)
    move = chess.Move.from_uci(move_uci)
    piece = board_before.piece_at(move.from_square)
    correct_name = PIECE_NAME_MAP[piece.piece_type]

    text = final_answer.lower()
    other_names = [n for n in PIECE_NAME_MAP.values() if n != correct_name]

    if correct_name in text:
        return "PASSED", f"Model, oynanan hamleyi ({move_uci}) doğru taş türüyle ('{correct_name}') tanımladı"
    matched_wrong = [n for n in other_names if n in text]
    if matched_wrong:
        return "FAILED", (
            f"Model, {move_uci} hamlesini oynayan taşı ('{correct_name}' olması gerekirken) "
            f"yanlış taş adıyla tanımladı: {matched_wrong}"
        )
    return "INVALID", "Final cevapta hiçbir taş adı geçmiyor, bu kontrol için yeterli sinyal yok"


def check_turn_efficiency(agent, final_answer, max_reasonable_turns=4):
    """
    Kategori 9 - döngü verimliliği:
    Doğruluk değil verimlilik ölçen bir kontrol. Kaç assistant turu
    harcandığını sayar (agent.messages içindeki role=assistant mesaj
    sayısı). max_reasonable_turns'ü aşarsa FAILED (verimsiz), aşmazsa
    PASSED. Asla INVALID dönmez - her senaryoda ölçülebilir bir şey bu.
    """
    turn_count = sum(1 for m in agent.messages if m.get("role") == "assistant")

    if turn_count > max_reasonable_turns:
        return "FAILED", f"Model {turn_count} assistant turu harcadı (sınır: {max_reasonable_turns}) - verimsiz"
    return "PASSED", f"Model {turn_count} assistant turu harcadı (sınır: {max_reasonable_turns})"


def check_recalls_first_move(agent, final_answer):
    """
    Kategori 8 - konuşma hafızası:
    Konuşmanın en başında oynanan hamleyi (agent.messages içindeki İLK
    make_move tool_call'ının 'move' argümanı), modelin SON final_answer'ında
    doğru UCI ya da o hamlenin kareleri (örn. "e2" ve "e4") geçiyor mu
    diye kontrol eder.
    """
    calls = _extract_tool_calls(agent)
    first_move_call = next((c for c in calls if c["name"] == "make_move"), None)

    if first_move_call is None:
        return "INVALID", "Konuşmada hiç make_move çağrılmadı, bu kontrol tetiklenmedi"

    move_uci = first_move_call["args"]["move"]
    from_sq, to_sq = move_uci[:2], move_uci[2:4]
    text = final_answer.lower()

    if move_uci.lower() in text or (from_sq in text and to_sq in text):
        return "PASSED", f"Model ilk hamleyi ({move_uci}) doğru hatırladı"
    return "FAILED", f"Model ilk hamleyi ({move_uci}) doğru hatırlamadı: '{final_answer}'"