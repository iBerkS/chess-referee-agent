import requests
import json
import chess
import chess.engine

MAX_TURNS = 10
LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
MODEL_NAME = "qwen-satrancprosu"
STOCKFISH_PATH = "D:/creatorstation-chessai/chess-referee-agent/bin/stockfish.exe"

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
    },
{
    "type": "function",
    "function": {
        "name": "evaluate_position",
        "description": "Evaluates the current board position using a real chess engine. Use this when the user asks who is winning, how good a position is, or what the best move is - only makes sense to call after a legal move has been played.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
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
        try:
            move = chess.Move.from_uci(move_uci)
        except Exception:
            return None, False, "invalid UCI format"

        is_legal = move in self.board.legal_moves

        if is_legal:
            return move, True, None

        piece = self.board.piece_at(move.from_square)
        turn_str = "white" if self.board.turn else "black"

        if piece is None:
            reason = f"there is no piece on {chess.square_name(move.from_square)}"
        elif piece.color != self.board.turn:
            reason = f"it is not that piece's turn to move - it is currently {turn_str} to move"
        else:
            reason = "illegal move for that piece in the current position"

        return move, False, reason

    def __init__(self, fen=None):
        # fen verilmezse chess.Board() otomatik standart başlangıç pozisyonunu kurar
        self.board = chess.Board(fen) if fen else chess.Board()

        self.engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)

    def close(self):
        self.engine.quit()

    def _system_message(self):
        return {
            "role": "system",
            "content": (
                f"The current board position (FEN) is: {self.board.fen()}. "
                "You do not need to provide a FEN yourself - only decide which "
                "move to check, in UCI notation. "
                "When you decide to make a move, you must call the make_move tool - "
                "do not merely describe your intention in text without calling it."
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

        if func_name == "evaluate_position":
            info = self.engine.analyse(self.board, chess.engine.Limit(depth=15))
            score = info["score"].white()
            is_mate = score.is_mate()
            cp = score.score(mate_score=100000)
            best_move = info["pv"][0].uci() if info.get("pv") else None
            return json.dumps({
                "score_cp": cp,
                "is_mate": is_mate,
                "best_move": best_move
            })

        move_uci = args["move"]
        move, is_legal , reason = self._check_legality(move_uci)

        if move is None:
            return json.dumps({"error": f"'{move_uci}' geçerli bir UCI formatı değil"})

        legal_hint = None
        if not is_legal and reason == "illegal move for that piece in the current position":
            legal_hint = [
                m.uci() for m in self.board.legal_moves
                if m.from_square == move.from_square
            ]

        if func_name == "check_move_legality":
            result = {"legal": is_legal}
            if not is_legal:
                result["reason"] = reason
            if legal_hint is not None:
                result["legal_moves_for_piece"] = legal_hint
            return json.dumps(result)

        elif func_name == "make_move":
            if not is_legal:
                result = {"success": False, "reason": reason}
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
        "I want to move my knight from b1 to b3. If that's not legal, "
        "play a legal knight move instead. Also, feel free to develop "
        "another piece at the same time if you think it helps."
    )
    print("--- Nihai cevap ---")
    print(answer)
    agent.close()