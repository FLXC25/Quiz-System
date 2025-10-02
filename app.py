import os
from dotenv import load_dotenv

# Load variables from .env into environment
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

print("Loaded key:", OPENAI_API_KEY)  # For debugging only, don’t keep in prod

from flask import Flask, render_template, request, redirect, url_for, session, flash
import os, json, re 

# Try to import OpenAI client
import os

try:
    from openai import OpenAI
    print(os.getenv("OPENAI_API_KEY"))

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    HAS_OPENAI = True
    print("[LOG] OpenAI client initialized successfully.")
except Exception as e:
    HAS_OPENAI = False
    print("[ERROR] Failed to initialize OpenAI client:", str(e))


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

# ---------------- Helpers ---------------- #
def _to_json(raw: str) -> dict:
    """Try to parse strict or loose JSON from model reply."""
    try:
        return json.loads(raw)
    except Exception:
        pass

    # extract {...} block if model added extra text
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass

    # last fallback → replace quotes
    try:
        return json.loads(raw.replace("'", '"'))
    except Exception:
        return {}

# Global switch: turn logging on/off
TEST_LOG = True   # set to False to disable logs

def log(msg: str):
    """Print logs only if TEST_LOG is enabled."""
    if TEST_LOG:
        print(f"[LOG] {msg}")

def generate_mcqs(source_text: str, num_q: int) -> dict:
    """Generate MCQs with OpenAI or fall back to dummy data."""
    num_q = max(1, min(int(num_q), 10))  # ensure 1–10
    log(f"Requested {num_q} questions.")
    log(f"Requested {HAS_OPENAI} questions.")
    if HAS_OPENAI and os.getenv("OPENAI_API_KEY"):
        prompt = f"""
You are a quiz generator. Based on the MATERIAL, produce {num_q} multiple-choice questions.
Return STRICT JSON with this schema:
{{
  "questions": [
    {{"question":"...","choices":["A","B","C","D"],"answer_index":0}},
    ...
  ]
}}
Rules:
- Exactly 4 choices per question.
- answer_index must be 0..3.
- Keep questions clear and self-contained.

MATERIAL:
{source_text[:8000]}
"""
        log("Prompt prepared, calling OpenAI API...")

        try:
            resp = client.chat.completions.create(
    model=os.getenv("OPENAI_MODEL", "gpt-5"),
    messages=[
        {"role": "system", "content": "Return ONLY strict JSON."},
        {"role": "user", "content": prompt},
    ],
    response_format={"type": "json_object"}
)
            raw = resp.choices[0].message.content
            log("Response received from OpenAI API.")
            log(f"Raw output: {raw[:300]}...")  # show first 300 chars

            data = _to_json(raw)
            log("JSON parsing complete.")

            cleaned = []
            for i, q in enumerate((data.get("questions") or [])[:num_q], start=1):
                question = str(q.get("question", "")).strip()
                choices = q.get("choices") or []
                if not question or not isinstance(choices, list) or len(choices) != 4:
                    log(f"Skipping invalid question #{i}")
                    continue
                try:
                    ai = int(q.get("answer_index", 0))
                except Exception:
                    ai = 0
                cleaned.append({
                    "question": question,
                    "choices": [str(c) for c in choices],
                    "answer_index": max(0, min(ai, 3)),
                })
                log(f"Processed question #{i}: {question}")

            if cleaned:
                log(f"Successfully generated {len(cleaned)} questions.")
                return {"questions": cleaned}
        except Exception as e:
            log(f"OpenAI error: {e}")

    # ---------------- fallback (offline or error) ---------------- #
    log("Falling back to dummy questions.")
    qs = []
    for i in range(1, num_q + 1):
        qs.append({
            "question": f"Sample Question {i}?",
            "choices": ["Option A", "Option B", "Option C", "Option D"],
            "answer_index": 0,
        })
    log(f"Generated {len(qs)} fallback questions.")
    return {"questions": qs}


# ---------------- Routes ---------------- #
@app.route("/")
def index():
    return render_template("page1_input.html")

@app.route("/generate", methods=["POST"])
def generate():
    num = request.form.get("num_questions", "5")
    text = (request.form.get("input_text") or "").strip()

    if not text:
        flash("⚠️ Please paste some text first.", "error")
        return redirect(url_for("index"))

    quiz = generate_mcqs(text, num)
    if not quiz.get("questions"):
        flash("⚠️ Couldn’t generate questions. Try again.", "error")
        return redirect(url_for("index"))

    session["quiz"] = quiz
    return render_template("page2_quiz.html", quiz=quiz)

@app.route("/submit", methods=["POST"])
def submit():
    quiz = session.get("quiz")
    if not quiz:
        return redirect(url_for("index"))

    user_answers, correct = [], 0
    for idx, q in enumerate(quiz["questions"]):
        picked = request.form.get(f"q_{idx}")
        try:
            picked_idx = int(picked)
        except (TypeError, ValueError):
            picked_idx = -1
        user_answers.append(picked_idx)
        if picked_idx == q["answer_index"]:
            correct += 1

    total = len(quiz["questions"]) or 1
    score = int(round(100 * correct / total))

    return render_template(
        "page3_result.html",
        quiz=quiz,
        user_answers=user_answers,
        correct=correct,
        total=total,
        score=score,
    )

# ---------------- Run ---------------- #
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
