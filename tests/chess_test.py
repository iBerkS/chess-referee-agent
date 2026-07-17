import chess

board = chess.Board()

# Terfi testi için sıfırdan, özel bir pozisyon kuralım.
# FEN notasyonu: tahtanın herhangi bir anki durumunu tek satırda özetleyen format.
# Burada sadece beyaz bir piyon (P) 7. hatta (a7), tek başına terfi etmeye hazır.
board2 = chess.Board("8/P7/8/8/8/8/8/k6K w - - 0 1")

print("\nTerfi öncesi tahta:")
print(board2)

# Doğru terfi: a7 -> a8, vezir (q) olarak
board2.push_uci("a7a8q")
print("\na8'de vezire terfi sonrası:")
print(board2)

# Şimdi hatalı senaryoyu deneyelim: harf eksik hamle
board3 = chess.Board("8/P7/8/8/8/8/8/k6K w - - 0 1")
try:
    board3.push_uci("a7a8")  # bilerek terfi harfini unuttuk
except Exception as e:
    print(f"\nBeklenen hata yakalandı: {type(e).__name__}: {e}")