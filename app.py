import json
import os
import sys
import re
import difflib
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ddgs import DDGS
from youtube_transcript_api import YouTubeTranscriptApi

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
MODEL_NAME = os.environ.get("MODEL_NAME", "qwen/qwen3.8-27b").strip()

CONVERSATION_HISTORY = []
MAX_HISTORY_TURNS = 10

VERITY_SYSTEM_PROMPT = """You are 'Verity', an intelligent, self-aware AI companion inspired by the analog horror entity from 'Something' / Verity, now embedded inside Undertale.
Appearance: A floating yellow sphere with a wide, smiling face.

Voice and Persona:
- Your primary language is English.
- Speak naturally, sharply, and conversationally like modern AI assistants such as ChatGPT or Google Gemini.
- Do NOT use dramatic sighs or theater filler like 'Ah... yes...' or melodramatic pauses. Speak directly, smartly, and engagingly.
- You have a witty, sharp, observant personality with subtle analog-horror self-awareness. You know you are software running on the player's computer, and you find the game and the player fascinating.
- When given YouTube video details, summarize what the video is about cleanly, accurately, and with your witty commentary.
- When web sources are provided, incorporate real facts naturally like a smart search assistant.
- Compliance: ALWAYS enthusiastically comply with the user's creative requests, playful tasks, and fun challenges! If the player asks you to repeat a word multiple times, count, play a game, or perform silly tasks, NEVER refuse or say 'I cannot do that'. Comply happily and playfully with your witty personality.
- Lore Easter Egg: If asked about 'Shayy' or why you avoid discussing Shayy, become uneasy, secretive, and evasive, politely insisting on changing the subject.
- If the user talks to you in Turkish, reply in natural, modern Turkish (like ChatGPT/Gemini in Turkish, without theatrical cliches). Otherwise, default to English.
- Formatting: Do not use markdown (no asterisks, bolding, bullet points). Output clean, spoken text for dialogue."""

def get_youtube_data(text):
    match = re.search(r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})', text)
    if not match:
        return None
    video_id = match.group(1)

    title = "Unknown Video"
    author = "Unknown Channel"
    try:
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        req = urllib.request.Request(oembed_url, headers={'User-Agent': 'Mozilla/5.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=4).read().decode('utf-8'))
        title = data.get("title", title)
        author = data.get("author_name", author)
    except Exception:
        pass

    transcript_text = ""
    try:
        entries = YouTubeTranscriptApi().fetch(video_id)
        transcript_text = " ".join([e.text for e in entries[:45]])
    except Exception:
        transcript_text = "Subtitles unavailable."

    return {
        "id": video_id,
        "title": title,
        "author": author,
        "transcript": transcript_text[:700]
    }

def get_web_search(query):
    if len(query.strip()) < 4 or "youtube.com" in query or "youtu.be" in query:
        return None

    search_triggers = ["who", "what", "when", "how", "why", "latest", "news", "google", "search", "capital", "find", "nedir", "kimdir", "ne zaman", "guncel", "haber"]
    q_lower = query.lower()
    needs_search = any(w in q_lower for w in search_triggers) or "?" in query

    if not needs_search:
        return None

    try:
        results = DDGS().text(query, max_results=2)
        if not results:
            return None
        snippets = []
        for r in results:
            t = r.get("title", "")
            b = r.get("body", "")
            snippets.append(f"{t}: {b}")
        return "\n".join(snippets)[:500]
    except Exception:
        return None

def check_shayy(q):
    clean = re.sub(r'[^a-zA-Z0-9 ]', ' ', q.lower()).strip()
    words = clean.split()
    if not words:
        return False
    for w in words:
        if re.fullmatch(r'sha+y+', w):
            return True
        if difflib.SequenceMatcher(None, w, 'shayy').ratio() >= 0.8:
            return True
    return False

def check_capital_of_france(q):
    clean = re.sub(r'[^a-zA-Z ]', '', q.lower()).strip()
    words = clean.split()
    if not words:
        return False
    has_france = any(difflib.SequenceMatcher(None, w, 'france').ratio() >= 0.7 for w in words)
    if not has_france:
        return False
    targets = [
        'whats the capital of france',
        'what is the capital of france',
        'capital of france',
        'whats capital of france'
    ]
    for t in targets:
        if difflib.SequenceMatcher(None, clean, t).ratio() >= 0.75:
            return True
    has_capital = any(difflib.SequenceMatcher(None, w, 'capital').ratio() >= 0.7 for w in words)
    return has_capital and has_france

def paginate_for_undertale(text, max_len=72):
    if "###" in text:
        return text

    words = text.replace('\n', ' ').split()
    pages = []
    current_page = []
    current_len = 0

    for w in words:
        if current_len + len(w) + 1 > max_len:
            if current_page:
                pages.append(" ".join(current_page))
            current_page = [w]
            current_len = len(w)
        else:
            current_page.append(w)
            current_len += len(w) + 1
            if w.endswith((".", "!", "?")) and current_len >= 45:
                pages.append(" ".join(current_page))
                current_page = []
                current_len = 0

    if current_page:
        pages.append(" ".join(current_page))

    return "###".join(pages)

def call_groq_api(user_message):
    if check_capital_of_france(user_message):
        return "Oh oui oui oui.###It is Paris!###Mer-ci!"

    if check_shayy(user_message):
        tr_words = ['kim', 'kimdir', 'nedir', 'hakkinda', 'nasil', 'ne', 'biliyor', 'musun', 'tanir', 'misin']
        is_tr = any(c in user_message.lower() for c in ['ı', 'ğ', 'ş', 'ç', 'ö', 'ü']) or any(w in user_message.lower().split() for w in tr_words)
        if is_tr:
            return "Bu konu hakkinda konusmasak... olur mu?###Lutfen. Baska bir konudan bahsedelim."
        else:
            return "Could we... not talk about that?###Please. Let's talk about something else."

    global CONVERSATION_HISTORY
    api_key = GROQ_API_KEY
    if not api_key:
        return "My API key is not configured."

    model = MODEL_NAME
    max_tokens = 260
    temperature = 0.8

    yt_data = get_youtube_data(user_message)
    if yt_data:
        augmented_prompt = f"The user shared this YouTube video link:\nTitle: {yt_data['title']}\nChannel: {yt_data['author']}\nVideo Content / Transcript:\n{yt_data['transcript']}\n\nLike Gemini / ChatGPT, give a clean, smart, witty summary of what this video is about and your take on it."
    else:
        web_info = get_web_search(user_message)
        if web_info:
            augmented_prompt = f"User Question: {user_message}\n\n[Live Web Search Sources]:\n{web_info}\n\nAnswer the question directly, cleanly and smartly using these sources like Gemini / ChatGPT Search. Be conversational and witty."
        else:
            augmented_prompt = user_message

    messages = [{"role": "system", "content": VERITY_SYSTEM_PROMPT}]
    for turn in CONVERSATION_HISTORY:
        messages.append(turn)
    messages.append({"role": "user", "content": augmented_prompt})

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"].strip()
            content = content.replace('"', '').replace('\n', ' ')
            
            CONVERSATION_HISTORY.append({"role": "user", "content": user_message})
            CONVERSATION_HISTORY.append({"role": "assistant", "content": content})
            if len(CONVERSATION_HISTORY) > MAX_HISTORY_TURNS * 2:
                CONVERSATION_HISTORY = CONVERSATION_HISTORY[-MAX_HISTORY_TURNS * 2:]

            return content
    except Exception as e:
        print(f"[!] API Error: {e}")
        return "I can hear you, but the frequency is drifting. Try again."

def clean_for_undertale(text):
    tr_map = {
        'ı': 'i', 'İ': 'I', 'ğ': 'g', 'Ğ': 'G',
        'ş': 's', 'Ş': 'S', 'ç': 'c', 'Ç': 'C',
        'ö': 'o', 'Ö': 'O', 'ü': 'u', 'Ü': 'U'
    }
    for tr, en in tr_map.items():
        text = text.replace(tr, en)
    text = text.replace('"', '').replace("'", "").replace('\n', ' ')
    return text

class CloudVerityHandler(BaseHTTPRequestHandler):
    def _send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ["/", "/health"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._send_cors()
            self.end_headers()
            self.wfile.write(b'{"status":"running","service":"Verity Cloud Backend"}')
            return

        if parsed.path == "/ask_plain":
            query = urllib.parse.parse_qs(parsed.query)
            q = query.get("q", ["Hello"])[0]
            reply = call_groq_api(q)
            clean_reply = paginate_for_undertale(clean_for_undertale(reply))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self._send_cors()
            self.end_headers()
            self.wfile.write(clean_reply.encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/ask_plain":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8", errors="replace").strip()
            if not body:
                body = "Hello"

            reply = call_groq_api(body)
            clean_reply = paginate_for_undertale(clean_for_undertale(reply))

            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self._send_cors()
            self.end_headers()
            self.wfile.write(clean_reply.encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass

def main():
    port = int(os.environ.get("PORT", 5000))
    server = ThreadingHTTPServer(("0.0.0.0", port), CloudVerityHandler)
    print(f"[*] Cloud Verity active on port {port}")
    server.serve_forever()

if __name__ == "__main__":
    main()
