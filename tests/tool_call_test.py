import requests
import json
import chess

url = "http://localhost:1234/v1/chat/completions"

tools = [
    {
        "type": "function",
        "function": {
            "name": "check_move_legality",
            "description": "Checks whether a given move (UCI notation) is legal in a given FEN position.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fen": {
                        "type": "string",
                        "description": "The current board state in FEN notation."
                    },
                    "move": {
                        "type": "string",
                        "description": "The move to check, in UCI notation (e.g. 'e2e4')."
                    }
                },
                "required": ["fen", "move"]
            }
        }
    }
]

# --- 1. ADIM: Kullanıcı mesajını gönder, modelin tool-call üretmesini bekle ---
messages = [
    {
        "role": "system",
        "content": "The current board position (FEN) is: rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1 (standard starting position). Always use this exact FEN when calling tools — never generate or guess a FEN yourself."
    },
    {
        "role": "user",
        "content": "Check if the move 'b1b3' (UCI notation) is legal in the given position. Do not interpret or correct the move — pass it exactly as given to the tool."
    }
]

payload = {
    "model": "qwen-satrancprosu",
    "messages": messages,
    "tools": tools,
    "tool_choice": "auto"
}

response = requests.post(url, json=payload)
result = response.json()

assistant_message = result["choices"][0]["message"]
print("--- Model'in ilk cevabı (tool-call) ---")
print(json.dumps(assistant_message, indent=2, ensure_ascii=False))

# --- 2. ADIM: Modelin ürettiği tool-call'ı gerçekten çalıştır ---
tool_call = assistant_message["tool_calls"][0]

# 'arguments' bir JSON string'i, gerçek bir dict'e çeviriyoruz
args = json.loads(tool_call["function"]["arguments"])

fen = args["fen"]
move_uci = args["move"]

board = chess.Board(fen)

# board.parse_uci, hem string'i bir Move nesnesine çevirir
# hem de format geçersizse hata fırlatır (örn. 'xyz' gibi anlamsız bir string girilirse)
try:
    move = chess.Move.from_uci(move_uci)
    is_legal = move in board.legal_moves
    tool_result_content = json.dumps({"legal": is_legal})
except Exception as e:
    tool_result_content = json.dumps({"error": str(e)})

print(f"\n--- Gerçek python-chess sonucu ---")
print(tool_result_content)

# --- 3. ADIM: Sonucu tekrar modele 'tool' rolüyle gönder, nihai cevabı al ---
messages.append(assistant_message)  # modelin kendi tool-call mesajını konuşma geçmişine ekle
messages.append({
    "role": "tool",
    "tool_call_id": tool_call["id"],
    "content": tool_result_content
})

payload2 = {
    "model": "qwen-satrancprosu",
    "messages": messages,
    "tools": tools,
    "tool_choice": "auto"
}

response2 = requests.post(url, json=payload2)
result2 = response2.json()

final_message = result2["choices"][0]["message"]
print("\n--- Model'in nihai cevabı ---")
print(final_message["content"])