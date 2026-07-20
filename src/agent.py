import requests
import json
import chess

MAX_TURNS = 10
LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
MODEL_NAME = "qwen-satrancprosu"

# PHASE1.md bulgusu: model FEN'i açık talimata rağmen hayal ediyordu.
# Çözüm: tool şemasından 'fen' tamamen çıkarıldı. Model sadece 'move' üretecek,
# pozisyonun kendisini hiç görmeyecek/üretmeyecek.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_move_legality",
            "description": "Checks whether a given move is legal in the current board position.",
            "parameters": {
                "type": "object",
                "properties": {
                    "move": {
                        "type": "string",
                        "description": "The move to check, in UCI notation (e.g. 'e2e4')."
                    }
                },
                "required": ["move"]
            }
        }
    },
    {
    "type": "function",
    "function": {
        "name": "make_move",
        "description": "Plays a move on the board if it is legal. Use this after confirming legality, or when the user explicitly asks to play a move.",
        "parameters": {
            "type": "object",
            "properties": {
                "move": {
                    "type": "string",
                    "description": "The move to play, in UCI notation (e.g. 'e2e4')."
                }
            },
            "required": ["move"]
        }
    }
    }
]


class ChessAgent:
    """
    Java'daki bir class ile aynı mantık: 'self' = Java'daki 'this'.
    __init__ = constructor (Java'da 'public ChessAgent(...)' gibi düşün).

    Board state (gerçek pozisyon) burada, nesnenin kendi alanında (self.board)
    tutuluyor - Faz 2'de art arda birden fazla hamle oynanacağı için bu state'in
    fonksiyon çağrıları arasında kalıcı olması gerekiyor, bu yüzden class kullandık.
    """

    def _check_legality(self, move_uci):
        """
        Bir UCI string'ini parse edip legal mi diye kontrol eder.
        Format hatasında (örn. 'xyz') exception'ı burada yakalayıp
        None döner - çağıran taraf None görürse "format bozuk" anlar.
        Legal/illegal ayrımı ayrı bir bool olarak dönüyor.
        """
        try:
            move = chess.Move.from_uci(move_uci)
        except Exception:
            return None, False  # (move objesi yok, legal değil)

        is_legal = move in self.board.legal_moves
        return move, is_legal

    def __init__(self, fen=None):
        # fen verilmezse chess.Board() otomatik standart başlangıç pozisyonunu kurar
        self.board = chess.Board(fen) if fen else chess.Board()

    def _system_message(self):
        # Pozisyonu HER İSTEKTE biz enjekte ediyoruz - model asla üretmiyor.
        # self.board.fen() her çağrıldığında GÜNCEL durumu verir (Faz 2'de hamle
        # oynadıkça bu otomatik güncellenmiş olacak).
        return {
            "role": "system",
            "content": (
                f"The current board position (FEN) is: {self.board.fen()}. "
                "You do not need to provide a FEN yourself - only decide which "
                "move to check, in UCI notation."
            )
        }

    def _call_model(self, messages):
        payload = {
            "model": MODEL_NAME,
            "messages": messages,
            "tools": TOOLS,
            "tool_choice": "auto"
        }
        response = requests.post(LM_STUDIO_URL, json=payload)
        return response.json()["choices"][0]["message"]

    def _execute_tool_call(self, tool_call):
        func_name = tool_call["function"]["name"]
        args = json.loads(tool_call["function"]["arguments"])
        move_uci = args["move"]

        move, is_legal = self._check_legality(move_uci)

        if move is None:
            return json.dumps({"error": f"'{move_uci}' geçerli bir UCI formatı değil"})

        # Illegal ise, aynı kalkış karesinden gerçekten oynanabilir hamleleri
        # de ekliyoruz - model "hangi taşı oynatmak istediğini" doğru bildi,
        # sadece hedef kareyi yanlış tahmin etti; bu durumda motorun bildiği
        # doğru cevabı sunuyoruz, modelin yeniden tahmin etmesini beklemiyoruz.
        legal_hint = None
        if not is_legal:
            legal_hint = [
                m.uci() for m in self.board.legal_moves
                if m.from_square == move.from_square
            ]

        if func_name == "check_move_legality":
            result = {"legal": is_legal}
            if legal_hint is not None:
                result["legal_moves_for_piece"] = legal_hint
            return json.dumps(result)

        elif func_name == "make_move":
            if not is_legal:
                result = {"success": False, "reason": "illegal move"}
                if legal_hint is not None:
                    result["legal_moves_for_piece"] = legal_hint
                return json.dumps(result)
            self.board.push(move)
            return json.dumps({"success": True, "new_fen": self.board.fen()})



    def ask(self, user_content):
        print("--- Modelin gördüğü pozisyon (FEN'in insan-okur hali) ---")
        print(self.board)
        print(f"FEN: {self.board.fen()}\n")

        messages = [self._system_message(), {"role": "user", "content": user_content}]

        for tur in range(MAX_TURNS):
            assistant_message = self._call_model(messages)
            messages.append(assistant_message)

            print(f"--- Tur {tur + 1}: modelin tool çağrısı (ham) ---")
            print(json.dumps(assistant_message, indent=2, ensure_ascii=False))

            if not assistant_message.get("tool_calls"):
                print("--- Döngü sonu, gerçek board durumu ---")
                print(self.board)
                print(f"FEN: {self.board.fen()}")
                return assistant_message["content"]

            for tool_call in assistant_message["tool_calls"]:
                tool_result = self._execute_tool_call(tool_call)
                print(f"    -> tool sonucu ({tool_call['function']['name']}): {tool_result}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": tool_result
                })

        # Buraya geldiysek MAX_TURNS bitti ama model hâlâ tool çağırıyor demektir
        return "Model, verilen tur limiti içinde kesin bir cevaba ulaşamadı."


if __name__ == "__main__":
    # Bu blok, dosya direkt çalıştırıldığında (import edildiğinde değil) devreye girer -
    # Java'daki 'public static void main' ile aynı işlevi görüyor.
    agent = ChessAgent()

    answer = agent.ask(
        "I want to move my knight from b1 to b3. If that's not a legal move, "
        "figure out a legal knight move instead and play it."
    )
    print("--- Nihai cevap ---")
    print(answer)