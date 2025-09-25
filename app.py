from flask import Flask, render_template, request, redirect, url_for, session, flash
import os, json, re

# Optional OpenAI client (enabled when OPENAI_API_KEY is set)
try:
    from openai import OpenAI
    client = OpenAI()
    HAS_OPENAI = True
except Exception:
    HAS_OPENAI = False

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

def _to_json(raw: str) -> dict:
    """Try to parse strict/loose JSON from a model reply."""
    try:
        return json.loads(raw)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    try:
        return json.loads(raw.replace("'", '"'))
    except Exception:
        return {}

def generate_mcqs(source_text: str, num_q: int) -> dict:
    """Call the model to make MCQs; fall back to dummy items if needed."""
    num_q = max(1, min(int(num_q), 10))

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
""" + source_text[:8000]
        try:
            # Chat Completions with Python SDK v1
            resp = client.chat.completions.create(  # official API reference shows this usage
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": "Return ONLY strict JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            raw = resp.choices[0].message.content
            data = _to_json(raw)

            cleaned = []
            for q in (data.get("questions") or [])[:num_q]:
                question = str(q.get("question", "")).strip()
                choices = q.get("choices") or []
                if not question or not isinstance(choices, list) or len(choices) != 4:
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

            if cleaned:
                return {"questions": cleaned}
        except Exception as e:
            print("OpenAI error:", e)

    # Fallback (no API key or model failure)
    qs = []
    for i in range(1, num_q + 1):
        qs.append({
            "question": f"Sample Question {i}?",
            "choices": ["Option A", "Option B", "Option C", "Option D"],
            "answer_index": 0,
        })
    return {"questions": qs}

@app.route("/")
def index():
    return render_template("page1_input.html")

@app.route("/generate", methods=["POST"])
def generate():
    num = request.form.get("num_questions", "5")
    text = (request.form.get("input_text") or "").strip()
    if not text:
        flash("Please paste some text first.", "error")
        return redirect(url_for("index"))

    quiz = generate_mcqs(text, num)
    if not quiz.get("questions"):
        flash("Couldn’t generate questions. Try again.", "error")
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

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
