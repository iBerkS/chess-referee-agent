import requests

# LM Studio, OpenAI'nin API formatını taklit ediyor (uyumlu endpoint).
# Bu yüzden "requests" ile normal bir HTTP isteği atıyoruz, özel bir kütüphane gerekmiyor.
response = requests.get("http://localhost:1234/v1/models")

print(response.json())