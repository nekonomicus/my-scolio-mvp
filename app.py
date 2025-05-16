import os
import sqlite3
import datetime
import io
from flask import Flask, g, render_template_string, request, redirect, url_for, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from ics import Calendar, Event
from dotenv import load_dotenv

# Load environment variables from .env file, if present
load_dotenv()

# --- Application Setup ---
# Define the base directory of the application
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# Define the database file path, defaulting to 'app.db' if DB environment variable is not set
DATABASE_FILE = os.path.join(BASE_DIR, os.getenv("DB", "app.db"))

# Initialize Flask application
app = Flask(__name__)
# Set the secret key for session management, defaulting if not set in environment
app.secret_key = os.getenv("SECRET_KEY", "a_default_dev_secret_key")

# --- HTML Templates ---
# Storing HTML templates directly in the Python file for simplicity in this MVP
TEMPLATES = {
    'login': '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login</title>
    <style>
        body { font-family: sans-serif; margin: 20px; background-color: #f4f4f4; color: #333; }
        h2 { color: #333; }
        form { background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        input[type="email"], input[type="password"] { width: calc(100% - 22px); padding: 10px; margin-bottom: 10px; border: 1px solid #ddd; border-radius: 4px; }
        button { background-color: #007bff; color: white; padding: 10px 15px; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background-color: #0056b3; }
    </style>
</head>
<body>
    <h2>Login</h2>
    <form method="post">
        Email <input name="email" type="email" required><br>
        Password <input name="password" type="password" required><br>
        <button type="submit">Login</button>
    </form>
</body>
</html>''',
    'physio': '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Physio Dashboard</title>
    <style>
        body { font-family: sans-serif; margin: 20px; background-color: #f4f4f4; color: #333; }
        h2 { color: #333; }
        form { background-color: #fff; padding: 20px; margin-bottom:20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        select, input[type="date"], input[type="time"] { width: calc(100% - 22px); padding: 10px; margin-bottom: 10px; border: 1px solid #ddd; border-radius: 4px; }
        button { background-color: #28a745; color: white; padding: 10px 15px; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background-color: #1e7e34; }
        a { color: #007bff; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <h2>Assign Exercise</h2>
    <form method="post" action="{{ url_for('assign') }}">
        Patient: <select name="patient_id">
            {% for p in patients %}
                <option value="{{ p.id }}">{{ p.email }} ({{p.name}})</option>
            {% endfor %}
        </select><br>
        Exercise: <select name="exercise_id">
            {% for e in exercises %}
                <option value="{{ e.id }}">{{ e.name }}</option>
            {% endfor %}
        </select><br>
        Date: <input type="date" name="date" required><br>
        Time: <input type="time" name="time" required><br>
        <button type="submit">Assign</button>
    </form>
    <p><a href="{{ url_for('logout') }}">Logout</a></p>
</body>
</html>''',
    'patient': '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Patient Dashboard</title>
    <style>
        body { font-family: sans-serif; margin: 20px; background-color: #f4f4f4; color: #333; }
        h2 { color: #333; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 20px; background-color: #fff; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        th, td { padding: 10px; border: 1px solid #ddd; text-align: left; }
        th { background-color: #e9ecef; }
        button { background-color: #17a2b8; color: white; padding: 5px 10px; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background-color: #117a8b; }
        a { color: #007bff; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .completed { text-decoration: line-through; color: #6c757d; }
    </style>
</head>
<body>
    <h2>Today's Schedule ({{ session.get('user_name', 'Patient') }})</h2>
    <table border="1">
        <tr>
            <th>When</th>
            <th>Exercise</th>
            <th>Status</th>
        </tr>
        {% for item in items %}
        <tr>
            <td class="{{ 'completed' if item.completed else '' }}">{{ item.scheduled_at.strftime('%I:%M %p') }}</td>
            <td class="{{ 'completed' if item.completed else '' }}">{{ item.name }}</td>
            <td>
                {% if not item.completed %}
                    <form method="post" action="{{ url_for('done', id=item.id) }}" style="margin:0; padding:0; box-shadow:none; background:none;">
                        <button type="submit">✔ Mark as Done</button>
                    </form>
                {% else %}
                    Completed
                {% endif %}
            </td>
        </tr>
        {% endfor %}
        {% if not items %}
        <tr>
            <td colspan="3" style="text-align:center;">No exercises scheduled for today.</td>
        </tr>
        {% endif %}
    </table>
    <p><a href="{{ url_for('ics') }}">Download Calendar (ICS)</a></p>
    <p><a href="{{ url_for('logout') }}">Logout</a></p>
</body>
</html>'''
}

# --- Database Functions ---
def get_db():
    """Opens a new database connection if there is none yet for the current application context."""
    if 'db_conn' not in g:
        g.db_conn = sqlite3.connect(DATABASE_FILE)
        g.db_conn.row_factory = sqlite3.Row  # Access columns by name
    return g.db_conn

@app.teardown_appcontext
def close_db(error):
    """Closes the database again at the end of the request."""
    db_conn = g.pop('db_conn', None)
    if db_conn is not None:
        db_conn.close()

@app.before_request
def init_db_and_user():
    """
    Initializes the database schema and default data if it doesn't exist.
    This function runs before the first request to *this* instance of the app.
    Note: `@app.before_first_request` is deprecated. Using `@app.before_request`
    with a check to ensure it only runs once per application startup if needed,
    or using a CLI command is preferred for robust initialization.
    For simplicity in this MVP and considering Gunicorn's single worker on free Render,
    this approach might appear to work, but a proper CLI command is better.
    Here, we'll just ensure the DB is available for every request.
    """
    # Check if initialization has been done for this app instance to avoid re-running
    if not hasattr(app, '_database_initialized'):
        db = get_db()
        schema_path = os.path.join(BASE_DIR, 'schema.sql')
        try:
            with open(schema_path, 'r') as f:
                db.executescript(f.read())
            
            # Check if default physio user exists, if not, create it
            cursor = db.execute('SELECT id FROM users WHERE email = ?', ("physio@example.com",))
            if cursor.fetchone() is None:
                db.execute("INSERT INTO users (email, password_hash, role, name) VALUES (?, ?, ?, ?)",
                             ("physio@example.com", generate_password_hash("secret"), "physio", "Dr. Physio"))
                db.commit()
            
            # Check if default exercise exists
            cursor = db.execute('SELECT id FROM exercises WHERE name = ?', ("Cat-Camel",))
            if cursor.fetchone() is None:
                db.execute("INSERT INTO exercises (name) VALUES (?)", ("Cat-Camel",))
                db.commit()
            
            app._database_initialized = True # Mark as initialized
        except sqlite3.Error as e:
            app.logger.error(f"Database initialization error: {e}")
        except FileNotFoundError:
            app.logger.error(f"Schema file not found at {schema_path}. Make sure schema.sql is in the same directory as app.py.")


# --- Helper Functions ---
def render_custom_template(template_name, **context):
    """Renders an HTML template from the TEMPLATES dictionary."""
    # Add session to context so it's always available in templates
    context['session'] = session
    return render_template_string(TEMPLATES[template_name], **context)

# --- Routes ---
@app.route('/')
def root():
    """Redirects to dashboard if logged in, otherwise to login page."""
    if session.get('uid'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login_route')) # Changed to avoid conflict with function name

@app.route('/login', methods=['GET', 'POST'])
def login_route(): # Renamed from 'login' to avoid conflict with any 'login' import or variable
    """Handles user login."""
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['uid'] = user['id']
            session['role'] = user['role']
            session['user_name'] = user['name'] # Store user's name for display
            return redirect(url_for('dashboard'))
        else:
            # You might want to add an error message to the template here
            return render_custom_template('login', error="Invalid email or password")
    return render_custom_template('login')

@app.route('/logout')
def logout():
    """Clears the session and redirects to login page."""
    session.clear()
    return redirect(url_for('login_route'))

@app.route('/dashboard')
def dashboard():
    """Redirects to the appropriate dashboard based on user role."""
    if not session.get('uid'):
        return redirect(url_for('login_route'))
    
    if session.get('role') == 'physio':
        return redirect(url_for('physio_dashboard'))
    elif session.get('role') == 'patient':
        return redirect(url_for('patient_dashboard'))
    else:
        # Fallback if role is somehow not set or invalid
        session.clear()
        return redirect(url_for('login_route'))


@app.route('/physio')
def physio_dashboard():
    """Displays the physiotherapist's dashboard."""
    if not session.get('uid') or session.get('role') != 'physio':
        return redirect(url_for('login_route'))
    
    db = get_db()
    patients = db.execute("SELECT id, email, name FROM users WHERE role = 'patient'").fetchall()
    exercises = db.execute("SELECT id, name FROM exercises").fetchall()
    return render_custom_template('physio', patients=patients, exercises=exercises)

@app.route('/assign', methods=['POST'])
def assign():
    """Handles assignment of exercises by a physiotherapist."""
    if not session.get('uid') or session.get('role') != 'physio':
        return redirect(url_for('login_route'))

    patient_id = request.form['patient_id']
    exercise_id = request.form['exercise_id']
    date_str = request.form['date']
    time_str = request.form['time']
    
    try:
        # Combine date and time strings and parse into a datetime object
        scheduled_at_dt = datetime.datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M')
    except ValueError:
        # Handle invalid date/time format, perhaps return an error to the user
        app.logger.error("Invalid date/time format for assignment.")
        return redirect(url_for('physio_dashboard')) # Or show an error message

    db = get_db()
    try:
        db.execute("INSERT INTO schedule (patient_id, exercise_id, scheduled_at) VALUES (?, ?, ?)",
                     (patient_id, exercise_id, scheduled_at_dt))
        db.commit()
    except sqlite3.Error as e:
        app.logger.error(f"Database error on assign: {e}")
        # Handle error, perhaps show a message to the user
    return redirect(url_for('physio_dashboard'))

@app.route('/patient')
def patient_dashboard():
    """Displays the patient's dashboard with today's exercises."""
    if not session.get('uid') or session.get('role') != 'patient':
        return redirect(url_for('login_route'))

    db = get_db()
    today = datetime.date.today()
    # Define the start and end of today for the query
    start_of_today = datetime.datetime.combine(today, datetime.time.min)
    end_of_today = datetime.datetime.combine(today, datetime.time.max)

    items = db.execute("""
        SELECT s.id, e.name, s.scheduled_at, s.completed 
        FROM schedule s
        JOIN exercises e ON e.id = s.exercise_id 
        WHERE s.patient_id = ? AND s.scheduled_at BETWEEN ? AND ?
        ORDER BY s.scheduled_at ASC
    """, (session['uid'], start_of_today, end_of_today)).fetchall()
    
    # Convert scheduled_at strings to datetime objects if they aren't already (though SQLite should handle it)
    # For display, it's often better to format in the template or here if needed.
    # The sqlite3.Row factory should allow access like item['scheduled_at']
    # If they are strings, you might need:
    # processed_items = []
    # for item_row in items:
    # item_dict = dict(item_row) # Convert row to dict
    #     item_dict['scheduled_at'] = datetime.datetime.strptime(item_dict['scheduled_at'], '%Y-%m-%d %H:%M:%S') # Adjust format if needed
    #     processed_items.append(item_dict)
    # items = processed_items

    return render_custom_template('patient', items=items)

@app.route('/done/<int:id>', methods=['POST'])
def done(id):
    """Marks an exercise as completed by the patient."""
    if not session.get('uid') or session.get('role') != 'patient':
        return redirect(url_for('login_route'))

    db = get_db()
    try:
        # Ensure the schedule item belongs to the current patient before updating
        db.execute("UPDATE schedule SET completed = 1 WHERE id = ? AND patient_id = ?", (id, session['uid']))
        db.commit()
    except sqlite3.Error as e:
        app.logger.error(f"Database error on done: {e}")
    return redirect(url_for('patient_dashboard'))

@app.route('/calendar.ics')
def ics():
    """Generates an ICS calendar file for the patient's schedule."""
    if not session.get('uid') or session.get('role') != 'patient':
        return redirect(url_for('login_route'))

    cal = Calendar()
    db = get_db()
    cursor = db.execute("""
        SELECT e.name, s.scheduled_at 
        FROM schedule s
        JOIN exercises e ON e.id = s.exercise_id
        WHERE s.patient_id = ? AND s.completed = 0 
    """, (session['uid'],)) # Only include non-completed items, or all - adjust as needed

    for row in cursor:
        event_name = row['name']
        # Ensure scheduled_at is a datetime object
        if isinstance(row['scheduled_at'], str):
            begin_time = datetime.datetime.strptime(row['scheduled_at'], '%Y-%m-%d %H:%M:%S') # Adjust format if SQLite stores it differently
        else:
            begin_time = row['scheduled_at'] # Assuming it's already a datetime object

        ev = Event()
        ev.name = event_name
        ev.begin = begin_time
        # You might want to set a default duration for events
        ev.duration = datetime.timedelta(minutes=30) 
        cal.events.add(ev)
    
    # Create an in-memory bytes buffer for the ICS file
    ics_data = io.BytesIO(str(cal).encode('utf-8'))
    return send_file(
        ics_data,
        mimetype='text/calendar',
        as_attachment=True, # Use as_attachment=True for modern Flask
        download_name='exercises.ics'
    )

# --- Main Execution ---
if __name__ == '__main__':
    # This block runs only when the script is executed directly (e.g., `python app.py`)
    # It's useful for local development. Gunicorn will not use this.
    # For local dev, ensure schema.sql and app.db are in the same directory or adjust paths.
    
    # One-time DB setup for local dev if app.db doesn't exist.
    # This is a simplified version of init_db_and_user for local startup.
    if not os.path.exists(DATABASE_FILE):
        print(f"Database file {DATABASE_FILE} not found. Initializing...")
        conn = sqlite3.connect(DATABASE_FILE)
        schema_path = os.path.join(BASE_DIR, 'schema.sql')
        try:
            with open(schema_path, 'r') as f:
                conn.executescript(f.read())
            conn.execute("INSERT INTO users (email, password_hash, role, name) VALUES (?, ?, ?, ?)",
                         ("physio@example.com", generate_password_hash("secret"), "physio", "Dr. Physio"))
            conn.execute("INSERT INTO exercises (name) VALUES (?)", ("Cat-Camel",))
            conn.commit()
            print("Database initialized with default data.")
        except Exception as e:
            print(f"Error initializing database locally: {e}")
        finally:
            conn.close()

    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5001)), debug=True)
