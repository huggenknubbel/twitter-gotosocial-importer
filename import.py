import json
import os
import re
import requests
from datetime import datetime
import time
import glob

# Konfiguration
GOTOSOCIAL_URL = "{Your URL with https://}]"
ACCESS_TOKEN = "{generated access token}"
MEDIA_BASE_DIR = "tweets_media"
TWEETS_JS_PATH = "tweets.js"
DELAY = 1  # Sekunden zwischen API-Requests

# Verbessertes JSON Parsing für Twitter-Archiv
def parse_twitter_js_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

        # Entferne JavaScript Präfix
        if content.startswith("window.YTD.tweets.part"):
            content = content.split("=", 1)[1].strip()

        # Behandle eventuelle fehlende Kommas
        content = re.sub(r'}\s*{', '},{', content)

        return json.loads(content)

# Hilfsfunktionen
def parse_twitter_date(date_str):
    return datetime.strptime(date_str, "%a %b %d %H:%M:%S %z %Y")

def upload_media(file_path, alt_text=None):
    url = f"{GOTOSOCIAL_URL}/api/v2/media"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}

    try:
        with open(file_path, 'rb') as f:
            files = {'file': f}
            data = {'description': alt_text} if alt_text else {}
            response = requests.post(url, files=files, data=data, headers=headers)

        # Korrektur: Erfolg bei 200 (nicht 202)
        if response.status_code == 200:
            media_data = response.json()
            return media_data.get('id')
        print(f"Fehler beim Upload: {response.status_code} {response.text}")
        return None
    except Exception as e:
        print(f"Upload-Fehler: {str(e)}")
        return None

def clean_text(tweet):
    text = tweet["full_text"]

    # Ersetze normale URLs
    for url in tweet["entities"]["urls"]:
        text = text.replace(url["url"], url.get("expanded_url", url["url"]))

    # Entferne Medien-URLs
    for media in tweet.get("extended_entities", {}).get("media", []):
        text = text.replace(media["url"], "")

    # Entferne führende/folgende Leerzeichen
    return re.sub(r'\s+', ' ', text).strip()

def extract_media_filename(media_url):
    """Vereinfachte Extraktion des Dateinamens aus der URL"""
    return media_url.split("/")[-1]

# Hauptverarbeitung
try:
    # Tweets laden
    tweets_data = parse_twitter_js_file(TWEETS_JS_PATH)
    print(f"Erfolgreich {len(tweets_data)} Tweets geladen")

    # Tweets filtern
    filtered_tweets = []
    for entry in tweets_data:
        tweet = entry["tweet"]

        # Filterkriterien
        if (
            tweet.get("in_reply_to_status_id") is None and
            not tweet["full_text"].startswith('@') and
            "poll" not in tweet and
            "retweeted_status" not in tweet
        ):
            filtered_tweets.append(tweet)

    print(f"Gefilterte Tweets: {len(filtered_tweets)}")

    # Tweets verarbeiten
    for tweet in filtered_tweets:
        tweet_id = tweet["id_str"]
        try:
            # Textbereinigung
            text = clean_text(tweet)

            # Medienverarbeitung
            media_ids = []

            # Prüfen ob Medien vorhanden sind
            if "extended_entities" in tweet and "media" in tweet["extended_entities"]:
                for media in tweet["extended_entities"]["media"]:
                    # Extrahiere den Dateinamen aus der media_url_https
                    filename = extract_media_filename(media["media_url_https"])

                    # Konstruiere den erwarteten Dateipfad
                    file_pattern = os.path.join(MEDIA_BASE_DIR, f"{tweet_id}-{filename}")

                    # Suche nach passenden Dateien (mit verschiedenen Erweiterungen)
                    matching_files = glob.glob(file_pattern + "*")

                    if matching_files:
                        # Nehme die erste passende Datei
                        file_path = matching_files[0]
                        alt_text = media.get("ext_alt_text", "")
                        uploaded_id = upload_media(file_path, alt_text)
                        if uploaded_id:
                            media_ids.append(uploaded_id)
                            time.sleep(DELAY)
                        else:
                            print(f"Upload fehlgeschlagen für: {file_path}")
                    else:
                        print(f"Medien-Datei nicht gefunden: {file_pattern}")

            # Status erstellen
            created_at = parse_twitter_date(tweet["created_at"])
            payload = {
                "status": text,
                "scheduled_at": created_at.isoformat(),
                "visibility": "public",
                "media_ids": media_ids  # Array von Medien-IDs
            }

            # Status senden
            headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
            response = requests.post(
                f"{GOTOSOCIAL_URL}/api/v1/statuses",
                json=payload,
                headers=headers
            )

            if response.status_code == 200:
                media_count = len(media_ids)
                print(f"Importiert: {tweet_id} mit {media_count} Medien")
            else:
                print(f"Fehler bei Status-Erstellung für {tweet_id}: {response.status_code} {response.text}")

            time.sleep(DELAY)

        except Exception as e:
            print(f"Fehler bei Tweet {tweet_id}: {str(e)}")

except json.JSONDecodeError as e:
    print(f"JSON Parse Fehler: {str(e)}")
    print("Stelle sicher, dass die tweets.js korrekt formatiert ist")
except Exception as e:
    print(f"Kritischer Fehler: {str(e)}")

print("Import abgeschlossen!")
