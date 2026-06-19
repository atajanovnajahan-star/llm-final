import os
import re
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "Novalingo-final-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///novalingo.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
LLM_API_KEY = os.getenv("LLM_API_KEY")
print("TAVILY =", TAVILY_API_KEY)
print("LLM =", LLM_API_KEY)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)


class Vocabulary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(100), nullable=False)
    phonetic = db.Column(db.String(100))
    part_of_speech = db.Column(db.String(100))
    meaning_cn = db.Column(db.Text)
    english_definition = db.Column(db.Text)
    example_sentence = db.Column(db.Text)
    translation_cn = db.Column(db.Text)
    source_name = db.Column(db.String(120))
    source_url = db.Column(db.Text)
    synonyms = db.Column(db.Text)
    antonyms = db.Column(db.Text)
    collocations = db.Column(db.Text)
    review_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


def is_logged_in():
    return "user_id" in session


def detect_source_name(url):
    if not url:
        return "English Source"

    url = url.lower()

    if "reuters" in url:
        return "Reuters"
    if "bbc" in url:
        return "BBC"
    if "apnews" in url:
        return "AP News"
    if "theguardian" in url:
        return "The Guardian"
    if "npr" in url:
        return "NPR"
    if "nytimes" in url:
        return "The New York Times"

    return "English Source"


def search_real_example(word):
    if not TAVILY_API_KEY:
        return {
            "sentence": f"The word {word} is used in authentic English learning contexts.",
            "source_url": "https://www.bbc.com",
            "source_name": "BBC"
        }

    query = f'"{word}" English news example sentence Reuters BBC AP News Guardian NPR New York Times'

    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "advanced",
                "include_answer": False,
                "include_raw_content": True,
                "max_results": 5
            },
            timeout=20
        )

        data = response.json()
        results = data.get("results", [])

        for item in results:
            content = item.get("content", "")
            url = item.get("url", "")
            sentences = re.split(r"(?<=[.!?])\s+", content)

            for sentence in sentences:
                if word.lower() in sentence.lower() and len(sentence.split()) >= 7:
                    return {
                        "sentence": sentence.strip(),
                        "source_url": url,
                        "source_name": detect_source_name(url)
                    }

        if results:
            return {
                "sentence": results[0].get("content", "")[:250],
                "source_url": results[0].get("url", ""),
                "source_name": detect_source_name(results[0].get("url", ""))
            }

    except Exception:
        pass

    return {
        "sentence": f"The word {word} appears in English news and learning materials.",
        "source_url": "",
        "source_name": "English Source"
    }


def generate_ai_vocabulary(word, example_sentence):
    if not LLM_API_KEY:
        return {
            "phonetic": "/example/",
            "part_of_speech": "noun / verb",
            "meaning_cn": "中文释义",
            "english_definition": "AI generated English definition.",
            "translation_cn": "中文翻译",
            "synonyms": "similar, related",
            "antonyms": "opposite, different",
            "collocations": f"{word} policy, {word} system, {word} decision"
        }

    prompt = f"""
Return ONLY valid JSON. Do not add markdown.

Word: {word}
Real example sentence: {example_sentence}

Generate these fields:
phonetic
part_of_speech
meaning_cn
english_definition
translation_cn
synonyms
antonyms
collocations

Rules:
- meaning_cn and translation_cn must be Simplified Chinese.
- english_definition must be simple English.
- synonyms, antonyms and collocations should be comma-separated strings.

JSON format:
{{
  "phonetic": "",
  "part_of_speech": "",
  "meaning_cn": "",
  "english_definition": "",
  "translation_cn": "",
  "synonyms": "",
  "antonyms": "",
  "collocations": ""
}}
"""

    try:
        response = requests.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "qwen-plus",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an English vocabulary tutor. Return only valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.2
            },
            timeout=60
        )

        print("QWEN STATUS:", response.status_code)
        print("QWEN RESPONSE:", response.text)

        data = response.json()

        if response.status_code != 200:
            return {
                "phonetic": "",
                "part_of_speech": "",
                "meaning_cn": "AI generation failed. Please check Qwen API key, region, or model access.",
                "english_definition": "",
                "translation_cn": "",
                "synonyms": "",
                "antonyms": "",
                "collocations": ""
            }

        content = data["choices"][0]["message"]["content"]

        content = content.replace("```json", "").replace("```", "").strip()

        return json.loads(content)

    except Exception as e:
     print("QWEN ERROR:", str(e))

    return {
            "phonetic": "",
            "part_of_speech": "",
            "meaning_cn": "AI generation failed. Please check API key.",
            "english_definition": "",
            "translation_cn": "",
            "synonyms": "",
            "antonyms": "",
            "collocations": ""
        }


def create_word_entry(word, user_id):
    print("CREATE WORD:", word)

    example = search_real_example(word)
    print("EXAMPLE RESULT:", example)

    ai_data = generate_ai_vocabulary(word, example["sentence"])
    print("AI DATA:", ai_data)

    vocab = Vocabulary(
        word=word,
        phonetic=ai_data.get("phonetic", ""),
        part_of_speech=ai_data.get("part_of_speech", ""),
        meaning_cn=ai_data.get("meaning_cn", ""),
        english_definition=ai_data.get("english_definition", ""),
        example_sentence=example.get("sentence", ""),
        translation_cn=ai_data.get("translation_cn", ""),
        source_name=example.get("source_name", ""),
        source_url=example.get("source_url", ""),
        synonyms=ai_data.get("synonyms", ""),
        antonyms=ai_data.get("antonyms", ""),
        collocations=ai_data.get("collocations", ""),
        user_id=user_id
    )

    db.session.add(vocab)
    db.session.commit()

    return vocab


@app.route("/")
def home():
    if is_logged_in():
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]

        if User.query.filter_by(username=username).first():
            flash("Username already exists.")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("Email already exists.")
            return redirect(url_for("register"))

        user = User(
            username=username,
            email=email,
            password=generate_password_hash(password)
        )

        db.session.add(user)
        db.session.commit()

        flash("Account created successfully.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            session["username"] = user.username
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("login"))

    q = request.args.get("q", "").strip()

    query = Vocabulary.query.filter_by(user_id=session["user_id"])

    if q:
        query = query.filter(Vocabulary.word.contains(q))

    words = query.order_by(Vocabulary.created_at.desc()).all()

    return render_template("dashboard.html", words=words, q=q)


@app.route("/add_word", methods=["POST"])
def add_word():
    if not is_logged_in():
        return redirect(url_for("login"))

    word = request.form["word"].strip().lower()

    if not word:
        flash("Please enter a word.")
        return redirect(url_for("dashboard"))

    existing = Vocabulary.query.filter_by(
        word=word,
        user_id=session["user_id"]
    ).first()

    if existing:
        flash("This word already exists.")
        return redirect(url_for("dashboard"))

    create_word_entry(word, session["user_id"])

    flash("Word added by Example Search Agent.")
    return redirect(url_for("dashboard"))


@app.route("/word/<int:word_id>")
def word_detail(word_id):
    if not is_logged_in():
        return redirect(url_for("login"))

    word = Vocabulary.query.filter_by(
        id=word_id,
        user_id=session["user_id"]
    ).first_or_404()

    return render_template("word_detail.html", word=word)


@app.route("/delete/<int:word_id>", methods=["POST"])
def delete_word(word_id):
    if not is_logged_in():
        return redirect(url_for("login"))

    word = Vocabulary.query.filter_by(
        id=word_id,
        user_id=session["user_id"]
    ).first_or_404()

    db.session.delete(word)
    db.session.commit()

    flash("Word deleted.")
    return redirect(url_for("dashboard"))


@app.route("/review")
def review():
   
    if not is_logged_in():
        return redirect(url_for("login"))

    words = Vocabulary.query.filter_by(
        user_id=session["user_id"]
    ).order_by(Vocabulary.review_count.asc()).all()

    return render_template("review.html", words=words)

@app.route("/quiz", methods=["GET", "POST"])
def quiz():
    if not is_logged_in():
        return redirect(url_for("login"))

    word = Vocabulary.query.filter_by(
        user_id=session["user_id"]
    ).order_by(Vocabulary.review_count.asc()).first()

    if not word:
        flash("Add vocabulary first before starting quiz.")
        return redirect(url_for("dashboard"))

    result = None
    user_answer = ""

    if request.method == "POST":
        user_answer = request.form.get("answer", "").strip()

        correct_answer = (word.meaning_cn or "").strip()

        if user_answer and user_answer in correct_answer:
            result = "correct"
            word.review_count += 1
            db.session.commit()
        else:
            result = "wrong"

    return render_template(
        "quiz.html",
        word=word,
        result=result,
        user_answer=user_answer
    )

@app.route("/review_done/<int:word_id>", methods=["POST"])
def review_done(word_id):
    if not is_logged_in():
        return redirect(url_for("login"))

    word = Vocabulary.query.filter_by(
        id=word_id,
        user_id=session["user_id"]
    ).first_or_404()

    word.review_count += 1
    db.session.commit()

    return redirect(url_for("review"))

@app.route("/api/openclaw", methods=["POST"])
def openclaw_api():
    data = request.get_json() or {}
    message = data.get("message", "").strip().lower()
    user_id = int(data.get("user_id", 1))

    demo_user = User.query.get(user_id)

    if not demo_user:
        demo_user = User(
            username="openclaw",
            email="openclaw@example.com",
            password=generate_password_hash("123456")
        )
        db.session.add(demo_user)
        db.session.commit()
        user_id = demo_user.id

    if message.startswith("add "):
        word = message.replace("add ", "").strip()

        existing = Vocabulary.query.filter_by(
            word=word,
            user_id=user_id
        ).first()

        if existing:
            return jsonify({
                "reply": f"'{word}' already exists.\nMeaning: {existing.meaning_cn}\nExample: {existing.example_sentence}"
            })

        vocab = create_word_entry(word, user_id)

        return jsonify({
            "reply": f"Added: {vocab.word}\nMeaning: {vocab.meaning_cn}\nExample: {vocab.example_sentence}\nTranslation: {vocab.translation_cn}\nSource: {vocab.source_name}\nURL: {vocab.source_url}"
        })

    if message.startswith("query "):
        word_text = message.replace("query ", "").strip()

        vocab = Vocabulary.query.filter_by(
            word=word_text,
            user_id=user_id
        ).first()

        if not vocab:
            return jsonify({
                "reply": "Word not found."
            })

        return jsonify({
            "reply": f"{vocab.word} {vocab.phonetic}\nMeaning: {vocab.meaning_cn}\nExample: {vocab.example_sentence}\nTranslation: {vocab.translation_cn}"
        })

    if message == "review":
        words = Vocabulary.query.filter_by(
            user_id=user_id
        ).order_by(Vocabulary.review_count.asc()).limit(5).all()

        if not words:
            return jsonify({
                "reply": "No review words."
            })

        reply = "Review words:\n"
        reply += "\n".join([
            f"- {w.word}: {w.meaning_cn}"
            for w in words
        ])

        return jsonify({
            "reply": reply
        })

    if message == "quiz":
        word = Vocabulary.query.filter_by(
            user_id=user_id
        ).order_by(Vocabulary.review_count.asc()).first()

        if not word:
            return jsonify({
                "reply": "No quiz available."
            })

        return jsonify({
            "reply": f"Quiz: What does '{word.word}' mean in Chinese?"
        })

    return jsonify({
        "reply": "Commands: add word, query word, review, quiz"
    })
@app.route("/features")
def features():
    if not is_logged_in():
        return redirect(url_for("login"))

    return render_template("features.html")


@app.route("/workflow")
def workflow():
    if not is_logged_in():
        return redirect(url_for("login"))

    return render_template("workflow.html")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        if not User.query.filter_by(username="demo").first():
            demo = User(
                username="demo",
                email="demo@example.com",
                password=generate_password_hash("123456")
            )
            db.session.add(demo)
            db.session.commit()

    app.run(debug=True)





