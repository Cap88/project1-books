import os

from flask import Flask, session, render_template, request, redirect, url_for, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
import requests

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Check for API key variable
if not os.getenv("KEY"):
    raise RuntimeError("KEY is not set")
KEY = os.getenv("KEY")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))


@app.route("/")
def index():
    if session.get("user_id", None) == None:
        return render_template("index.html")
    else:
        return render_template("search.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        user_name = request.form.get("user_name")
        password = request.form.get("password")

        # Make sure the username does not exist
        if db.execute("SELECT * FROM users WHERE user_name = :user_name", {"user_name": user_name}).rowcount > 0:
            return render_template("message.html", message="Username already exists.")
        # Insert user and password
        db.execute("INSERT INTO users (user_name, password) VALUES (:user_name, :password)",
            {"user_name": user_name, "password": password})
        db.commit()
        # Redirect to login
        return render_template("index.html")
    else:
        return render_template("register.html")

@app.route("/login", methods=["POST"])
def login():
    user_name = request.form.get("user_name")
    password = request.form.get("password")

    # Make sure the username and password match
    user = db.execute("SELECT * FROM users WHERE user_name = :user_name AND password = :password", 
        {"user_name": user_name, "password": password}).fetchone()
    if user is None:
        return render_template("index.html", message="Wrong user name and password.")
    else:
        # Add login to session
        session["user_id"] = user.id
        return redirect(url_for('search'))

@app.route("/logout")
def logout():
    # Remove user from session
    session.clear()
    return render_template("index.html")

@app.route("/search", methods=["GET", "POST"])
def search():
    if session.get("user_id", None) == None:
        return render_template("index.html")
    
    if request.method == "POST":
        search = "%" + request.form.get("search") + "%"
        # Query for books for match in ISBN, title or author
        books = db.execute("SELECT * FROM books WHERE isbn LIKE :search OR title LIKE :search OR author LIKE :search", {"search": search}).fetchall()
        if not books:
            message = "Sorry, no books were found."
            return render_template("search.html", message=message)
        else:
            return render_template("search.html", books=books)
    else:
        return render_template("search.html")

@app.route("/book", methods=["GET", "POST"])
def book():
    if session.get("user_id", None) == None:
        return render_template("index.html")

    isbn = request.args.get('isbn')
    book = db.execute("SELECT * FROM books WHERE isbn = :isbn", {"isbn": isbn}).fetchone()
    if not book:
        return render_template("message.html", message="Wrong ISBN")

    if request.method == "POST":
        review = db.execute("SELECT * FROM reviews WHERE user_id = :user_id AND book_id = :book_id", {"user_id": session["user_id"], "book_id": book.id}).fetchone()
        if review is None:
            db.execute("INSERT INTO reviews (rating, comment, book_id, user_id) VALUES (:rating, :comment, :book_id, :user_id)",
                {"rating": request.form.get("rating"), "comment": request.form.get("review"), "book_id": book.id, "user_id": session["user_id"]})
            db.commit()
            return render_template("message.html", message="Success!")
        else:
            return render_template("message.html", message="Review already given.")
    else:
        reviews = db.execute("SELECT * FROM reviews JOIN users ON reviews.user_id = users.id WHERE book_id = :book_id", {"book_id": book.id}).fetchall()
        res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": KEY, "isbns": isbn})
        goodreads = {"average_rating": res.json()["books"][0]["average_rating"], "ratings_count": res.json()["books"][0]["ratings_count"]}
        return render_template("book.html", book=book, reviews=reviews, goodreads=goodreads)

@app.route("/api/<string:isbn>")
def api(isbn):
    # Make sure the isbn exists
    book = db.execute("SELECT * FROM books WHERE isbn = :isbn", {"isbn": isbn}).fetchone()
    if book is None:
        abort(404)
    else:
        reviews = db.execute("SELECT AVG(rating), COUNT(*) FROM reviews WHERE book_id = :book_id;", {"book_id": book.id}).fetchone()
        res = {
            "title": book.title,
            "author": book.author,
            "year": book.year,
            "isbn": book.isbn,
            "review_count": reviews.count,
            "average_score": float("{0:.2f}".format(reviews.avg))
        }
        return jsonify(res)