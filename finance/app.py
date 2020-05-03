import sqlalchemy
import os
import time
import sqlite3
import sys

from datetime import datetime
#from utils import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def SQL(db_file):
    """ create a database connection to the SQLite database
        specified by the db_file
    """
    # conn = None
    # try:
    #     conn = sqlite3.connect(db_file)
    # except RuntimeError as e:
    #     print(e)
    #
    # return conn

    engine = None
    try:
        engine = sqlalchemy.create_engine(
            db_file,
            connect_args={'check_same_thread': False}
            )
    except RuntimeError as e:
        print(e)
  
    return engine

# def db_execute(conn, query, parameters = None):
#     """
#     Given the query, execute and return the result
#     """
#     conn.row_factory = dict_factory
#     cur = conn.cursor()
#     cur.execute(query)
 
#     rows = cur.fetchall()

def db_execute(path, query, parameters = None):
    """
    Given the query, execute and return the result
    """
    # engine = None
    # try:
    #     engine = sqlalchemy.create_engine(
    #         path,
    #         connect_args={'check_same_thread': False}
    #         )
    # except RuntimeError as e:
    #     print(e)

    engine = SQL(path)

    res_list = []
    res = engine.execute(query)
    # for r in res:
    #     res_list.append(r.__)
    if res:
        for r in res:
            res_list.append(r)
    
    return res_list

 

# Configure library to use SQLite database
#db = SQL("finance.db")
db = "sqlite:///finance.db"
print(type(db))

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    user_id = session["user_id"]

    # Query database for stock holdings
    rows = db_execute(db, f"""
        SELECT SUM(quantity) as total_count
             , ticker_symbol 
        FROM transaction_history 
        WHERE user_id = {user_id} 
        GROUP BY user_id, ticker_symbol 
        HAVING SUM(quantity) > 0""")

    positions = []
    for row in rows:
        stock_data = lookup(row["ticker_symbol"])
        positions.append({"symbol": stock_data["symbol"], "shares": row["total_count"],
                          "price": stock_data["price"], "total_value": round((stock_data["price"] * row["total_count"]), 2)})

    # Update user balance
    total_cash = db_execute(db, f"""
        SELECT cash 
        FROM users 
        WHERE id = {user_id}""")[0]["cash"]
    total_cash_fmt = "$" + str(round(total_cash, 2))

    total_holding_value = 0
    for position in positions:
        total_holding_value = total_holding_value + position["total_value"]

    total_holding_value_fmt = "$" + str(round(total_holding_value, 2))

    return render_template("index.html", positions=positions, total_cash=total_cash_fmt, total_holding_value=total_holding_value_fmt)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        quantity = request.form.get("shares")
        if not symbol:
            return apology("must provide symbol", 400)
        while True:
            try:
                val = int(quantity)
                if val >= 0:
                    break
                else:
                    return apology("Amount needs to be a positive integer", 400)
            except ValueError:
                return apology("Amount needs to be a positive integer, try again", 400)
            if not request.form.get("symbol"):
                return apology("must provide symbol", 400)

        stock_data = lookup(symbol)

        if not stock_data:
            return apology("There is no such ticker symbol", 400)

        # Get user_id
        user_id = session["user_id"]

        # Get the old balance
        old_balance = db_execute(db, f"""
            SELECT cash 
            FROM users 
            WHERE id = {user_id}""")[0]["cash"]

        # Get info from lookup
        price = stock_data["price"]
        ticker_symbol = stock_data["symbol"]
        trade_cost = stock_data["price"] * int(quantity)

        if old_balance < trade_cost:
            return apology("Not enough money to make this trade", 403)

        # Get new max transaction_id for insertion
        new_max_transaction_id = db_execute(db, f"""
            SELECT max(transaction_id) AS max_id 
            FROM transaction_history""")[0]["max_id"]

        if new_max_transaction_id:
            transaction_id = new_max_transaction_id + 1
        else:
            transaction_id = 1

        # Get current time
        timestamp = datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S:%f')

        # Insert new row into database
        rows = db_execute(db, f"""
            INSERT INTO transaction_history (
                transaction_id
              , transaction_type
              , user_id
              , total
              , ticker_symbol
              , timestamp
              , quantity
              , price) 
            VALUES ({transaction_id}
              , 'buy'
              , {user_id}
              , {trade_cost}
              , '{ticker_symbol}'
              , '{timestamp}'
              , {quantity}
              , {price})""")

        # Update user balance
        rows = db_execute(db, f"""UPDATE users 
            SET cash = cash - {trade_cost} - 5 
            WHERE id = {user_id}""")

        flash(f"{quantity} shares of {ticker_symbol} purchased at ${price} a share !")

    return render_template("buy.html")


@app.route("/lookup", methods=["GET"])
@login_required
def lookupprice():
    return jsonify(lookup(request.args.get("symbol")))


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""

    username = request.args.get("username")

    # Ensure username was submitted
    if not username:
        return apology("must provide username", 400)

    if len(username) < 2 or (db_execute(db, f"""
       SELECT COUNT(*) AS u_count 
       FROM users 
       WHERE username = {username}""")[0]["u_count"] > 0):
        return jsonify(False)
    else:
        return jsonify(True)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Get user_id
    user_id = session["user_id"]

    # Get the users transactions
    transactions = db_execute(db, f"""
        SELECT transaction_type
             , round(total, 2) as total
             , ticker_symbol
             , substr(timestamp, 1, 19) as timestamp
             , quantity
             , price 
        FROM transaction_history 
        WHERE user_id = '{user_id}' 
        ORDER BY timestamp DESC""")

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)
        
        username=request.form.get("username")

        # Query database for username
        rows = db_execute(db, f"SELECT * FROM users WHERE username = '{username}'")

        # Ensure username exists and password is correct
        if not rows:
            return apology("invalid username and/or password", 400) 
        elif len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # User reached  route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("symbol"):
            return apology("no symbol given", 400)

        symbol = request.form.get("symbol")
        quote_data = lookup(symbol)

        if not quote_data:
            return apology("There is no such quote", 400)

        return render_template("quoted.html", quote_data=quote_data)
    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    # Forget any user_id
    session.clear()

    # User reached  route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)
        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Check if confirmatiopn and password are the same
        elif request.form.get("password") != request.form.get("confirmation"):
            #flash(f"Password and confirmation are not the same.")
            return apology("must confirm password", 400)

        # Get max id for insertion
        print(db_execute(db, "SELECT max(id) AS max_id FROM users"))
        max_id = db_execute(db, "SELECT max(id) AS max_id FROM users")[0]["max_id"]

        if max_id:
            new_max_id = max_id + 1
        else:
            new_max_id = 1

        username = request.form.get("username")
        # Query database for username, to see if already exists
        rows = db_execute(db, f"""SELECT * FROM users WHERE username = '{username}'""")

        # If username exists, return error
        if len(rows) != 0:
            flash("username already exists!")

            # return render_template("register.html", 400)
            return apology("username is already used", 400)

        # Insert new row into database
        rows = db_execute(db, "INSERT INTO users (id, username, hash, cash) VALUES ({id}, '{username}', '{hash}', {cash})".format(
            id=new_max_id, username=request.form.get("username"), hash=generate_password_hash(request.form.get("password")), cash=0))

        new_rows = db_execute(db, "SELECT username FROM users WHERE username = '{username}'".format(username=username))

        if (len(new_rows) > 0):
            session["user_id"] = new_max_id
            flash("registration succesful!")
            return redirect("/")

        else:
            flash("registration unsuccesful :(")
            return render_template("register.html")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # Get user_id
    user_id = session["user_id"]

    if request.method == "POST":
        symbol = request.form.get("symbol")
        quantity = request.form.get("shares")

        if not symbol:
            return apology("must provide symbol", 400)
        while True:
            try:
                quantity = int(quantity)
                if quantity >= 0:
                    break
                else:
                    return apology("Amount needs to be a positive integer", 400)
            except ValueError:
                return apology("Amount needs to be a positive integer, try again", 400)
            if not request.form.get("symbol"):
                return apology("must provide symbol", 400)

        stock_data = lookup(symbol)

        # Get info from lookup
        price = stock_data["price"]
        ticker_symbol = stock_data["symbol"]
        trade_cost = stock_data["price"] * int(quantity) * -1
        quantity = quantity * -1

        # Get the old balance
        num_old_shares = db_execute(db, f"""
            SELECT SUM(quantity) as sum_q 
            FROM transaction_history 
            WHERE user_id = {user_id} 
              AND ticker_symbol = '{ticker_symbol}' """)[0]["sum_q"] or 0

        print(type(num_old_shares))
        print(type(quantity))

        if num_old_shares < quantity:
            return apology("You do not hold enough shares to make this trade", 400)

        # Get new max transaction_id for insertion
        new_max_transaction_id = db_execute(db, f"""
            SELECT max(transaction_id) AS max_id 
            FROM transaction_history""")[0]["max_id"]

        if new_max_transaction_id:
            transaction_id = new_max_transaction_id + 1
        else:
            transaction_id = 1

        # Get current time
        timestamp = datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S:%f')

        # Insert new row into database
        rows = db.execute(f"""
          INSERT INTO transaction_history (
              transaction_id
            , transaction_type
            , user_id, total
            , ticker_symbol
            , timestamp
            , quantity
            , price )
          VALUES (
              {transaction_id}
              , 'sell'
              , {user_id}
              , {trade_cost}
              , '{ticker_symbol}'
              , '{timestamp}'
              , {quantity}
              , {price})
          """)

        # Update user balance
        rows = db_execute(db, f""" 
          "UPDATE users
          "SET cash = cash - {trade_cost} - 5"
          "WHERE id = '{user_id}'""")

        quantity_p = quantity * -1

        flash(f"{quantity_p} shares of {ticker_symbol} sold at ${price} a share !")

    if request.method == "GET":

        stocks = db_execute(db, f"""
            SELECT ticker_symbol 
            FROM transaction_history 
            WHERE user_id = {user_id}
            GROUP BY user_id
                   , ticker_symbol 
            HAVING SUM(quantity) > 0""")

        print(stocks)

        return render_template("sell.html", stocks=stocks)

    return render_template("sell.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
