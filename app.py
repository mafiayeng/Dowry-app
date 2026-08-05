import os
import uuid
import random
import string
import io
import zipfile
import secrets
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc, func, inspect
import bcrypt
import requests
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'pL3x9QmW8vN2kR5yTzH7bJ4dF6sA1cX0')

database_url = os.environ.get('DATABASE_URL')
if database_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    print("✅ Using PostgreSQL database.")
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
    print("⚠️ DATABASE_URL not set. Using SQLite (data will NOT persist).")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.permanent_session_lifetime = timedelta(days=30)
db = SQLAlchemy(app)

# ---------- CONFIG ----------
SERVICE_FEE_PERCENTAGE = float(os.environ.get('SERVICE_FEE_PERCENTAGE', 2.0))
SUPPORT_WHATSAPP = os.environ.get('SUPPORT_WHATSAPP', '254737349468')
SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL', 'support@goldenvow.com')

# ---------- EMAIL / SMS ----------
def send_email_notification(subject, message, to=None):
    print(f"[EMAIL DISABLED] To: {to} | Subject: {subject} | Message: {message}")
    return True

def send_sms(phone, message):
    print(f"[SMS DISABLED] Phone: {phone} | Message: {message}")
    return True

# ---------- MODELS ----------
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    is_super_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    referral_code = db.Column(db.String(20), unique=True, nullable=False, default='')
    referred_by = db.Column(db.String(20), db.ForeignKey('admin.referral_code'), nullable=True)
    referral_count = db.Column(db.Integer, default=0)
    bonus_earned = db.Column(db.Float, default=0.0)
    last_login = db.Column(db.DateTime, nullable=True)
    last_action = db.Column(db.DateTime, nullable=True)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(100), unique=True, nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'))
    event_type = db.Column(db.String(50), nullable=False, default='dowry')
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    target_amount = db.Column(db.Float, nullable=False)
    deadline = db.Column(db.DateTime, nullable=False)
    event_date = db.Column(db.DateTime, nullable=False)
    picture_url = db.Column(db.String(500))
    background_image_url = db.Column(db.String(500), nullable=True)
    paybill = db.Column(db.String(50))
    mpesa_number = db.Column(db.String(20))
    till_number = db.Column(db.String(50))
    bank_name = db.Column(db.String(100))
    bank_account_name = db.Column(db.String(100))
    bank_account_number = db.Column(db.String(50))
    payment_instructions = db.Column(db.Text)
    whatsapp_contact = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    first_contribution_date = db.Column(db.DateTime, nullable=True)
    fee_paid = db.Column(db.Boolean, default=False)
    fee_paid_date = db.Column(db.DateTime, nullable=True)
    grace_period = db.Column(db.Integer, default=0)
    has_grace_period = db.Column(db.Boolean, default=False)
    ended_at = db.Column(db.DateTime, nullable=True)
    thank_you_message = db.Column(db.Text, nullable=True)
    super_admin_message = db.Column(db.Text, nullable=True)
    disabled = db.Column(db.Boolean, default=False)
    disabled_reason = db.Column(db.Text, nullable=True)

class Contributor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    token = db.Column(db.String(100), unique=True, nullable=False)
    pin = db.Column(db.String(4), nullable=False, default='0000')
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    pledge_amount = db.Column(db.Float, nullable=False)
    fee_amount = db.Column(db.Float, default=0.0)
    net_contribution = db.Column(db.Float, default=0.0)
    paid_amount = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='pending')
    payment_proof_screenshot = db.Column(db.String(500))
    payment_proof_text = db.Column(db.Text)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_weekly_receipt = db.Column(db.DateTime, nullable=True)

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

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'))
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=True)
    contributor_id = db.Column(db.Integer, db.ForeignKey('contributor.id'), nullable=True)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), default='info')
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Testimonial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    contributor_id = db.Column(db.Integer, db.ForeignKey('contributor.id'))
    rating = db.Column(db.Integer, default=0)
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Withdrawal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'))
    amount = db.Column(db.Float, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    method = db.Column(db.String(20), default='mpesa')
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)

class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PasswordReset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'))
    token = db.Column(db.String(100), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)

# ---------- CREATE TABLES & SAFE MIGRATION ----------
with app.app_context():
    db.create_all()
    if not Setting.query.filter_by(key='maintenance_mode').first():
        setting = Setting(key='maintenance_mode', value='False')
        db.session.add(setting)
        db.session.commit()
        print("✅ Maintenance setting created.")

    try:
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('event')]
        needed = {
            'background_image_url': 'VARCHAR(500)',
            'grace_period': 'INTEGER',
            'has_grace_period': 'BOOLEAN',
            'ended_at': 'TIMESTAMP WITHOUT TIME ZONE',
            'thank_you_message': 'TEXT',
            'super_admin_message': 'TEXT',
            'disabled': 'BOOLEAN',
            'disabled_reason': 'TEXT'
        }
        with db.engine.connect() as conn:
            for col_name, col_type in needed.items():
                if col_name not in columns:
                    conn.execute(f'ALTER TABLE event ADD COLUMN {col_name} {col_type}')
                    print(f"✅ Added column '{col_name}' to Event table.")
            conn.commit()
    except Exception as e:
        print(f"⚠️ Migration warning: {e}")

# ---------- HELPERS ----------
def is_admin_logged_in():
    return session.get('admin_id') is not None

def get_admin():
    if not is_admin_logged_in():
        return None
    return Admin.query.get(session['admin_id'])

def is_super_admin():
    admin = get_admin()
    return admin and admin.is_super_admin

def generate_unique_token():
    return str(uuid.uuid4())[:12]

def generate_pin():
    return f"{random.randint(1000, 9999)}"

def generate_referral_code():
    prefix = 'GV'
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{prefix}-{suffix}"

def hash_password(plain):
    return bcrypt.hashpw(plain.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(plain, hashed):
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))

def create_notification(admin_id, message, type='info', event_id=None, contributor_id=None):
    notif = Notification(admin_id=admin_id, event_id=event_id, contributor_id=contributor_id, message=message, type=type)
    db.session.add(notif)
    db.session.commit()

def get_unread_notifications(admin_id):
    return Notification.query.filter_by(admin_id=admin_id, is_read=False).count()

# ---------- DAILY NOTES ----------
DAILY_NOTES = {
    'dowry': ["A journey of love begins with a single step...", "Every shilling contributed is a brick...", "Love knows no bounds...", "Two families become one...", "Your kindness today creates memories...", "Together we rise...", "A beautiful future awaits..."],
    'burial': ["In times of sorrow, we find strength...", "A life remembered is a life that lives on...", "We mourn together, we heal together...", "In loving memory of a beautiful soul...", "Grief shared is grief halved...", "Your kindness brings light...", "May their soul rest in peace..."],
    'medical': ["Hope is the best medicine...", "Every contribution is a step toward recovery...", "Strength comes from community...", "Your generosity brings hope...", "Together we fight, together we heal...", "Every shilling brings a smile...", "Healing begins with hope..."],
    'education': ["Every child deserves a chance to dream...", "Education is the most powerful weapon...", "Your generosity today builds a brighter tomorrow...", "Knowledge is the seed of greatness...", "Every shilling contributed is a step...", "The future belongs to those who believe...", "Together we build the leaders of tomorrow..."],
    'harambee': ["When we come together, great things happen...", "Community is the foundation of progress...", "Together we rise...", "We are stronger together...", "Building a better future starts with us...", "United we stand, together we achieve...", "Community is the heart of progress..."],
    'other': ["Great things happen when we come together...", "Every contribution, no matter how small...", "Your kindness creates a ripple...", "Together we make the impossible possible...", "Your support is a beacon of hope...", "Together we achieve more...", "Thank you for your generous heart..."]
}

def get_daily_note(event_type, day):
    notes = DAILY_NOTES.get(event_type, DAILY_NOTES['other'])
    return notes[(day - 1) % len(notes)]

# ---------- EVENT LOGO ----------
EVENT_COLORS = {
    'dowry': {'bg1': '#1A2A3A', 'bg2': '#D4AF37', 'symbol': '🐂', 'ring': '#D4AF37'},
    'burial': {'bg1': '#2C2C2C', 'bg2': '#C0C0C0', 'symbol': '🕊️', 'ring': '#C0C0C0'},
    'medical': {'bg1': '#C62828', 'bg2': '#FFFFFF', 'symbol': '❤️', 'ring': '#C62828'},
    'education': {'bg1': '#1565C0', 'bg2': '#D4AF37', 'symbol': '🎓', 'ring': '#1565C0'},
    'harambee': {'bg1': '#2E7D32', 'bg2': '#D4AF37', 'symbol': '🤝', 'ring': '#2E7D32'},
    'other': {'bg1': '#6A1B9A', 'bg2': '#D4AF37', 'symbol': '✦', 'ring': '#6A1B9A'}
}

def generate_event_logo(event, size=120):
    colors = EVENT_COLORS.get(event.event_type, EVENT_COLORS['other'])
    initials = ''.join([word[0].upper() for word in event.title.split()][:2])
    if not initials:
        initials = event.title[:2].upper()
    svg = f'''<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">
        <circle cx="{size/2}" cy="{size/2}" r="{size/2 - 5}" fill="{colors['bg1']}" />
        <defs><linearGradient id="grad{event.id}" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="{colors['bg1']}" stop-opacity="1" />
            <stop offset="100%" stop-color="{colors['bg2']}" stop-opacity="0.8" />
        </linearGradient></defs>
        <circle cx="{size/2}" cy="{size/2}" r="{size/2 - 15}" stroke="{colors['ring']}" stroke-width="3" fill="none" opacity="0.8"/>
        <circle cx="{size/2}" cy="{size/2}" r="{size/2 - 30}" stroke="{colors['ring']}" stroke-width="2" fill="none" opacity="0.5"/>
        <text x="{size/2}" y="{size/2 - 10}" text-anchor="middle" fill="{colors['ring']}" font-size="{size/3}" font-family="Arial">{colors['symbol']}</text>
        <text x="{size/2}" y="{size/2 + 25}" text-anchor="middle" fill="#FFFFFF" font-family="Georgia, serif" font-size="{size/5}" font-weight="bold">{initials}</text>
        <text x="{size/4}" y="{size/4}" fill="{colors['ring']}" font-size="{size/8}">✦</text>
        <text x="{size*0.75}" y="{size/4}" fill="{colors['ring']}" font-size="{size/8}">✦</text>
    </svg>'''
    return svg

def get_app_logo(size=40):
    svg = f'''<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">
        <circle cx="{size/2}" cy="{size/2}" r="{size/2 - 3}" fill="#1A2A3A" />
        <circle cx="{size/2}" cy="{size/2}" r="{size/2 - 8}" stroke="#D4AF37" stroke-width="2" fill="none" />
        <text x="{size/2}" y="{size/2 + 5}" text-anchor="middle" fill="#D4AF37" font-family="Georgia, serif" font-size="{size/3}" font-weight="bold">GV</text>
        <text x="{size/4}" y="{size/4}" fill="#D4AF37" font-size="{size/8}">✦</text>
        <text x="{size*0.75}" y="{size/4}" fill="#D4AF37" font-size="{size/8}">✦</text>
    </svg>'''
    return svg

# ---------- FEE ----------
def get_fee_percentage(admin_id):
    admin = Admin.query.get(admin_id)
    if not admin:
        return SERVICE_FEE_PERCENTAGE
    count = admin.referral_count
    if count >= 10:
        return 1.2
    elif count >= 5:
        return 1.4
    elif count >= 3:
        return 1.6
    elif count >= 1:
        return 1.8
    else:
        return 2.0

def calculate_fee(amount, admin_id=None):
    if admin_id:
        fee_percentage = get_fee_percentage(admin_id)
    else:
        fee_percentage = SERVICE_FEE_PERCENTAGE
    fee = round(amount * (fee_percentage / 100), 2)
    if fee < 1:
        fee = 1
    return fee

def get_event_total_contributions(event_id):
    return db.session.query(func.sum(Contributor.pledge_amount)).filter_by(event_id=event_id, status='approved').scalar() or 0

def get_event_total_fee(event_id):
    return db.session.query(func.sum(Contributor.fee_amount)).filter_by(event_id=event_id, status='approved').scalar() or 0

def get_event_total_paid(event_id):
    return db.session.query(func.sum(Contributor.paid_amount)).filter_by(event_id=event_id).scalar() or 0

def get_fee_due(event_id):
    total = get_event_total_contributions(event_id)
    event = Event.query.get(event_id)
    return calculate_fee(total, event.admin_id if event else None)

def is_fee_overdue(event):
    if not event.first_contribution_date:
        return False
    if event.fee_paid:
        return False
    due_date = event.first_contribution_date + timedelta(days=3)
    if datetime.utcnow() > due_date:
        grace_end = due_date + timedelta(hours=1)
        if datetime.utcnow() > grace_end:
            return True
    return False

def get_page_lock_status(event):
    if event.disabled:
        return True
    if not event.first_contribution_date:
        return False
    if event.fee_paid:
        return False
    if is_fee_overdue(event):
        return True
    return False

# ---------- CONTEXT PROCESSORS ----------
@app.context_processor
def utility_processor():
    return dict(
        app_logo=get_app_logo(),
        get_app_logo=get_app_logo,
        get_fee_percentage=get_fee_percentage,
        get_event_total_contributions=get_event_total_contributions,
        get_page_lock_status=get_page_lock_status,
        generate_event_logo=generate_event_logo,
        get_unread_notifications=get_unread_notifications,
        is_admin_logged_in=is_admin_logged_in,
        get_admin=get_admin,
        support_whatsapp=SUPPORT_WHATSAPP,
        support_email=SUPPORT_EMAIL,
        fee_percentage=SERVICE_FEE_PERCENTAGE,
        now=datetime.utcnow
    )

# ---------- MAINTENANCE FILTER ----------
@app.before_request
def check_maintenance():
    if request.endpoint in ['static', 'force_maintenance_off', 'run_migration']:
        return
    if is_admin_logged_in() and get_admin().is_super_admin:
        return
    setting = Setting.query.filter_by(key='maintenance_mode').first()
    if setting and setting.value == 'True':
        allowed = ['login', 'register', 'maintenance', 'event_landing', 'contact', 'forgot_password', 'reset_password']
        if request.endpoint not in allowed:
            return render_template('maintenance.html'), 503

# ---------- ROUTES ----------
@app.route('/force_maintenance_off')
def force_maintenance_off():
    secret = request.args.get('secret')
    if secret != 'c4eB9xQmW8vN2kR5yTzH7bJ4dF6sA1cX0':
        return "Unauthorized", 401
    setting = Setting.query.filter_by(key='maintenance_mode').first()
    if setting:
        setting.value = 'False'
        db.session.commit()
    return "✅ Maintenance mode has been forced OFF. The app is now accessible."

@app.route('/run-migration')
def run_migration():
    secret = request.args.get('secret')
    if secret != 'c4eB9xQmW8vN2kR5yTzH7bJ4dF6sA1cX0':
        return "Unauthorized", 401
    from sqlalchemy import inspect
    with app.app_context():
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('event')]
        needed = {
            'background_image_url': 'VARCHAR(500)',
            'grace_period': 'INTEGER',
            'has_grace_period': 'BOOLEAN',
            'ended_at': 'TIMESTAMP WITHOUT TIME ZONE',
            'thank_you_message': 'TEXT',
            'super_admin_message': 'TEXT',
            'disabled': 'BOOLEAN',
            'disabled_reason': 'TEXT'
        }
        added = []
        for col, typ in needed.items():
            if col not in columns:
                db.engine.execute(f'ALTER TABLE event ADD COLUMN {col} {typ}')
                added.append(col)
        if added:
            return f"✅ Added columns: {', '.join(added)}"
        else:
            return "✅ All columns already exist. No changes made."

@app.route('/maintenance')
def maintenance():
    return render_template('maintenance.html'), 503

@app.route('/register', methods=['GET', 'POST'])
def register():
    event_token = request.args.get('event_token')
    event = None
    if event_token:
        event = Event.query.filter_by(token=event_token).first()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        phone = request.form.get('phone', '')
        if Admin.query.filter_by(username=username).first():
            flash('⚠️ Username already taken.', 'danger')
            return redirect(url_for('register', event_token=event_token))
        if Admin.query.filter_by(email=email).first():
            flash('⚠️ Email already registered.', 'danger')
            return redirect(url_for('register', event_token=event_token))
        if phone and Admin.query.filter_by(phone=phone).first():
            flash('⚠️ Phone number already registered.', 'danger')
            return redirect(url_for('register', event_token=event_token))
        hashed = hash_password(password)
        is_super = Admin.query.count() == 0
        admin = Admin(username=username, password_hash=hashed, email=email, phone=phone, is_super_admin=is_super)
        admin.referral_code = generate_referral_code()
        ref = request.args.get('ref')
        if ref:
            referrer = Admin.query.filter_by(referral_code=ref).first()
            if referrer and referrer.id != admin.id:
                admin.referred_by = ref
                referrer.referral_count += 1
                db.session.add(referrer)
        db.session.add(admin)
        db.session.commit()
        flash('✅ Account created! Please login.', 'success')
        if event_token:
            return redirect(url_for('login', event_token=event_token))
        return redirect(url_for('login'))
    return render_template('register.html', event=event)

@app.route('/login', methods=['GET', 'POST'])
def login():
    event_token = request.args.get('event_token')
    event = None
    if event_token:
        event = Event.query.filter_by(token=event_token).first()
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password(password, admin.password_hash):
            session['admin_id'] = admin.id
            session.permanent = True
            admin.last_login = datetime.utcnow()
            admin.last_action = datetime.utcnow()
            db.session.commit()
            flash('Logged in successfully.', 'success')
            if event_token:
                return redirect(url_for('public_event', token=event_token))
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid username or password. Please try again.', 'danger')
            return render_template('login.html', event=event)
    return render_template('login.html', event=event)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def home():
    if is_admin_logged_in():
        return redirect(url_for('admin_dashboard'))
    return render_template('landing.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        admin = Admin.query.filter_by(email=email).first()
        if not admin:
            flash('No account found with that email.', 'danger')
            return redirect(url_for('forgot_password'))
        token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(hours=24)
        reset = PasswordReset(admin_id=admin.id, token=token, expires_at=expires)
        db.session.add(reset)
        db.session.commit()
        reset_link = f"{request.host_url}reset_password?token={token}"
        send_email_notification("Password Reset Request", f"Click this link to reset your password: {reset_link}\n\nThis link expires in 24 hours.", to=admin.email)
        flash('✅ Password reset link sent to your email.', 'success')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    token = request.args.get('token')
    if not token:
        flash('Invalid reset link.', 'danger')
        return redirect(url_for('login'))
    reset = PasswordReset.query.filter_by(token=token, used=False).first()
    if not reset or reset.expires_at < datetime.utcnow():
        flash('Reset link expired or invalid.', 'danger')
        return redirect(url_for('login'))
    if request.method == 'POST':
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', token=token)
        admin = Admin.query.get(reset.admin_id)
        admin.password_hash = hash_password(password)
        reset.used = True
        db.session.commit()
        flash('✅ Password reset successfully. Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html', token=token)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone', '')
        subject = request.form.get('subject')
        message = request.form.get('message')
        if not name or not email or not subject or not message:
            flash('Please fill in all required fields.', 'danger')
            return render_template('contact.html')
        contact = ContactMessage(name=name, email=email, phone=phone, subject=subject, message=message)
        db.session.add(contact)
        db.session.commit()
        super_admin = Admin.query.filter_by(is_super_admin=True).first()
        if super_admin:
            create_notification(super_admin.id, f"📩 New contact message from {name}: {subject}", 'contact')
        flash('✅ Your message has been sent. We will get back to you soon!', 'success')
        return redirect(url_for('contact'))
    return render_template('contact.html')

@app.route('/admin')
def admin_dashboard():
    # ---- SAFETY MIGRATION: Add missing columns if any ----
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('event')]
        needed = {
            'background_image_url': 'VARCHAR(500)',
            'grace_period': 'INTEGER',
            'has_grace_period': 'BOOLEAN',
            'ended_at': 'TIMESTAMP WITHOUT TIME ZONE',
            'thank_you_message': 'TEXT',
            'super_admin_message': 'TEXT',
            'disabled': 'BOOLEAN',
            'disabled_reason': 'TEXT'
        }
        with db.engine.connect() as conn:
            for col, typ in needed.items():
                if col not in columns:
                    conn.execute(f'ALTER TABLE event ADD COLUMN {col} {typ}')
                    print(f"✅ Added column '{col}' on the fly.")
            conn.commit()
    except Exception as e:
        print(f"⚠️ On-the-fly migration failed: {e}")
    # ------------------------------------------------

    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    admin.last_action = datetime.utcnow()
    db.session.commit()
    events = Event.query.filter_by(admin_id=admin.id).order_by(desc(Event.created_at)).all()
    total_contributors = 0
    total_raised = 0
    pending_approvals = 0
    for ev in events:
        total_contributors += Contributor.query.filter_by(event_id=ev.id).count()
        total_raised += get_event_total_paid(ev.id)
        pending_approvals += Contributor.query.filter_by(event_id=ev.id, status='pending').count()
    setting = Setting.query.filter_by(key='maintenance_mode').first()
    maintenance_mode = setting.value == 'True' if setting else False
    return render_template('admin_dashboard.html',
                         admin=admin,
                         events=events,
                         total_contributors=total_contributors,
                         total_raised=total_raised,
                         pending_approvals=pending_approvals,
                         maintenance_mode=maintenance_mode)

@app.route('/admin/create', methods=['GET', 'POST'])
def admin_create_event():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    if admin.is_super_admin:
        flash('Super Admin cannot create events.', 'danger')
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        title = request.form['title']
        existing = Event.query.filter_by(title=title).first()
        if existing:
            flash('An event with this name already exists.', 'danger')
            return render_template('admin_create.html')
        event_type = request.form['event_type']
        description = request.form.get('description', '')
        target_amount = float(request.form['target_amount'])
        deadline_str = request.form['deadline']
        event_date_str = request.form['event_date']
        paybill = request.form.get('paybill', '')
        mpesa_number = request.form.get('mpesa_number', '')
        till_number = request.form.get('till_number', '')
        bank_name = request.form.get('bank_name', '')
        bank_account_name = request.form.get('bank_account_name', '')
        bank_account_number = request.form.get('bank_account_number', '')
        payment_instructions = request.form.get('payment_instructions', '')
        whatsapp_contact = request.form.get('whatsapp_contact', '')
        picture_url = request.form.get('picture_url', '')
        background_image_url = request.form.get('background_image_url', '')
        grace_period = int(request.form.get('grace_period', 0))
        super_admin_message = request.form.get('super_admin_message', '')
        deadline = datetime.strptime(deadline_str, '%Y-%m-%d')
        event_date = datetime.strptime(event_date_str, '%Y-%m-%d')
        token = generate_unique_token()
        event = Event(
            token=token, admin_id=admin.id, event_type=event_type, title=title,
            description=description, target_amount=target_amount, deadline=deadline,
            event_date=event_date, picture_url=picture_url, background_image_url=background_image_url,
            paybill=paybill, mpesa_number=mpesa_number, till_number=till_number,
            bank_name=bank_name, bank_account_name=bank_account_name, bank_account_number=bank_account_number,
            payment_instructions=payment_instructions, whatsapp_contact=whatsapp_contact,
            grace_period=grace_period, has_grace_period=grace_period > 0,
            super_admin_message=super_admin_message
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
    admin.last_action = datetime.utcnow()
    db.session.commit()
    event = Event.query.filter_by(id=event_id, admin_id=admin.id).first_or_404()
    if event.disabled:
        flash('This event has been disabled by the Super Admin.', 'warning')
    contributors = Contributor.query.filter_by(event_id=event.id).order_by(Contributor.created_at).all()
    total_contributions = get_event_total_contributions(event.id)
    total_fees = get_event_total_fee(event.id)
    total_paid = get_event_total_paid(event.id)
    pending_count = Contributor.query.filter_by(event_id=event.id, status='pending').count()
    fee_due = get_fee_due(event.id)
    is_locked = get_page_lock_status(event)
    messages = ChatMessage.query.filter_by(event_id=event.id).order_by(ChatMessage.timestamp).all()
    logo_svg = generate_event_logo(event, 100)
    return render_template('admin_event.html',
                         admin=admin, event=event, contributors=contributors,
                         total_contributions=total_contributions,
                         total_fees=total_fees, total_paid=total_paid,
                         pending_count=pending_count, fee_due=fee_due,
                         is_locked=is_locked, messages=messages,
                         logo_svg=logo_svg)

@app.route('/admin/update_contributor/<int:contrib_id>', methods=['POST'])
def admin_update_contributor(contrib_id):
    if not is_admin_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401
    admin = get_admin()
    admin.last_action = datetime.utcnow()
    db.session.commit()
    contrib = Contributor.query.get_or_404(contrib_id)
    event = Event.query.get(contrib.event_id)
    action = request.form.get('action')
    if action == 'approve':
        contrib.status = 'approved'
        db.session.commit()
        create_notification(event.admin_id, f"✅ {contrib.name}'s payment approved.", 'success', event.id, contrib.id)
        flash(f'{contrib.name} approved.', 'success')
    elif action == 'decline':
        contrib.status = 'declined'
        db.session.commit()
        create_notification(event.admin_id, f"❌ {contrib.name}'s payment declined.", 'danger', event.id, contrib.id)
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
            if not event.first_contribution_date:
                event.first_contribution_date = datetime.utcnow()
                db.session.commit()
            create_notification(event.admin_id, f"💰 Payment of KES {amount} added for {contrib.name}.", 'info', event.id, contrib.id)
            flash(f'Added KES {amount} to {contrib.name}.', 'success')
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/admin/mark_fee_paid/<int:event_id>', methods=['POST'])
def admin_mark_fee_paid(event_id):
    if not is_admin_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401
    event = Event.query.get_or_404(event_id)
    event.fee_paid = True
    event.fee_paid_date = datetime.utcnow()
    db.session.commit()
    flash('✅ Fee marked as paid. Event unlocked.', 'success')
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/admin/generate_early_receipt/<int:event_id>', methods=['POST'])
def admin_generate_early_receipt(event_id):
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    event = Event.query.filter_by(id=event_id, admin_id=admin.id).first_or_404()
    contributor_id = request.form.get('contributor_id')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    if not contributor_id or not start_date or not end_date:
        flash('Please fill in all fields.', 'danger')
        return redirect(request.referrer)
    contrib = Contributor.query.get_or_404(contributor_id)
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    payments = Payment.query.filter(Payment.contributor_id == contrib.id, Payment.date_paid >= start, Payment.date_paid <= end).all()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    c.setFillColorRGB(1,1,1); c.rect(0,0,width,height,fill=1)
    c.setStrokeColorRGB(0.83,0.69,0.22); c.setLineWidth(3); c.rect(40,40,width-80,height-80)
    c.setFillColorRGB(0.83,0.69,0.22); c.setFont("Helvetica-Bold", 24); c.drawString(200, height-80, "✦ GOLDENVOW ✦")
    c.setFillColorRGB(0.2,0.2,0.2); c.setFont("Helvetica", 12); c.drawString(220, height-100, "Tunza Mila · Nurture Tradition")
    c.setFillColorRGB(0,0,0); c.setFont("Helvetica-Bold", 18); c.drawString(50, height-150, event.title)
    c.setFont("Helvetica", 12); c.drawString(50, height-190, f"Contributor: {contrib.name}")
    c.drawString(50, height-210, f"Phone: {contrib.phone}")
    c.drawString(50, height-230, f"Date Range: {start.strftime('%d %b %Y')} - {end.strftime('%d %b %Y')}")
    c.line(50, height-250, width-50, height-250)
    c.setFont("Helvetica-Bold", 14); c.drawString(50, height-280, "Payment History")
    y = height-310; c.setFont("Helvetica", 10)
    for p in payments:
        c.drawString(50, y, f"{p.date_paid.strftime('%d %b %Y, %H:%M')} - KES {p.amount}"); y -= 20
    if not payments: c.drawString(50, y, "No payments in this period.")
    y = 70
    c.setFillColorRGB(0.83,0.69,0.22); c.setFont("Helvetica-Oblique", 12); c.drawString(50, y+30, '"Thank you for being part of this journey."')
    c.setFillColorRGB(0.2,0.2,0.2); c.setFont("Helvetica-Bold", 10); c.drawString(50, y+10, "GoldenVow · Tunza Mila")
    c.setFillColorRGB(0.5,0.5,0.5); c.setFont("Helvetica", 8); c.drawString(50, y-10, event.super_admin_message or "Sincerely thankful from the Super Admin.")
    c.drawString(50, y-25, "© 2026 GoldenVow · All rights reserved.")
    c.save()
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                     download_name=f"Receipt_{contrib.name}_{start.strftime('%d%m%Y')}_{end.strftime('%d%m%Y')}.pdf")

@app.route('/admin/download_all_receipts/<int:event_id>')
def admin_download_all_receipts(event_id):
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    event = Event.query.filter_by(id=event_id, admin_id=admin.id).first_or_404()
    contributors = Contributor.query.filter_by(event_id=event.id, status='approved').all()
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zf:
        for c in contributors:
            pdf_buffer = io.BytesIO()
            p = canvas.Canvas(pdf_buffer, pagesize=A4)
            p.drawString(100, 800, "GoldenVow Receipt")
            p.drawString(100, 780, f"Event: {event.title}")
            p.drawString(100, 760, f"Contributor: {c.name}")
            p.drawString(100, 740, f"Amount: KES {c.paid_amount}")
            p.drawString(100, 720, f"Date: {datetime.utcnow().strftime('%d %b %Y')}")
            p.save()
            pdf_buffer.seek(0)
            zf.writestr(f"{c.name}_receipt.pdf", pdf_buffer.read())
    zip_buffer.seek(0)
    return send_file(zip_buffer, mimetype='application/zip', as_attachment=True,
                     download_name=f"{event.title}_all_receipts.zip")

@app.route('/notifications')
def view_notifications():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    notifications = Notification.query.filter_by(admin_id=admin.id).order_by(desc(Notification.created_at)).all()
    Notification.query.filter_by(admin_id=admin.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return render_template('notifications.html', admin=admin, notifications=notifications)

# ---------- PUBLIC ----------
@app.route('/e/<token>')
def public_event(token):
    event = Event.query.filter_by(token=token, is_active=True).first_or_404()
    if event.disabled:
        return render_template('event_disabled.html', event=event)
    if not is_admin_logged_in():
        return redirect(url_for('event_landing', token=token))
    admin = get_admin()
    admin.last_action = datetime.utcnow()
    db.session.commit()
    contributors = Contributor.query.filter_by(event_id=event.id).order_by(Contributor.created_at).all()
    messages = ChatMessage.query.filter_by(event_id=event.id).order_by(ChatMessage.timestamp).all()
    day = (datetime.utcnow() - event.created_at).days + 1
    daily_note = get_daily_note(event.event_type, day)
    is_locked = get_page_lock_status(event)
    logo_svg = generate_event_logo(event, 80)
    contributor = None
    can_download_weekly = False
    next_available = None
    weekly_total = 0
    contrib = Contributor.query.filter_by(event_id=event.id, phone=admin.phone).first()
    if contrib:
        contributor = contrib
        if contributor.last_weekly_receipt:
            next_available = contributor.last_weekly_receipt + timedelta(days=7)
            if datetime.utcnow() >= next_available:
                can_download_weekly = True
        else:
            can_download_weekly = True
            next_available = datetime.utcnow() + timedelta(days=7)
        week_ago = datetime.utcnow() - timedelta(days=7)
        payments = Payment.query.filter(Payment.contributor_id == contrib.id, Payment.date_paid >= week_ago).all()
        weekly_total = sum(p.amount for p in payments)
    total_raised = get_event_total_paid(event.id)
    return render_template('public_event.html',
                         event=event, contributors=contributors, messages=messages,
                         daily_note=daily_note, is_locked=is_locked,
                         logo_svg=logo_svg,
                         contributor=contributor,
                         can_download_weekly=can_download_weekly,
                         next_available_date=next_available,
                         weekly_total=weekly_total,
                         total_raised=total_raised)

@app.route('/join/<token>')
def event_landing(token):
    event = Event.query.filter_by(token=token, is_active=True).first_or_404()
    if event.disabled:
        return render_template('event_disabled.html', event=event)
    logo_svg = generate_event_logo(event, 80)
    return render_template('event_landing.html', event=event, logo_svg=logo_svg)

@app.route('/api/pledge/<token>', methods=['POST'])
def api_pledge(token):
    if not is_admin_logged_in():
        return jsonify({'error': 'Please login to pledge.'}), 401
    event = Event.query.filter_by(token=token, is_active=True).first_or_404()
    if event.disabled:
        return jsonify({'error': 'This event has been disabled.'}), 400
    if is_fee_overdue(event):
        return jsonify({'error': 'This event is locked. Contact organizer.'}), 400
    deadline_extended = event.deadline + timedelta(days=event.grace_period if event.has_grace_period else 0)
    if datetime.utcnow() > deadline_extended:
        return jsonify({'error': 'Deadline passed.'}), 400
    name = request.form.get('name')
    phone = request.form.get('phone')
    amount = float(request.form.get('amount', 0))
    if not name or not phone or amount <= 0:
        return jsonify({'error': 'Fill all fields.'}), 400
    MINIMUM_PLEDGE = 50
    if amount < MINIMUM_PLEDGE:
        return jsonify({'error': f'Minimum pledge is KES {MINIMUM_PLEDGE}.'}), 400
    existing = Contributor.query.filter_by(event_id=event.id, phone=phone).first()
    if existing:
        return jsonify({'error': 'Phone already registered.'}), 400
    fee = calculate_fee(amount, event.admin_id)
    net = amount - fee
    contrib_token = generate_unique_token()
    pin = generate_pin()
    while Contributor.query.filter_by(event_id=event.id, pin=pin).first():
        pin = generate_pin()
    contrib = Contributor(
        event_id=event.id, token=contrib_token, pin=pin, name=name, phone=phone,
        pledge_amount=amount, fee_amount=fee, net_contribution=net,
        paid_amount=0.0, status='pending'
    )
    db.session.add(contrib)
    db.session.commit()
    if not event.first_contribution_date:
        event.first_contribution_date = datetime.utcnow()
        db.session.commit()
    create_notification(event.admin_id, f"🔔 New pledge: {name} pledged KES {amount}.", 'pledge', event.id, contrib.id)
    return jsonify({'success': f'Pledge submitted! Net: KES {net}. PIN: {pin}', 'pin': pin})

@app.route('/api/submit_proof/<token>', methods=['POST'])
def api_submit_proof(token):
    if not is_admin_logged_in():
        return jsonify({'error': 'Please login.'}), 401
    contrib = Contributor.query.filter_by(token=token).first_or_404()
    event = Event.query.get(contrib.event_id)
    screenshot = request.form.get('screenshot_url', '')
    proof_text = request.form.get('proof_text', '')
    if not proof_text and not screenshot:
        return jsonify({'error': 'Provide proof.'}), 400
    contrib.payment_proof_screenshot = screenshot
    contrib.payment_proof_text = proof_text
    contrib.paid_amount = contrib.pledge_amount
    contrib.status = 'approved'
    db.session.commit()
    create_notification(event.admin_id, f"✅ Payment from {contrib.name} auto-confirmed!", 'success', event.id, contrib.id)
    return jsonify({'success': 'Payment confirmed! Thank you for your support. 🙏'})

@app.route('/api/chat/<int:event_id>', methods=['GET', 'POST'])
def api_chat(event_id):
    event = Event.query.get_or_404(event_id)
    if request.method == 'POST':
        if not is_admin_logged_in():
            return jsonify({'error': 'Please login to chat.'}), 401
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
        'timestamp': m.timestamp.strftime('%H:%M'),
        'date': m.timestamp.strftime('%b %d')
    } for m in messages])

@app.route('/receipt/weekly/<token>')
def weekly_receipt(token):
    contrib = Contributor.query.filter_by(token=token).first_or_404()
    event = Event.query.get(contrib.event_id)
    if contrib.last_weekly_receipt:
        next_available = contrib.last_weekly_receipt + timedelta(days=7)
        if datetime.utcnow() < next_available:
            flash(f'Your next weekly receipt available on {next_available.strftime("%d %b %Y")}.', 'warning')
            return redirect(url_for('public_event', token=event.token))
    week_ago = datetime.utcnow() - timedelta(days=7)
    payments = Payment.query.filter(Payment.contributor_id == contrib.id, Payment.date_paid >= week_ago).all()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    c.setFillColorRGB(1,1,1); c.rect(0,0,width,height,fill=1)
    c.setStrokeColorRGB(0.83,0.69,0.22); c.setLineWidth(3); c.rect(40,40,width-80,height-80)
    c.setFillColorRGB(0.83,0.69,0.22); c.setFont("Helvetica-Bold", 24); c.drawString(200, height-80, "✦ GOLDENVOW ✦")
    c.setFillColorRGB(0.2,0.2,0.2); c.setFont("Helvetica", 12); c.drawString(220, height-100, "Tunza Mila · Nurture Tradition")
    c.setFillColorRGB(0,0,0); c.setFont("Helvetica-Bold", 18); c.drawString(50, height-150, event.title)
    c.setFont("Helvetica", 12); c.drawString(50, height-190, f"Contributor: {contrib.name}")
    c.drawString(50, height-210, f"Phone: {contrib.phone}")
    c.drawString(50, height-230, f"Week Ending: {datetime.utcnow().strftime('%d %b %Y')}")
    c.line(50, height-250, width-50, height-250)
    c.setFont("Helvetica-Bold", 14); c.drawString(50, height-280, "Weekly Summary")
    c.setFont("Helvetica", 12); c.drawString(50, height-310, f"Total Pledged: KES {contrib.pledge_amount}")
    c.drawString(50, height-330, f"Total Paid: KES {contrib.paid_amount}")
    weekly_sum = sum(p.amount for p in payments)
    c.drawString(50, height-350, f"Weekly Total: KES {weekly_sum}")
    c.line(50, height-370, width-50, height-370)
    c.setFont("Helvetica-Bold", 14); c.drawString(50, height-400, "Payment History")
    y = height-430; c.setFont("Helvetica", 10)
    for p in payments:
        c.drawString(50, y, f"{p.date_paid.strftime('%d %b %Y, %H:%M')} - KES {p.amount}"); y -= 20
    if not payments: c.drawString(50, y, "No payments this week.")
    y = 70
    c.setFillColorRGB(0.83,0.69,0.22); c.setFont("Helvetica-Oblique", 12); c.drawString(50, y+30, '"Thank you for being part of this journey."')
    c.setFillColorRGB(0.2,0.2,0.2); c.setFont("Helvetica-Bold", 10); c.drawString(50, y+10, "GoldenVow · Tunza Mila")
    c.setFillColorRGB(0.5,0.5,0.5); c.setFont("Helvetica", 8); c.drawString(50, y-10, event.super_admin_message or "Sincerely thankful from the Super Admin.")
    c.drawString(50, y-25, "© 2026 GoldenVow · All rights reserved.")
    c.save()
    buffer.seek(0)
    contrib.last_weekly_receipt = datetime.utcnow()
    db.session.commit()
    return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                     download_name=f"GoldenVow_Weekly_Receipt_{contrib.name}.pdf")

@app.route('/about')
def about():
    return render_template('about.html')

# ---------- PENDING CHECK ----------
@app.route('/check-pending')
def check_pending():
    secret = request.args.get('secret')
    if secret != os.environ.get('CRON_SECRET', 'c4eB9xQmW8vN2kR5yTzH7bJ4dF6sA1cX0'):
        return "Unauthorized", 401
    cutoff = datetime.utcnow() - timedelta(hours=12)
    pending = Contributor.query.filter(Contributor.status == 'pending', Contributor.created_at <= cutoff).all()
    admin_pending = {}
    for c in pending:
        event = Event.query.get(c.event_id)
        if event:
            admin_id = event.admin_id
            admin_pending.setdefault(admin_id, []).append(c)
    for admin_id, contributors in admin_pending.items():
        admin = Admin.query.get(admin_id)
        if not admin:
            continue
        last_reminder = Notification.query.filter_by(admin_id=admin_id, type='pending_reminder').order_by(desc(Notification.created_at)).first()
        if last_reminder and (datetime.utcnow() - last_reminder.created_at).total_seconds() < 21600:
            continue
        count = len(contributors)
        msg = f"⏰ You have {count} pending approval{'s' if count>1 else ''} older than 12 hours."
        create_notification(admin_id, msg, 'pending_reminder')
        send_email_notification("Pending Approvals Reminder", f"Dear {admin.username},\n\n{msg}\n\nLogin: {request.host_url}admin", admin.email)
    inactive_cutoff = datetime.utcnow() - timedelta(hours=24)
    inactive = Admin.query.filter(Admin.last_action < inactive_cutoff, Admin.is_super_admin == False).all()
    if inactive:
        super_admin = Admin.query.filter_by(is_super_admin=True).first()
        if super_admin:
            last_notify = Notification.query.filter_by(admin_id=super_admin.id, type='inactivity_alert').order_by(desc(Notification.created_at)).first()
            if not last_notify or (datetime.utcnow() - last_notify.created_at).total_seconds() >= 21600:
                names = [a.username for a in inactive]
                msg = f"📞 Inactive admins (>24h): {', '.join(names)}"
                create_notification(super_admin.id, msg, 'inactivity_alert')
                send_email_notification("Inactive Admins Alert", msg, super_admin.email)
    return "OK", 200

# ---------- SUPER ADMIN ----------
@app.route('/superadmin')
def super_admin_dashboard():
    if not is_admin_logged_in():
        return redirect(url_for('login'))
    admin = get_admin()
    if not admin.is_super_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('admin_dashboard'))
    all_admins = Admin.query.filter_by(is_super_admin=False).all()
    all_events = Event.query.order_by(desc(Event.created_at)).all()
    contact_messages = ContactMessage.query.order_by(desc(ContactMessage.created_at)).all()
    total_events = len(all_events)
    total_contributors = Contributor.query.count()
    total_contributions = db.session.query(func.sum(Contributor.pledge_amount)).scalar() or 0
    total_fees = db.session.query(func.sum(Contributor.fee_amount)).scalar() or 0
    withdrawals = Withdrawal.query.order_by(desc(Withdrawal.created_at)).all()
    setting = Setting.query.filter_by(key='maintenance_mode').first()
    maintenance_mode = setting.value == 'True' if setting else False
    return render_template('super_admin.html',
                         admin=admin, admins=all_admins, all_events=all_events,
                         total_events=total_events, total_contributors=total_contributors,
                         total_contributions=total_contributions, total_fees=total_fees,
                         maintenance_mode=maintenance_mode,
                         withdrawals=withdrawals, contact_messages=contact_messages)

@app.route('/superadmin/remove_admin/<int:admin_id>', methods=['POST'])
def superadmin_remove_admin(admin_id):
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        return redirect(url_for('login'))
    admin = get_admin()
    if admin.id == admin_id:
        flash('Cannot remove yourself.', 'danger')
        return redirect(url_for('super_admin_dashboard'))
    target = Admin.query.get_or_404(admin_id)
    if target.is_super_admin:
        flash('Cannot remove another Super Admin.', 'danger')
        return redirect(url_for('super_admin_dashboard'))
    for ev in Event.query.filter_by(admin_id=target.id).all():
        Contributor.query.filter_by(event_id=ev.id).delete()
        ChatMessage.query.filter_by(event_id=ev.id).delete()
        db.session.delete(ev)
    db.session.delete(target)
    db.session.commit()
    flash(f'✅ Admin "{target.username}" removed.', 'success')
    return redirect(url_for('super_admin_dashboard'))

@app.route('/superadmin/toggle_maintenance', methods=['POST'])
def toggle_maintenance():
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('login'))
    setting = Setting.query.filter_by(key='maintenance_mode').first()
    current = setting.value == 'True'
    setting.value = str(not current)
    db.session.commit()
    status = "ON" if setting.value == 'True' else "OFF"
    flash(f'🔧 Maintenance mode is now {status}.', 'success')
    return redirect(url_for('super_admin_dashboard'))

@app.route('/superadmin/withdrawal/<int:withdrawal_id>', methods=['POST'])
def superadmin_withdrawal_action(withdrawal_id):
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        return redirect(url_for('login'))
    withdrawal = Withdrawal.query.get_or_404(withdrawal_id)
    action = request.form.get('action')
    if action == 'approve':
        withdrawal.status = 'approved'
    elif action == 'reject':
        withdrawal.status = 'rejected'
    elif action == 'paid':
        withdrawal.status = 'paid'
        withdrawal.paid_at = datetime.utcnow()
    db.session.commit()
    flash(f'✅ Withdrawal {action}d.', 'success')
    return redirect(url_for('super_admin_dashboard'))

@app.route('/superadmin/toggle_disable_event/<int:event_id>', methods=['POST'])
def toggle_disable_event(event_id):
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        return redirect(url_for('login'))
    event = Event.query.get_or_404(event_id)
    event.disabled = not event.disabled
    event.disabled_reason = request.form.get('reason', 'Disabled by Super Admin.')
    db.session.commit()
    status = "disabled" if event.disabled else "enabled"
    flash(f'✅ Event "{event.title}" has been {status}.', 'success')
    return redirect(url_for('super_admin_dashboard'))

@app.route('/superadmin/delete_event/<int:event_id>', methods=['POST'])
def superadmin_delete_event(event_id):
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        return redirect(url_for('login'))
    event = Event.query.get_or_404(event_id)
    try:
        ChatMessage.query.filter_by(event_id=event.id).delete()
        Notification.query.filter_by(event_id=event.id).delete()
        contributors = Contributor.query.filter_by(event_id=event.id).all()
        for c in contributors:
            Payment.query.filter_by(contributor_id=c.id).delete()
            db.session.delete(c)
        db.session.delete(event)
        db.session.commit()
        flash(f'✅ Event "{event.title}" and all associated data permanently deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error deleting event: {str(e)}', 'danger')
    return redirect(url_for('super_admin_dashboard'))

@app.route('/superadmin/mark_contact_read/<int:msg_id>', methods=['POST'])
def mark_contact_read(msg_id):
    if not is_admin_logged_in() or not get_admin().is_super_admin:
        return redirect(url_for('login'))
    msg = ContactMessage.query.get_or_404(msg_id)
    msg.is_read = True
    db.session.commit()
    flash('✅ Message marked as read.', 'success')
    return redirect(url_for('super_admin_dashboard'))

# ---------- API ----------
@app.route('/api/notifications/unread')
def api_unread_notifications():
    if not is_admin_logged_in():
        return jsonify({'count': 0, 'latest': None}), 401
    admin = get_admin()
    unread = Notification.query.filter_by(admin_id=admin.id, is_read=False).order_by(desc(Notification.created_at)).all()
    count = len(unread)
    latest = unread[0].message if unread else None
    return jsonify({'count': count, 'latest': latest})

# ---------- RUN ----------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
