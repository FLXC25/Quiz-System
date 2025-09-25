import io
import os
import random
import re
from typing import Iterable, List

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from PyPDF2 import PdfReader
from pptx import Presentation


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

ALLOWED_EXTENSIONS = {"pdf", "pptx"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_pdf(stream: io.BytesIO) -> str:
    reader = PdfReader(stream)
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    return "\n".join(pages)


def extract_text_from_pptx(stream: io.BytesIO) -> str:
    presentation = Presentation(stream)
    slide_text: List[str] = []
    for slide in presentation.slides:
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                slide_text.append(shape.text)
    return "\n".join(slide_text)


def sanitize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def pick_candidate_words(text: str) -> List[str]:
    # words with at least four letters, ignoring case
    words = re.findall(r"\b[A-Za-z][A-Za-z'-]{3,}\b", text)
    unique_words = list({word.lower(): word for word in words}.values())
    return unique_words


def build_question(sentence: str, pool: Iterable[str]) -> dict:
    words_in_sentence = re.findall(r"\b[A-Za-z][A-Za-z'-]{3,}\b", sentence)
    if not words_in_sentence:
        raise ValueError("Sentence does not contain suitable words")

    target = random.choice(words_in_sentence)
    # replace first occurrence
    blank_sentence = re.sub(rf"\b{re.escape(target)}\b", "____", sentence, count=1)

    pool_choices = [w for w in pool if w.lower() != target.lower()]
    random.shuffle(pool_choices)
    distractors = pool_choices[:3]

    filler_words = ["Insight", "Strategy", "Concept", "Dynamics", "Framework"]
    idx = 0
    while len(distractors) < 3:
        filler = filler_words[idx % len(filler_words)]
        if filler.lower() != target.lower():
            distractors.append(filler)
        idx += 1

    choices = distractors + [target]
    random.shuffle(choices)
    answer_index = choices.index(target)

    prompt = (
        "In the context of the provided material, what word best completes the "
        f"following sentence?\n{blank_sentence}"
    )

    return {
        "question": prompt,
        "choices": choices,
        "answer_index": answer_index,
        "original_sentence": sentence,
        "answer": target,
    }


def make_quiz_from_text(raw_text: str, num_questions: int) -> dict:
    cleaned_text = sanitize_text(raw_text)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned_text) if s.strip()]
    if not sentences:
        raise ValueError("No sentences were detected in the provided content.")

    candidate_words = pick_candidate_words(cleaned_text)
    if not candidate_words:
        raise ValueError("Not enough meaningful words to create questions.")

    random.shuffle(sentences)
    questions = []

    for sentence in sentences:
        if len(questions) >= num_questions:
            break
        try:
            question = build_question(sentence, candidate_words)
            questions.append(question)
        except ValueError:
            continue

    if not questions:
        raise ValueError("Could not create quiz questions from the provided content.")

    # If we have fewer questions than requested, cycle through existing ones with minor tweaks
    while len(questions) < num_questions:
        recycled = random.choice(questions)
        duplicated = recycled.copy()
        duplicated["question"] += "\n(Repeated for additional practice.)"
        duplicated["choices"] = list(duplicated["choices"])
        questions.append(duplicated)

    return {"questions": questions[:num_questions]}

@app.route("/")
def index():
    return render_template("page1_input.html")

@app.route("/generate", methods=["POST"])
def generate():
    text_input = request.form.get("input_text", "").strip()
    try:
        num_questions = int(request.form.get("num_questions", 5))
    except ValueError:
        num_questions = 5
    num_questions = max(1, min(num_questions, 10))

    file_text = ""
    upload = request.files.get("source_file")
    if upload and upload.filename:
        filename = upload.filename
        if not allowed_file(filename):
            flash("Unsupported file format. Please upload a PDF or PPTX file.")
            return redirect(url_for("index"))

        file_bytes = io.BytesIO(upload.read())
        file_bytes.seek(0)
        extension = filename.rsplit(".", 1)[1].lower()
        try:
            if extension == "pdf":
                file_text = extract_text_from_pdf(file_bytes)
            else:
                file_text = extract_text_from_pptx(file_bytes)
        except Exception as exc:  # pragma: no cover - defensive
            flash(f"Could not read the uploaded file: {exc}")
            return redirect(url_for("index"))

    combined_text = " ".join(part for part in [text_input, file_text] if part).strip()

    if not combined_text:
        flash("Please provide text input or upload a supported file.")
        return redirect(url_for("index"))

    try:
        quiz = make_quiz_from_text(combined_text, num_questions)
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for("index"))

    session["quiz"] = quiz
    session["num_questions"] = num_questions
    return render_template("page2_quiz.html", quiz=quiz, num_questions=num_questions)

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
