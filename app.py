-2,90 +2,96 @@ import os,sqlite3,datetime,io
from flask import Flask,g,render_template_string,request,redirect,url_for,session,send_file
from werkzeug.security import generate_password_hash,check_password_hash
from ics import Calendar,Event
from dotenv import load_dotenv;load_dotenv()

TEMPLATES={
'login':'''<h2>Login</h2><form method=post>Email <input name=email><br>
Password <input name=password type=password><br><button>OK</button></form>''',
'physio':'<h2>Assign</h2><form method=post action=/assign>\
<select name=patient_id>{%for p in patients%}<option value={{p[0]}}>{{p[1]}}</option>{%endfor%}</select>\
<select name=exercise_id>{%for e in exercises%}<option value={{e[0]}}>{{e[1]}}</option>{%endfor%}</select>\
<input type=date name=date required><input type=time name=time required><button>Assign</button></form>',
'patient':'<h2>Today</h2><table border><tr><th>When</th><th>Exercise</th><th></th></tr>\
{%for i in items%}<tr><td>{{i[2]}}</td><td>{{i[1]}}</td><td>\
{%if not i[3]%}<form method=post action=/done/{{i[0]}}><button>✔</button></form>{%endif%}</td></tr>{%endfor%}</table>\
<a href=/calendar.ics>Calendar</a>'}

BASE=os.path.abspath(os.path.dirname(__file__));DB=os.getenv("DB","app.db")
app=Flask(__name__);app.secret_key=os.getenv("SECRET_KEY","dev")

def db():
    if 'd' not in g:
        g.d=sqlite3.connect(DB);g.d.row_factory=sqlite3.Row
    return g.d
@app.teardown_appcontext
def _c(e): g.pop('d',None) and g.d.close()
def _c(e):
    d = g.pop('d', None)
    if d:
        d.close()

@app.before_first_request
def init():
    with open('schema.sql') as f: db().executescript(f.read())
    if not db().execute('select 1 from users').fetchone():
        db().execute("insert into users(email,password_hash,role)values(?,?,?)",
                     ("physio@example.com",generate_password_hash("secret"),"physio"))
        db().execute("insert into exercises(name)values(?)",("Cat-Camel",));db().commit()

def tpl(name,**c): return render_template_string(TEMPLATES[name],**c,session=session)

@app.route('/')
def root(): return redirect('/dash') if session.get('uid') else redirect('/login')

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        u=db().execute('select * from users where email=?',(request.form['email'],)).fetchone()
        if u and check_password_hash(u['password_hash'],request.form['password']):
            session.update(uid=u['id'],role=u['role'])
            return redirect('/dash')
    return tpl('login')

@app.route('/logout');logout=lambda:(session.clear(),redirect('/login'))[1]
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/dash')
def dash(): return redirect('/physio') if session['role']=='physio' else redirect('/patient')

@app.route('/physio'); 
@app.route('/physio')
def physio():
    p=db().execute("select id,email from users where role='patient'").fetchall()
    e=db().execute("select * from exercises").fetchall()
    return tpl('physio',patients=p,exercises=e)

@app.post('/assign');
@app.post('/assign')
def assign():
    dt=datetime.datetime.strptime(f"{request.form['date']} {request.form['time']}",'%Y-%m-%d %H:%M')
    db().execute("insert into schedule(patient_id,exercise_id,scheduled_at) values(?,?,?)",
                 (request.form['patient_id'],request.form['exercise_id'],dt));db().commit()
    return redirect('/physio')

@app.route('/patient');
@app.route('/patient')
def patient():
    today=datetime.date.today()
    t0,t1=datetime.datetime.combine(today,datetime.time.min),datetime.datetime.combine(today,datetime.time.max)
    it=db().execute("""select s.id,e.name,s.scheduled_at,s.completed from schedule s
                       join exercises e on e.id=s.exercise_id where patient_id=? and
                       scheduled_at between ? and ?""",(session['uid'],t0,t1)).fetchall()
    return tpl('patient',items=it)

@app.post('/done/<int:id>');
@app.post('/done/<int:id>')
def done(id):
    db().execute("update schedule set completed=1 where id=?", (id,));db().commit()
    return redirect('/patient')

@app.route('/calendar.ics');
@app.route('/calendar.ics')
def ics():
    cal=Calendar();cur=db().execute("""select e.name,s.scheduled_at from schedule s
                                        join exercises e on e.id=s.exercise_id
                                        where patient_id=?""",(session['uid'],))
    for n,t in cur: ev=Event();ev.name=n;ev.begin=t;cal.events.add(ev)
    return send_file(io.BytesIO(str(cal).encode()),mimetype='text/calendar',
                     download_name='exercises.ics')
if __name__=='__main__': app.run()
