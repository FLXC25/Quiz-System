from flask import Flask, render_template, request, redirect, url_for, session
import os

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

# ----- simple quiz generator (no DB, no file parsing) -----
def make_quiz(num=5):
    quiz = {"questions": []}
    for i in range(1, num + 1):
        quiz["questions"].append({
            "question": f"Sample Question {i}?",
            "choices": ["Option A", "Option B", "Option C", "Option D"],
            "answer_index": 0
        })
    return quiz

@app.route("/")
def index():
    return render_template("page1_input.html")

@app.route("/generate", methods=["POST"])
def generate():
    try:
        num = int(request.form.get("num_questions", 5))
    except ValueError:
        num = 5
    num = max(1, min(num, 10))
    quiz = make_quiz(num)
    session["quiz"] = quiz
    return render_template("page2_quiz.html", quiz=quiz)

@app.route("/submit", methods=["POST"])
def submit():
    quiz = session.get("quiz")
    if not quiz:
        return redirect(url_for("index"))

    user_answers = []
    correct = 0
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
        score=score
    )

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
