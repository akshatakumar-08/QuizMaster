from flask import Flask, render_template, request, session, redirect, url_for, flash
from sqlalchemy.orm import scoped_session, sessionmaker, joinedload
from models.db_setup import engine, User, Subject, Chapter, Quiz, Question, Score
from werkzeug.security import check_password_hash
from datetime import datetime, timedelta
from functools import wraps
import os
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()
app.secret_key = os.getenv("SECRET_KEY")

# Database session setup
Session = scoped_session(sessionmaker(bind=engine))

# === Login Required Decorator ===
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user_id = session.get("user_id")
            user_role = session.get("role")
            if not user_id:
                return redirect(url_for("login"))
            if role and user_role != role:
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return wrapper
    return decorator

# === INDEX / HOME ===
@app.route('/')
def index():
    if "user_id" in session:
        return redirect(url_for("admin_dashboard" if session["role"] == "admin" else "user_dashboard"))
    return render_template('index.html')


# === AUTHENTICATION ROUTES ===
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        session_db = Session()
        user = session_db.query(User).filter_by(email=email).first()
        session_db.close()

        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            session["role"] = user.role
            return redirect(url_for("admin_dashboard" if user.role == "admin" else "user_dashboard"))

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        full_name = request.form["full_name"]
        qualification = request.form.get("qualification", "")
        dob = request.form["dob"]

        try:
            dob = datetime.strptime(dob, "%Y-%m-%d").date() if dob else None
        except ValueError:
            return redirect(url_for("register"))

        session_db = Session()
        if session_db.query(User).filter_by(email=email).first():
            session_db.close()
            return redirect(url_for("register"))

        new_user = User(email=email, full_name=full_name, qualification=qualification, dob=dob, role="user")
        new_user.set_password(password)
        session_db.add(new_user)
        session_db.commit()
        session_db.close()

        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# === USER ROUTES (Protected) ===
@app.route('/user/dashboard')
@login_required(role="user")
def user_dashboard():
    session_db = Session()
    user_id = session["user_id"]

    quizzes = session_db.query(Quiz).options(joinedload(Quiz.questions)).all()
    attempted_quiz_ids = set(
        row.quiz_id for row in session_db.query(Score.quiz_id).filter_by(user_id=user_id).all()
    )

    session_db.close()
    return render_template('user/user_dashboard.html', quizzes=quizzes, attempted_quiz_ids=attempted_quiz_ids)



@app.route('/user/summary')
@login_required(role="user")
def user_summary():
    session_db = Session()
    user_id = session["user_id"]

    # Join Score -> Quiz -> Chapter -> Subject
    results = session_db.query(Score, Quiz, Chapter, Subject)\
        .join(Quiz, Score.quiz_id == Quiz.id)\
        .join(Chapter, Quiz.chapter_id == Chapter.id)\
        .join(Subject, Chapter.subject_id == Subject.id)\
        .filter(Score.user_id == user_id)\
        .all()

    session_db.close()

    subject_counts = {}
    month_counts = {}

    for score, quiz, chapter, subject in results:
        subject_name = subject.name
        month = quiz.quiz_date.strftime("%B")

        subject_counts[subject_name] = subject_counts.get(subject_name, 0) + 1
        month_counts[month] = month_counts.get(month, 0) + 1

    return render_template("user/user_summary.html",
        subject_labels=list(subject_counts.keys()),
        subject_counts=list(subject_counts.values()),
        month_labels=list(month_counts.keys()),
        month_counts=list(month_counts.values())
    )




@app.route('/user/quiz/<int:quiz_id>')
@login_required(role="user")
def view_quiz(quiz_id):
    session_db = Session()
    quiz = session_db.query(Quiz)\
        .options(
            joinedload(Quiz.questions),
            joinedload(Quiz.chapter).joinedload(Chapter.subject)
        ).get(quiz_id)

    if not quiz:
        session_db.close()
        return redirect(url_for("user_dashboard"))

    session_db.expunge_all()
    session_db.close()

    return render_template("user/view_quiz.html", quiz=quiz)


@app.route("/take_quiz/<int:quiz_id>/<int:q_no>", methods=["GET", "POST"])
@login_required(role="user")
def take_quiz(quiz_id, q_no):
    session_db = Session()
    quiz = session_db.query(Quiz).options(joinedload(Quiz.questions)).filter_by(id=quiz_id).first()

    if not quiz or q_no > len(quiz.questions) or q_no < 1:
        return redirect(url_for("user_dashboard"))

    question = quiz.questions[q_no - 1]

    # Save quiz start time only once
    if "quiz_start_time" not in session:
        session["quiz_start_time"] = datetime.utcnow().isoformat()

    # Calculate remaining time
    start_time = datetime.fromisoformat(session["quiz_start_time"])
    quiz_end_time = start_time + timedelta(minutes=quiz.duration)
    remaining_time = (quiz_end_time - datetime.utcnow()).total_seconds()
    if remaining_time <= 0:
        return redirect(url_for("submit_quiz", quiz_id=quiz_id))

    if request.method == "POST":
        selected_option = request.form.get("option")
        if selected_option:
            session["answers"] = session.get("answers", {})
            session["answers"][str(question.id)] = selected_option

        if q_no < len(quiz.questions):
            return redirect(url_for("take_quiz", quiz_id=quiz_id, q_no=q_no + 1))
        else:
            return redirect(url_for("submit_quiz", quiz_id=quiz_id))

    return render_template("user/take_quiz.html", quiz=quiz, question=question, q_no=q_no, total=len(quiz.questions), remaining_time=int(remaining_time))


@app.route("/submit_quiz/<int:quiz_id>")
@login_required(role="user")
def submit_quiz(quiz_id):
    session.pop("quiz_start_time", None)
    session_db = Session()
    quiz = session_db.query(Quiz).options(joinedload(Quiz.questions)).filter_by(id=quiz_id).first()
    answers = session.pop("answers", {})
    score = 0

    for question in quiz.questions:
        correct = question.correct_option
        selected = answers.get(str(question.id))
        if selected == correct:
            score += 1

    # Save score
    new_score = Score(
        user_id=session["user_id"],
        quiz_id=quiz.id,
        score=score,
        total=len(quiz.questions)
    )
    session_db.add(new_score)
    session_db.commit()
    session_db.close()

    return redirect(url_for("user_scores"))

@app.route('/user/scores')
@login_required(role="user")
def user_scores():
    session_db = Session()
    scores = (
        session_db.query(Score)
        .options(joinedload(Score.quiz))
        .filter_by(user_id=session["user_id"])
        .order_by(Score.timestamp.desc())
        .all()
    )
    session_db.close()
    return render_template('user/scores.html', scores=scores)


# === ADMIN ROUTES (Protected) ===
@app.route('/admin/dashboard')
@login_required(role="admin")
def admin_dashboard():
    session_db = Session()
    subjects = session_db.query(Subject)\
        .options(joinedload(Subject.chapters)
        .joinedload(Chapter.quizzes)
        .joinedload(Quiz.questions)).all()
    session_db.close()
    return render_template('admin/adm_dashboard.html', subjects=subjects)


@app.route('/admin/summary')
@login_required(role="admin")
def admin_summary():
    session_db = Session()

    # Get all scores with subject info
    results = session_db.query(Score, Quiz, Chapter, Subject)\
        .join(Quiz, Score.quiz_id == Quiz.id)\
        .join(Chapter, Quiz.chapter_id == Chapter.id)\
        .join(Subject, Chapter.subject_id == Subject.id)\
        .all()

    subject_counts = {}
    month_counts = {}

    for score, quiz, chapter, subject in results:
        subject_name = subject.name
        month_name = quiz.quiz_date.strftime("%B")

        subject_counts[subject_name] = subject_counts.get(subject_name, 0) + 1
        month_counts[month_name] = month_counts.get(month_name, 0) + 1

    session_db.close()

    return render_template("admin/adm_summary.html",
        subject_labels=list(subject_counts.keys()),
        subject_counts=list(subject_counts.values()),
        month_labels=list(month_counts.keys()),
        month_counts=list(month_counts.values())
    )



@app.route('/admin/manage-quizzes')
@login_required(role="admin")
def quiz_management():
    session_db = Session()
    quizzes = session_db.query(Quiz).all()
    session_db.close()
    return render_template("admin/quiz_management.html", quizzes=quizzes)


# === SUBJECT CRUD ===
@app.route("/admin/subjects")
@login_required(role="admin")
def subject_management():
    session_db = Session()
    subjects = session_db.query(Subject).all()
    session_db.close()
    return render_template("admin/subject_management.html", subjects=subjects)


@app.route('/admin/quiz/delete/<int:quiz_id>', methods=["POST"])
@login_required(role="admin")
def delete_quiz(quiz_id):
    session_db = Session()
    quiz = session_db.query(Quiz).get(quiz_id)

    if quiz:
        for question in quiz.questions:
            session_db.delete(question)
        session_db.delete(quiz)
        session_db.commit()
    else:
        flash("Quiz not found!", "danger")

    session_db.close()
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/quiz/edit/<int:quiz_id>', methods=["GET", "POST"])
@login_required(role="admin")
def edit_quiz(quiz_id):
    session_db = Session()
    quiz = session_db.query(Quiz).options(joinedload(Quiz.questions)).get(quiz_id)

    if not quiz:
        session_db.close()
        return redirect(url_for('admin_dashboard'))

    if request.method == "POST":
        for question in quiz.questions:
            question.question_text = request.form.get(f"question_text_{question.id}")
            question.option_a = request.form.get(f"option_a_{question.id}")
            question.option_b = request.form.get(f"option_b_{question.id}")
            question.option_c = request.form.get(f"option_c_{question.id}")
            question.option_d = request.form.get(f"option_d_{question.id}")
            question.correct_option = request.form.get(f"correct_option_{question.id}")

        session_db.commit()
        session_db.close()
        return redirect(url_for('admin_dashboard'))

    session_db.close()
    return render_template('admin/edit_quiz.html', quiz=quiz)

@app.route('/admin/new-quiz', methods=['GET', 'POST'])
@login_required(role="admin")
def new_quiz():
    session_db = Session()

    if request.method == "POST":
        quiz_name = request.form["quiz_name"]
        chapter_id = request.form["chapter_id"]
        quiz_date = request.form["quiz_date"]
        duration = request.form["duration"]
        num_questions = request.form["num_questions"]

        if not quiz_name.strip() or not chapter_id or not quiz_date or not duration or not num_questions:
            session_db.close()
            return redirect(url_for('new_quiz'))

        new_quiz = Quiz(
            quiz_name=quiz_name,
            chapter_id=int(chapter_id),
            quiz_date=datetime.strptime(quiz_date, "%Y-%m-%d"),
            duration=int(duration)
        )
        session_db.add(new_quiz)
        session_db.commit()

        quiz_id = new_quiz.id
        session_db.close()
        return redirect(url_for('add_questions', quiz_id=quiz_id, num_questions=num_questions))

    # 🛠 FIX: Eager load the subject relation before using in template
    chapters = session_db.query(Chapter).options(joinedload(Chapter.subject)).all()
    session_db.close()
    return render_template('admin/new_quiz.html', chapters=chapters)


@app.route('/admin/quiz/<int:quiz_id>/add-questions', methods=['GET', 'POST'])
@login_required(role="admin")
def add_questions(quiz_id):
    num_questions = int(request.args.get('num_questions', 0))
    session_db = Session()

    if request.method == "POST":
        for i in range(1, num_questions + 1):
            q = Question(
                question_text=request.form.get(f"question_text_{i}"),
                option_a=request.form.get(f"option_a_{i}"),
                option_b=request.form.get(f"option_b_{i}"),
                option_c=request.form.get(f"option_c_{i}"),
                option_d=request.form.get(f"option_d_{i}"),
                correct_option=request.form.get(f"correct_option_{i}"),
                quiz_id=quiz_id
            )
            session_db.add(q)

        session_db.commit()
        session_db.close()
        return redirect(url_for('admin_dashboard'))

    session_db.close()
    return render_template('admin/add_questions.html', num_questions=num_questions)


@app.route('/admin/new-subject', methods=['GET', 'POST'])
@login_required(role="admin")
def new_subject():
    session_db = Session()
    if request.method == 'POST':
        name = request.form.get("name", "").strip()
        if not name:
            return redirect(url_for('new_subject'))

        subject = Subject(name=name)
        session_db.add(subject)
        session_db.commit()
        session_db.close()
        return redirect(url_for('admin_dashboard'))

    session_db.close()
    return render_template('admin/new_subject.html')


@app.route("/admin/subjects/edit/<int:subject_id>", methods=["POST"])
@login_required(role="admin")
def edit_subject(subject_id):
    session_db = Session()
    subject = session_db.query(Subject).get(subject_id)

    if subject:
        subject.name = request.form["name"]
        subject.description = request.form["description"]
        session_db.commit()
    else:
        flash("Subject not found!", "danger")

    session_db.close()
    return redirect(url_for("subject_management"))


@app.route("/admin/subjects/delete/<int:subject_id>", methods=["POST"])
@login_required(role="admin")
def delete_subject(subject_id):
    session_db = Session()
    subject = session_db.query(Subject).get(subject_id)

    if subject:
        session_db.delete(subject)
        session_db.commit()
        flash("Subject deleted!", "success")
    else:
        flash("Subject not found!", "danger")

    session_db.close()
    return redirect(url_for("subject_management"))


@app.route("/new_chapter", methods=["GET", "POST"])
@login_required(role="admin")
def new_chapter():
    session_db = Session()

    if request.method == "POST":
        chapter_name = request.form["chapter_name"]
        subject_id = request.form["subject_id"]

        if not chapter_name.strip() or not subject_id:
            flash("Chapter name and subject must be selected!", "danger")
            session_db.close()
            return redirect(url_for('new_chapter'))

        new_chapter = Chapter(chapter_name=chapter_name.strip(), subject_id=int(subject_id))
        session_db.add(new_chapter)
        session_db.commit()
        session_db.close()
        return redirect(url_for('admin_dashboard'))

    subjects = session_db.query(Subject).all()
    session_db.close()
    return render_template("admin/new_chapter.html", subjects=subjects)


@app.route('/admin/manage-users')
@login_required(role="admin")
def manage_users():
    session_db = Session()
    users = session_db.query(User).all()
    session_db.close()
    return render_template('admin/manage_users.html', users=users)


# === NEW QUESTION PAGE (if needed separately) ===
@app.route('/admin/new-question')
@login_required(role="admin")
def new_question():
    return render_template('admin/new_question.html')


# === FLASK BOOTSTRAP ===
if __name__ == '__main__':
    app.run(debug=True)
