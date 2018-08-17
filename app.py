# qReadReviews
# - Argenis Rodriguez

from flask import Flask, render_template, request, redirect, session, url_for
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import HTTPException
from os import getenv
import requests
from functools import wraps

# Good Reads API DEVELOPER KEY
# Stored in an Environment Variable
# https://www.goodreads.com/api
gr_key = (getenv("DEV_KEY"))

app = Flask(__name__)

# Sessions will be stored in the local server directory
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# SQLALCHEMY engine fetched from a database hosted on Heroku
# * The DATABASE_URL is stored in an environment Variable
engine = create_engine(getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))
db.init_app(app)

# Wrapper Function to make sure a user is logged into the session
# Will return them to the login screen if condition failed
def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'user_id' in session:
            return f(*args, **kwargs)
        return redirect(url_for('login'))
    return wrap

# ALL returned render_templates will pass in the session variable
# To adjust the page according to the users session
@app.route("/")
@login_required
def index():
    # This query only returns 7 random entries for display on the index page
    display = db.execute("SELECT isbn,title,author,year,reviews_count,rating FROM books ORDER BY RANDOM() LIMIT 7").fetchall()
    return render_template("index.html", sess=session, data=display)

@app.route("/reviews/<book>", methods=['GET','POST'])
@login_required
def reviews(book):
    # POST: For when the user inputs custom data (ex. Search Box)
    # GET: For when the user is directed by a click on a title.
    if request.method == 'POST':
        user_input = request.form.get("user_search")
        display = db.execute("SELECT * FROM books WHERE title LIKE :info OR author LIKE :info OR isbn LIKE :info",\
                            { "info" : str("%" + user_input + "%") }).fetchone()
        if display is None:
            return render_template('error.html', message="No Matching Books Found. Please try a different search!")
        
        return render_template("reviews.html", sess=session, data=display)
        
    else:
        display = db.execute("SELECT * FROM books WHERE isbn = :isbn",{"isbn":book}).fetchone()
        return render_template("reviews.html", sess=session, data=display)

@app.route("/register", methods=['GET','POST'])
def register():
    # POST: For when the user submits the registration form
    # GET: Display the form
    if request.method == 'POST':
        email = request.form.get("user_email")
        username = request.form.get("user_name")
        password = request.form.get("user_pass")
        confirm_pass = request.form.get("user_confirm_pass")

        if email is "" or username is "" or password is "" or confirm_pass is "":
            return render_template('error.html', message="Missing Information.")
        elif db.execute("SELECT username FROM users WHERE username = :email OR username = :username",
                       {"email": email, "username": username}).rowcount > 0:
            return render_template('error.html', message="Email or Username is already in use.")
        elif password != confirm_pass:
            return render_template('error.html', message="Passwords did not match.")
        else:
            # Storing the HASHED sha256 password into the database along with the other info
            db.execute("INSERT INTO users (email,username,password,date_created) VALUES (:email,:username,:password, current_timestamp)", \
                      {"email": email, "username": username, "password" : generate_password_hash(password, method='sha256')})
            db.commit()
            
            # Sessions are stored incase it's needed somewhere else in the code.
            session['user_id'] = db.execute("SELECT user_id FROM users WHERE email = :email",{"email": email}).fetchone()
            session['email'] = email
            session['logged_in'] = True
            return redirect("/")

    else:
        return render_template("register.html", sess=session)

@app.route("/login", methods=['GET','POST'])
def login():
    # '/Login' is the main page if the session is empty (Logged Out)
    session.clear()
    if request.method == 'POST':
        user = request.form.get("login_user")
        pasw = request.form.get("login_pass")
        keepon = request.form.get("keepon")

        # Compares the database password with the provided user password.
        # Will return a boolean
        result = db.execute("SELECT password FROM users WHERE email = :username OR username = :username", {"username": user}).fetchone()
        
        if result is None:
            return render_template('error.html', message="No Such Account Found.")
        elif not check_password_hash(result.password, pasw):
            return render_template('error.html', message="Incorrect Information. Try Again")
     
        if keepon is not None:
            session.permanent = True

        # Filling the Session with info for later reference
        session_data = db.execute("SELECT user_id, username FROM users WHERE username = :username OR email = :username", {"username": user}).fetchone()
        session['user_id'] = session_data.user_id
        session['username'] = session_data.username
        return redirect(url_for('index'))
    return render_template("login.html", sess=session)

@app.route("/logout", methods=['POST'])
@login_required
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route("/top_books/")
@login_required
def top_books():
    data = db.execute('SELECT * FROM books ORDER BY rating DESC LIMIT 50').fetchall()
    return render_template('top_books.html', sess=session, data=data)


@app.route("/profile/<username>")
@login_required
def profile(username):
    result = db.execute("SELECT title,author,year,isbn,rating FROM books JOIN favorites ON favorites.book_id = books.book_id JOIN users ON favorites.user_id = :user_id",
    {"user_id": session['user_id']}).fetchall()
    return render_template('profile.html', sess=session, data=result)


@app.route("/add_favorite/<book>", methods=['POST'])
@login_required
def add_favorite(book):
    book_id = db.execute("SELECT book_id FROM books WHERE isbn = :book",{"book": book}).fetchone().book_id
    db.execute("INSERT INTO favorites(book_id, user_id) VALUES (:book_id, :user_id)",{"book_id": book_id, "user_id" : session['user_id']})
    db.commit()
    return redirect(url_for('index'))


@app.errorhandler(Exception)
def handle_error(e):
    # Global Error Handler
    # Will display the user with a error page without crashing the server
    # Prints the error message to the console
    code = 500
    if isinstance(e, HTTPException):
        code = e.code
    print(e)
    return render_template('error.html', message="Internal Server Error.")

if __name__ == '__main__':
    app.run()