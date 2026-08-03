import os
import uuid
import random
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc, func
import bcrypt
import requests

app = Flask(__name__)
app.secret_key = 'your-super-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(100), unique=True, nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'))
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    target_amount = db.Column(db.Float, nullable=False)
    deadline = db.Column(db.DateTime, nullable=False)
    dowry_date = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

class Contributor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    token = db.Column(db.String(100), unique=True, nullable=False)
    pin = db.Column(db.String(4), nullable=False, default='0000')
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    pledge_amount = db.Column(db.Float, nullable=False)
    paid_amount = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='pending')
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contributor_id = db.Column(db.Integer, db.ForeignKey('contributor.id'))
    amount = db.Column(db.Float, nullable=False)
    date_paid = db.Column(db.DateTime, default=datetime.utcnow)
    note = db.Column(db.String(200))

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    sender_name = db.Column(db.String(150), nullable=False)
    sender_type = db.Column(db.String(20), default='contributor')
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

def is_admin_logged_in():
    return session.get('admin_id') is not None

def get_admin():
    if not is_admin_logged_in():
        return None
    return Admin.query.get(session['admin_id'])

def generate_unique_token():
    return str(uuid.uuid4())[:12]

def generate_pin():
    return f"{random.randint(1000, 9999)}"

def hash_password(plain):
    return bcrypt.hashpw(plain.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(plain, hashed):
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))

def get_event_logo(event_title, size=120):
    name = event_title.replace('Dowry', '').replace('dowry', '').strip()
    if not name:
        name = event_title
    return f"https://ui-avatars.com/api/?name={name.replace(' ', '+')}&size={size}&rounded=true&bold=true&background=random&color=fff&font-size=0.5"

AT_USERNAME = "your_username"
AT_API_KEY = "your_api_key"

def send_sms(phone, message):
    url = "https://api.africastalking.com/version1/messaging"
    headers = {"apiKey": AT_API_KEY, "Content-Type": "application/x-www-form-urlencoded"}
    data = {"username": AT_USERNAME, "to": phone, "message": message}
    try:
        r = requests.post(url, data=data, headers=headers, timeout=10)
        return r.json()
    except Exception as e:
        print(f"SMS Error: {e}")
        return None

def calculate_pace(contributor):
    event = Event.query.get(contributor.event_id)
    if not event:
        return 0, 0, 0, 0
    remaining = max(0, contributor.pledge_amount - contributor.paid_amount)
    now = datetime.utcnow()
    if now > event.dowry_date:
        days_left = 0
    else:
        days_left = max(1, (event.dowry_date - now).days)
    per_day = round(remaining / days_left, 2) if days_left > 0 else 0
    per_week = round(per_day * 7, 2)
    return remaining, days_left, per_day, per_week

@app.route('/register', methods=['GET', 'POST'])
def register():
    if Admin.query.count() > 0:
        flash('Registration is closed.', 'danger')
        return redirect(url_for('login'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        phone = request.form.get('phone', '')
        if Admin.query.filter_by(username=username).first():
            flash('Username taken.', 'danger')
        else:
            hashed = hash_password(password)
            admin = Admin(username=username, password_hash=hashed, email=email, phone=phone)
            db.session.add(admin)
            db.session.commit()
            flash('Admin created! Please login.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password(password, admin.password_hash):
            session['admin_id'] = admin.id
            flash('Logged in.', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def home():
    if is_admin_logged_in():
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('login'))

@app.route('/admin')
def admin_dashboard():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    events = Event.query.filter_by(admin_id=admin.id).order_by(desc(Event.created_at)).all()
    for ev in events:
        ev.logo = get_event_logo(ev.title, 60)
    return render_template('admin_dashboard.html', admin=admin, events=events, get_logo=get_event_logo)

@app.route('/admin/create', methods=['GET', 'POST'])
def admin_create_event():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        target = float(request.form['target_amount'])
        deadline_str = request.form['deadline']
        dowry_date_str = request.form['dowry_date']
        deadline = datetime.strptime(deadline_str, '%Y-%m-%d')
        dowry_date = datetime.strptime(dowry_date_str, '%Y-%m-%d')
        token = generate_unique_token()
        event = Event(
            token=token, admin_id=admin.id, title=title, description=description,
            target_amount=target, deadline=deadline, dowry_date=dowry_date
        )
        db.session.add(event)
        db.session.commit()
        flash(f'✅ "{title}" created!', 'success')
        return redirect(url_for('admin_view_event', event_id=event.id))
    return render_template('admin_create.html')

@app.route('/admin/event/<int:event_id>')
def admin_view_event(event_id):
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    event = Event.query.filter_by(id=event_id, admin_id=admin.id).first_or_404()
    contributors = Contributor.query.filter_by(event_id=event.id).order_by(Contributor.created_at).all()
    total_paid = db.session.query(func.sum(Contributor.paid_amount)).filter_by(event_id=event.id).scalar() or 0
    total_pledged = db.session.query(func.sum(Contributor.pledge_amount)).filter_by(event_id=event.id).scalar() or 0
    pending_count = Contributor.query.filter_by(event_id=event.id, status='pending').count()
    messages = ChatMessage.query.filter_by(event_id=event.id).order_by(ChatMessage.timestamp).all()
    logo = get_event_logo(event.title, 100)
    return render_template('admin_event.html',
                         admin=admin, event=event, contributors=contributors,
                         total_paid=total_paid, total_pledged=total_pledged,
                         pending_count=pending_count, messages=messages,
                         calculate_pace=calculate_pace, logo=logo, get_logo=get_event_logo)

@app.route('/admin/update_contributor/<int:contrib_id>', methods=['POST'])
def admin_update_contributor(contrib_id):
    if not is_admin_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401
    contrib = Contributor.query.get_or_404(contrib_id)
    event = Event.query.get(contrib.event_id)
    action = request.form.get('action')

    if action == 'approve':
        contrib.status = 'approved'
        db.session.commit()
        msg = f"Hello {contrib.name}, your pledge of KES {contrib.pledge_amount} for {event.title} is APPROVED! Your PIN: {contrib.pin}"
        send_sms(contrib.phone, msg)
        flash(f'{contrib.name} approved.', 'success')

    elif action == 'decline':
        contrib.status = 'declined'
        db.session.commit()
        msg = f"Hi {contrib.name}, your pledge was declined. Contact admin."
        send_sms(contrib.phone, msg)
        flash(f'{contrib.name} declined.', 'warning')

    elif action == 'add_payment':
        amount = float(request.form.get('amount', 0))
        if amount > 0:
            contrib.paid_amount += amount
            if contrib.paid_amount >= contrib.pledge_amount:
                contrib.status = 'completed'
                contrib.completed_at = datetime.utcnow()
            elif contrib.status == 'pending':
                contrib.status = 'approved'
            db.session.commit()
            payment = Payment(contributor_id=contrib.id, amount=amount, note=request.form.get('note', ''))
            db.session.add(payment)
            db.session.commit()

            remaining, days_left, per_day, per_week = calculate_pace(contrib)
            pace_msg = f"Remaining: KES {remaining}. To finish by {event.dowry_date.strftime('%d %b')}, pay KES {per_day} daily or KES {per_week} weekly."
            msg = f"✅ Payment of KES {amount} received. Total paid: KES {contrib.paid_amount}. {pace_msg}"
            send_sms(contrib.phone, msg)

            admin = get_admin()
            if admin and admin.phone:
                send_sms(admin.phone, f"{contrib.name} paid KES {amount} for {event.title}.")
            flash(f'Added KES {amount} to {contrib.name}.', 'success')

    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/admin/send_link_sms/<int:event_id>', methods=['POST'])
def admin_send_link_sms(event_id):
    if not is_admin_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401
    event = Event.query.get_or_404(event_id)
    phone = request.form.get('phone')
    if not phone:
        flash('Phone number required.', 'danger')
        return redirect(request.referrer)
    link = f"{request.host_url}e/{event.token}"
    message = f"Hello! You are invited to contribute to {event.title}. Use this link: {link}"
    send_sms(phone, message)
    flash(f'✅ SMS sent to {phone}.', 'success')
    return redirect(request.referrer)

@app.route('/e/<token>')
def public_event(token):
    event = Event.query.filter_by(token=token, is_active=True).first_or_404()
    contributors = Contributor.query.filter_by(event_id=event.id, status='approved').order_by(Contributor.paid_amount.desc()).all()
    messages = ChatMessage.query.filter_by(event_id=event.id).order_by(ChatMessage.timestamp).all()
    logo = get_event_logo(event.title, 80)
    return render_template('public_event.html', event=event, contributors=contributors,
                         messages=messages, calculate_pace=calculate_pace, logo=logo)

@app.route('/api/pledge/<token>', methods=['POST'])
def public_pledge(token):
    event = Event.query.filter_by(token=token, is_active=True).first_or_404()
    if datetime.utcnow() > event.deadline:
        return jsonify({'error': 'Contribution deadline passed'}), 400

    name = request.form.get('name')
    phone = request.form.get('phone')
    pledge_amount = float(request.form.get('amount', 0))
    if not name or not phone or pledge_amount <= 0:
        return jsonify({'error': 'Invalid data'}), 400

    existing = Contributor.query.filter_by(event_id=event.id, phone=phone).first()
    if existing:
        return jsonify({'error': 'Phone already registered.'}), 400

    contrib_token = generate_unique_token()
    pin = generate_pin()
    while Contributor.query.filter_by(event_id=event.id, pin=pin).first():
        pin = generate_pin()

    contrib = Contributor(
        event_id=event.id, token=contrib_token, pin=pin, name=name, phone=phone,
        pledge_amount=pledge_amount, status='pending'
    )
    db.session.add(contrib)
    db.session.commit()

    admin = Admin.query.get(event.admin_id)
    if admin and admin.phone:
        send_sms(admin.phone, f"🔔 New pledge: {name} pledged KES {pledge_amount} for {event.title}.")

    receipt_link = f"{request.host_url}receipt/{contrib_token}"
    msg = f"Hi {name}, your pledge of KES {pledge_amount} for {event.title} is pending. Your PIN: {pin}. Receipt link (active after full payment): {receipt_link}"
    send_sms(phone, msg)

    return jsonify({'success': 'Pledge submitted! Check SMS for your PIN and receipt link.'})

@app.route('/api/chat/<int:event_id>', methods=['GET', 'POST'])
def chat_api(event_id):
    event = Event.query.get_or_404(event_id)
    if request.method == 'POST':
        data = request.get_json()
        sender_name = data.get('sender_name')
        sender_type = data.get('sender_type', 'contributor')
        message = data.get('message')
        if not sender_name or not message:
            return jsonify({'error': 'Missing fields'}), 400
        chat = ChatMessage(event_id=event.id, sender_name=sender_name, sender_type=sender_type, message=message)
        db.session.add(chat)
        db.session.commit()
        return jsonify({'success': 'Message sent'})

    messages = ChatMessage.query.filter_by(event_id=event.id).order_by(desc(ChatMessage.timestamp)).limit(100).all()
    messages.reverse()
    return jsonify([{
        'sender_name': m.sender_name,
        'sender_type': m.sender_type,
        'message': m.message,
        'timestamp': m.timestamp.strftime('%H:%M')
    } for m in messages])

@app.route('/receipt/<token>')
def view_receipt(token):
    contrib = Contributor.query.filter_by(token=token).first_or_404()
    event = Event.query.get(contrib.event_id)
    if contrib.paid_amount < contrib.pledge_amount:
        flash('Receipt available only after full payment.', 'warning')
        return redirect(url_for('public_event', token=event.token))
    payments = Payment.query.filter_by(contributor_id=contrib.id).all()
    logo = get_event_logo(event.title, 60)
    return render_template('receipt.html', contrib=contrib, event=event, payments=payments, now=datetime.utcnow(), logo=logo)

@app.route('/admin/receipt/<int:contrib_id>')
def admin_receipt_download(contrib_id):
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    contrib = Contributor.query.get_or_404(contrib_id)
    return redirect(url_for('view_receipt', token=contrib.token))

if __name__ == '__main__':
    app.run(debug=True)
