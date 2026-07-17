import requests
import json
import chess

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
        args = json.loads(tool_call["function"]["arguments"])
        move_uci = args["move"]

        try:
            move = chess.Move.from_uci(move_uci)
            is_legal = move in self.board.legal_moves
            return json.dumps({"legal": is_legal})
        except Exception as e:
            # Format bozuksa (örn. 'xyz' gibi anlamsız bir string) buraya düşer
            return json.dumps({"error": str(e)})

    def ask(self, user_content):
        # Modele gönderdiğimiz FEN'in gerçekte nasıl bir pozisyona karşılık
        # geldiğini insan gözüyle doğrulamak için tahtayı burada yazdırıyoruz.
        # str(self.board) çağrısı, Board class'ının __str__ metodunu tetikler
        # (print(board) yazınca da arka planda aynı şey oluyor).
        print("--- Modelin gördüğü pozisyon (FEN'in insan-okur hali) ---")
        print(self.board)
        print(f"FEN: {self.board.fen()}\n")

        messages = [self._system_message(), {"role": "user", "content": user_content}]

        assistant_message = self._call_model(messages)

        # Model tool çağırmadıysa (nadiren olur ama olabilir) direkt cevabı dön
        if not assistant_message.get("tool_calls"):
            return assistant_message["content"]

        tool_call = assistant_message["tool_calls"][0]
        tool_result = self._execute_tool_call(tool_call)

        messages.append(assistant_message)
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": tool_result
        })

        final_message = self._call_model(messages)
        return final_message["content"]


if __name__ == "__main__":
    # Bu blok, dosya direkt çalıştırıldığında (import edildiğinde değil) devreye girer -
    # Java'daki 'public static void main' ile aynı işlevi görüyor.
    agent = ChessAgent()

    answer = agent.ask(
        "Check if the move 'b1b3' (UCI notation) is legal. "
        "Do not interpret or correct the move - pass it exactly as given."
    )
    print("--- Nihai cevap ---")
    print(answer)