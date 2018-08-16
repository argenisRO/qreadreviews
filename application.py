from flask import Flask, render_template, request, redirect, session, url_for
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
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
# * The DB_URI is stored in an environment Variable
engine = create_engine(getenv("DB_URI"))
db = scoped_session(sessionmaker(bind=engine))

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
    data = {}

    # This query only returns 7 random entries for display on the index page
    display = db.execute("SELECT isbn,title,author,year FROM books ORDER BY RANDOM() LIMIT 7").fetchall()

    for isbn,title,author,year in display:
        res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": gr_key, "isbns": isbn}).json()

        # Storing data from both the database and API into one dictionary
        # To make it easier to call data through the rendered template
        data[isbn] = {
            'isbn' : isbn,
            'title' : title,
            'author' : author,
            'year' : year,
            'review_count' : res['books'][0]['reviews_count'],
            'rating' : res['books'][0]['average_rating']
        }
    return render_template("index.html", sess=session, data=data)

@app.route("/reviews/<book>", methods=['GET','POST'])
@login_required
def reviews(book):
    # POST: For when the user inputs custom data (ex. Search Box)
    # GET: For when the user is directed by a click on a title.
    if request.method == 'POST':
        user_input = request.form.get("user_search")
        display = db.execute("SELECT * FROM books WHERE title LIKE :info OR author LIKE :info OR isbn LIKE :info", { "info" : str("%" + user_input + "%") }).fetchone()
        if display is None:
            return render_template('error.html', message="No Matching Books Found. Please try again!")
        
        rev = requests.get("https://www.goodreads.com/book/isbn/ISBN?format=json", params={"format" : "json","user_id": 84048400, "isbns": display.isbn}).json()
        data = {
            'isbn' : display.isbn,
            'title' : display.title,
            'author' : display.author,
            'year' : display.year,
            'markup' : rev['reviews_widget']
        }
        
        return render_template("reviews.html", sess=session, data=data)
        
    else:
        display = db.execute("SELECT isbn,title,author,year FROM books WHERE isbn = :isbn",{"isbn":book}).fetchone()
        rev = requests.get("https://www.goodreads.com/book/isbn/ISBN?format=json", params={"format" : "json","user_id": 84048400, "isbns": display.isbn}).json()
        data = {
            'isbn' : display.isbn,
            'title' : display.title,
            'author' : display.author,
            'year' : display.year,
            'markup' : rev['reviews_widget']
        }
        return render_template("reviews.html", sess=session, data=data)

@app.route("/register", methods=['GET','POST'])
def register():
    # POST: For when the user submits the registration form
    # GET: Display the form
    if request.method == 'POST':
        email = request.form.get("user_email")
        password = request.form.get("user_pass")
        confirm_pass = request.form.get("user_confirm_pass")

        if email is "" or password is "" or confirm_pass is "":
            return render_template('error.html', message="Missing Information.")
        elif db.execute("SELECT username FROM users WHERE username = :username", {"username": email}).rowcount > 0:
            return render_template('error.html', message="Email is already in use.")
        elif password != confirm_pass:
            return render_template('error.html', message="Passwords did not match.")
        else:
            db.execute("INSERT INTO users (username,password) VALUES (:username,:password)",{"username": email, "password" :password})
            db.commit()
            
            # Sessions are stored incase it's needed somewhere else in the code.
            session['user_id'] = db.execute("SELECT id FROM users WHERE username = :email",{"email": email}).fetchone()
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
        email = request.form.get("login_user")
        pasw = request.form.get("login_pass")
        keepon = request.form.get("keepon")

        result = db.execute("SELECT * FROM users WHERE username = :email AND password = :password",{"email":email, "password":pasw}).fetchone()
        if result is None:
            return render_template('error.html', message="Incorrect Information")

        # TODO: Add functionality to the 'Keep Me logged in' button

        # Filling the Session with info for later reference
        session['user_id'] = db.execute("SELECT id FROM users WHERE username = :email",{"email": email}).fetchone().id
        session['email'] = email
        return redirect(url_for('index'))
    return render_template("login.html", sess=session)

@app.route("/logout", methods=['POST'])
@login_required
def logout():
    session.clear()
    return redirect(url_for('login'))


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
    # Currently Running the server on debug mode for testing purposes
    app.run(debug=True, port=5000)