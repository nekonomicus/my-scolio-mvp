import os
import sqlite3
import datetime
import io
import logging # Added for more explicit logging configuration
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
app.secret_key = os.getenv("SECRET_KEY", "a_default_dev_secret_key_longer_and_more_random") # Made default key a bit better

# Configure logging
# Gunicorn typically handles logging, but this ensures Flask's logger is also active.
if not app.debug: # Only configure this if not in debug mode (Gunicorn will set debug=False)
    app.logger.setLevel(logging.INFO)
    # You can add handlers here if needed, but Render should capture stdout/stderr
    # For example, to ensure logs go to stdout for Render to pick up:
    # stream_handler = logging.StreamHandler()
    # stream_handler.setLevel(logging.INFO)
    # app.logger.addHandler(stream_handler)

app.logger.info("Flask application initialized.")


# --- HTML Templates ---
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
        form { background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); max-width: 400px; margin: 40px auto; }
        input[type="email"], input[type="password"] { width: calc(100% - 22px); padding: 10px; margin-bottom: 10px; border: 1px solid #ddd; border-radius: 4px; }
        button { background-color: #007bff; color: white; padding: 10px 15px; border: none; border-radius: 4px; cursor: pointer; width: 100%; }
        button:hover { background-color: #0056b3; }
        .error { color: red; margin-top: 10px; text-align: center; }
    </style>
</head>
<body>
    <h2>Login</h2>
    <form method="post">
        Email <input name="email" type="email" required><br>
        Password <input name="password" type="password" required><br>
        <button type="submit">Login</button>
        {% if error %}
            <p class="error">{{ error }}</p>
        {% endif %}
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
        .container { max-width: 800px; margin: 20px auto; padding: 20px; background-color: #fff; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        form { background-color: #fff; padding: 20px; margin-bottom:20px; border-radius: 8px; /*box-shadow: 0 0 10px rgba(0,0,0,0.1);*/ }
        select, input[type="date"], input[type="time"] { width: calc(100% - 22px); padding: 10px; margin-bottom: 10px; border: 1px solid #ddd; border-radius: 4px; }
        button { background-color: #28a745; color: white; padding: 10px 15px; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background-color: #1e7e34; }
        a { color: #007bff; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .logout-link { display: block; text-align: right; margin-top: 20px;}
    </style>
</head>
<body>
    <div class="container">
        <h2>Assign Exercise</h2>
        <form method="post" action="{{ url_for('assign') }}">
            Patient: <select name="patient_id">
                {% for p in patients %}
                    <option value="{{ p.id }}">{{ p.email }} ({{p.name or 'N/A'}})</option>
                {% else %}
                    <option value="">No patients found</option>
                {% endfor %}
            </select><br>
            Exercise: <select name="exercise_id">
                {% for e in exercises %}
                    <option value="{{ e.id }}">{{ e.name }}</option>
                {% else %}
                    <option value="">No exercises found</option>
                {% endfor %}
            </select><br>
            Date: <input type="date" name="date" required><br>
            Time: <input type="time" name="time" required><br>
            <button type="submit">Assign</button>
        </form>
        <p class="logout-link"><a href="{{ url_for('logout') }}">Logout ({{ session.get('user_name', 'Physio') }})</a></p>
    </div>
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
        .container { max-width: 800px; margin: 20px auto; padding: 20px; background-color: #fff; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        h2 { color: #333; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 20px; /*background-color: #fff; box-shadow: 0 0 10px rgba(0,0,0,0.1);*/ }
        th, td { padding: 10px; border: 1px solid #ddd; text-align: left; }
        th { background-color: #e9ecef; }
        button { background-color: #17a2b8; color: white; padding: 5px 10px; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background-color: #117a8b; }
        a { color: #007bff; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .completed { text-decoration: line-through; color: #6c757d; }
        .actions { margin-top: 20px; }
        .logout-link { display: block; text-align: right; margin-top: 20px;}
    </style>
</head>
<body>
    <div class="container">
        <h2>Today's Schedule ({{ session.get('user_name', 'Patient') }})</h2>
        <table border="1">
            <thead>
                <tr>
                    <th>When</th>
                    <th>Exercise</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                {% for item in items %}
                <tr>
                    <td class="{{ 'completed' if item.completed else '' }}">{{ item.scheduled_at.strftime('%I:%M %p') if item.scheduled_at else 'N/A' }}</td>
                    <td class="{{ 'completed' if item.completed else '' }}">{{ item.name }}</td>
                    <td>
                        {% if not item.completed %}
                            <form method="post" action="{{ url_for('done', id=item.id) }}" style="margin:0; padding:0; box-shadow:none; background:none; display:inline;">
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
            </tbody>
        </table>
        <div class="actions">
            <a href="{{ url_for('ics') }}">Download Calendar (ICS)</a>
        </div>
        <p class="logout-link"><a href="{{ url_for('logout') }}">Logout</a></p>
    </div>
</body>
</html>'''
}

# --- Database Functions ---
def get_db():
    if 'db_conn' not in g:
        app.logger.debug(f"Connecting to database: {DATABASE_FILE}")
        g.db_conn = sqlite3.connect(DATABASE_FILE)
        g.db_conn.row_factory = sqlite3.Row
    return g.db_conn

@app.teardown_appcontext
def close_db(error):
    db_conn = g.pop('db_conn', None)
    if db_conn is not None:
        app.logger.debug("Closing database connection.")
        db_conn.close()
    if error:
        app.logger.error(f"Teardown appcontext error: {error}")


@app.before_request
def init_db_and_user():
    if not hasattr(app, '_database_initialized'):
        app.logger.info("Attempting database initialization (once per app instance)...")
        db = get_db()
        schema_path = os.path.join(BASE_DIR, 'schema.sql')
        try:
            app.logger.info(f"Looking for schema at: {schema_path}")
            if not os.path.exists(schema_path):
                app.logger.error(f"CRITICAL: schema.sql not found at {schema_path}. Database cannot be initialized.")
            else:
                with open(schema_path, 'r') as f:
                    db.executescript(f.read())
                app.logger.info("Database schema executed.")

                # Create default Physio User
                cursor = db.execute('SELECT id FROM users WHERE email = ?', ("physio@example.com",))
                if cursor.fetchone() is None:
                    app.logger.info("Default physio user not found, creating...")
                    db.execute("INSERT INTO users (email, password_hash, role, name) VALUES (?, ?, ?, ?)",
                                 ("physio@example.com", generate_password_hash("secret"), "physio", "Dr. Physio"))
                    db.commit()
                    app.logger.info("Default physio user created.")
                else:
                    app.logger.info("Default physio user already exists.")

                # Create default Patient User <<-- ADDED THIS SECTION -->>
                cursor = db.execute('SELECT id FROM users WHERE email = ?', ("patient@example.com",))
                if cursor.fetchone() is None:
                    app.logger.info("Default patient user not found, creating...")
                    db.execute("INSERT INTO users (email, password_hash, role, name) VALUES (?, ?, ?, ?)",
                                 ("patient@example.com", generate_password_hash("secret"), "patient", "Pat Patient"))
                    db.commit()
                    app.logger.info("Default patient user created.")
                else:
                    app.logger.info("Default patient user already exists.")
                # <<-- END OF ADDED SECTION -->>

                # Create default Exercise
                cursor = db.execute('SELECT id FROM exercises WHERE name = ?', ("Cat-Camel",))
                if cursor.fetchone() is None:
                    app.logger.info("Default exercise 'Cat-Camel' not found, creating...")
                    db.execute("INSERT INTO exercises (name) VALUES (?)", ("Cat-Camel",))
                    db.commit()
                    app.logger.info("Default exercise 'Cat-Camel' created.")
                else:
                    app.logger.info("Default exercise 'Cat-Camel' already exists.")
            
            app._database_initialized = True
            app.logger.info("Database initialization process completed.")
        except sqlite3.Error as e:
            app.logger.error(f"SQLite error during database initialization: {e}")
        except FileNotFoundError:
            app.logger.error(f"CRITICAL: schema.sql file not found at {schema_path} during open().")
        except Exception as e:
            app.logger.error(f"An unexpected error occurred during database initialization: {e}")


# --- Helper Functions ---
def render_custom_template(template_name, **context):
    context['session'] = session
    return render_template_string(TEMPLATES[template_name], **context)

# --- Routes ---
@app.route('/')
def root():
    if session.get('uid'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login_route'))

@app.route('/login', methods=['GET', 'POST'])
def login_route():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        app.logger.info(f"Login attempt for email: {email}")
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()

        if user:
            app.logger.info(f"User found: {user['email']}, role: {user['role']}")
            if check_password_hash(user['password_hash'], password):
                session['uid'] = user['id']
                session['role'] = user['role']
                session['user_name'] = user['name']
                app.logger.info(f"Login successful for {email}. Role: {user['role']}. Redirecting to dashboard.")
                return redirect(url_for('dashboard'))
            else:
                app.logger.warning(f"Password mismatch for user: {email}")
                return render_custom_template('login', error="Invalid email or password.")
        else:
            app.logger.warning(f"No user found with email: {email}")
            return render_custom_template('login', error="Invalid email or password.")
    return render_custom_template('login')

@app.route('/logout')
def logout():
    user_name = session.get('user_name', 'User')
    session.clear()
    app.logger.info(f"{user_name} logged out.")
    return redirect(url_for('login_route'))

@app.route('/dashboard')
def dashboard():
    if not session.get('uid'):
        app.logger.warning("Dashboard access attempt without UID in session. Redirecting to login.")
        return redirect(url_for('login_route'))
    
    role = session.get('role')
    app.logger.info(f"Accessing dashboard for UID {session.get('uid')}, Role: {role}")
    if role == 'physio':
        return redirect(url_for('physio_dashboard'))
    elif role == 'patient':
        return redirect(url_for('patient_dashboard'))
    else:
        app.logger.error(f"Invalid or missing role ('{role}') for UID {session.get('uid')}. Clearing session and redirecting to login.")
        session.clear()
        return redirect(url_for('login_route'))


@app.route('/physio')
def physio_dashboard():
    if not session.get('uid') or session.get('role') != 'physio':
        app.logger.warning("Unauthorized access attempt to physio dashboard.")
        return redirect(url_for('login_route'))
    
    app.logger.info(f"Physio dashboard accessed by UID {session.get('uid')}")
    db = get_db()
    patients = db.execute("SELECT id, email, name FROM users WHERE role = 'patient'").fetchall()
    exercises = db.execute("SELECT id, name FROM exercises").fetchall()
    app.logger.info(f"Found {len(patients)} patients and {len(exercises)} exercises for physio dashboard.")
    return render_custom_template('physio', patients=patients, exercises=exercises)

@app.route('/assign', methods=['POST'])
def assign():
    if not session.get('uid') or session.get('role') != 'physio':
        app.logger.warning("Unauthorized assignment attempt.")
        return redirect(url_for('login_route'))

    patient_id = request.form['patient_id']
    exercise_id = request.form['exercise_id']
    date_str = request.form['date']
    time_str = request.form['time']
    app.logger.info(f"Assigning exercise {exercise_id} to patient {patient_id} for {date_str} {time_str}")
    
    try:
        scheduled_at_dt = datetime.datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M')
    except ValueError:
        app.logger.error(f"Invalid date/time format for assignment: {date_str} {time_str}")
        # Consider adding a flash message here for the user
        return redirect(url_for('physio_dashboard'))

    db = get_db()
    try:
        db.execute("INSERT INTO schedule (patient_id, exercise_id, scheduled_at) VALUES (?, ?, ?)",
                     (patient_id, exercise_id, scheduled_at_dt))
        db.commit()
        app.logger.info("Exercise assigned successfully.")
    except sqlite3.Error as e:
        app.logger.error(f"Database error on assign: {e}")
    return redirect(url_for('physio_dashboard'))

@app.route('/patient')
def patient_dashboard():
    if not session.get('uid') or session.get('role') != 'patient':
        app.logger.warning("Unauthorized access attempt to patient dashboard.")
        return redirect(url_for('login_route'))

    app.logger.info(f"Patient dashboard accessed by UID {session.get('uid')}")
    db = get_db()
    today = datetime.date.today()
    start_of_today = datetime.datetime.combine(today, datetime.time.min)
    end_of_today = datetime.datetime.combine(today, datetime.time.max)

    items = db.execute("""
        SELECT s.id, e.name, s.scheduled_at, s.completed 
        FROM schedule s
        JOIN exercises e ON e.id = s.exercise_id 
        WHERE s.patient_id = ? AND s.scheduled_at BETWEEN ? AND ?
        ORDER BY s.scheduled_at ASC
    """, (session['uid'], start_of_today, end_of_today)).fetchall()
    
    processed_items = []
    for item_row in items:
        item_dict = dict(item_row) 
        if isinstance(item_dict['scheduled_at'], str):
            try:
                item_dict['scheduled_at'] = datetime.datetime.fromisoformat(item_dict['scheduled_at'])
            except ValueError:
                app.logger.error(f"Could not parse scheduled_at string: {item_dict['scheduled_at']}")
                pass 
        processed_items.append(item_dict)
    
    app.logger.info(f"Found {len(processed_items)} items for patient UID {session.get('uid')} for today.")
    return render_custom_template('patient', items=processed_items)

@app.route('/done/<int:id>', methods=['POST'])
def done(id):
    if not session.get('uid') or session.get('role') != 'patient':
        app.logger.warning("Unauthorized 'done' action attempt.")
        return redirect(url_for('login_route'))

    app.logger.info(f"Marking schedule item {id} as done for UID {session.get('uid')}")
    db = get_db()
    try:
        db.execute("UPDATE schedule SET completed = 1 WHERE id = ? AND patient_id = ?", (id, session['uid']))
        db.commit()
        app.logger.info(f"Schedule item {id} marked as done.")
    except sqlite3.Error as e:
        app.logger.error(f"Database error on done action: {e}")
    return redirect(url_for('patient_dashboard'))

@app.route('/calendar.ics')
def ics():
    if not session.get('uid') or session.get('role') != 'patient':
        app.logger.warning("Unauthorized ICS download attempt.")
        return redirect(url_for('login_route'))

    app.logger.info(f"Generating ICS calendar for UID {session.get('uid')}")
    cal = Calendar()
    db = get_db()
    cursor = db.execute("""
        SELECT e.name, s.scheduled_at 
        FROM schedule s
        JOIN exercises e ON e.id = s.exercise_id
        WHERE s.patient_id = ? AND s.completed = 0 
    """, (session['uid'],))

    for row in cursor:
        event_name = row['name']
        begin_time_val = row['scheduled_at']
        
        if isinstance(begin_time_val, str):
            try:
                begin_time = datetime.datetime.fromisoformat(begin_time_val)
            except ValueError:
                app.logger.error(f"Could not parse scheduled_at string for ICS event: {begin_time_val}")
                continue 
        elif isinstance(begin_time_val, (datetime.datetime, datetime.date)):
             begin_time = begin_time_val
        else:
            app.logger.error(f"Unexpected type for scheduled_at in ICS: {type(begin_time_val)}")
            continue

        ev = Event()
        ev.name = event_name
        ev.begin = begin_time
        ev.duration = datetime.timedelta(minutes=30) 
        cal.events.add(ev)
    
    app.logger.info(f"Generated ICS with {len(cal.events)} events.")
    ics_data = io.BytesIO(str(cal).encode('utf-8'))
    return send_file(
        ics_data,
        mimetype='text/calendar',
        as_attachment=True,
        download_name='exercises.ics'
    )

# --- Main Execution ---
if __name__ == '__main__':
    app.logger.info("Starting Flask app in development mode (direct execution).")
    if not os.path.exists(DATABASE_FILE):
        print(f"Development: Database file {DATABASE_FILE} not found. Initializing...")
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            schema_path = os.path.join(BASE_DIR, 'schema.sql')
            with open(schema_path, 'r') as f:
                conn.executescript(f.read())
            # Default Physio
            conn.execute("INSERT INTO users (email, password_hash, role, name) VALUES (?, ?, ?, ?)",
                         ("physio@example.com", generate_password_hash("secret"), "physio", "Dr. Physio"))
            # Default Patient
            conn.execute("INSERT INTO users (email, password_hash, role, name) VALUES (?, ?, ?, ?)",
                         ("patient@example.com", generate_password_hash("secret"), "patient", "Pat Patient"))
            # Default Exercise
            conn.execute("INSERT INTO exercises (name) VALUES (?)", ("Cat-Camel",))
            conn.commit()
            print("Development: Database initialized with default physio, a test patient, and exercise.")
        except Exception as e:
            print(f"Development: Error initializing database locally: {e}")
        finally:
            if conn:
                conn.close()

    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5001)), debug=True)

