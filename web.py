from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
import os
import pytz


app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

def to_local_time(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Assume naive datetime is UTC
        dt = dt.replace(tzinfo=timezone.utc)
    local_tz = datetime.now().astimezone().tzinfo
    return dt.astimezone(local_tz)

# Run database migrations on startup
# with app.app_context():
#     from flask_migrate import upgrade
#     try:
#         upgrade()
#     except Exception as e:
#         print(f"Migration failed: {e}")
#         # Continue anyway, as tables might already exist

# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    first_name = db.Column(db.String(80), nullable=False)
    middle_name = db.Column(db.String(80), nullable=True)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    # Security question for password recovery and hashed answer
    security_question = db.Column(db.String(200), nullable=True)
    security_answer_hash = db.Column(db.String(200), nullable=True)

# Admin model
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    # allow storing contact details for the admin account
    email = db.Column(db.String(120), unique=False, nullable=True)
    phone = db.Column(db.String(50), nullable=True)

# Plot model
class Plot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    block = db.Column(db.String(50), nullable=True)
    row = db.Column(db.String(50), nullable=True)
    number = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(50), nullable=True)
    assigned_to = db.Column(db.String(200), nullable=True)
    reserved_date = db.Column(db.Date, nullable=True)
    square_meter = db.Column(db.String(50), nullable=True)
    price = db.Column(db.Float, nullable=True)


# Reservation model
class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    plot_id = db.Column(db.Integer, db.ForeignKey('plot.id'), nullable=False)
    block = db.Column(db.String(50), nullable=True)
    row = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(50), nullable=False, default='pending')
    reserved_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    price = db.Column(db.Float, nullable=True)
    plot = db.relationship('Plot', backref='reservations')


# Notification model
class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    message = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(50), nullable=True)  # e.g. pending/confirmed/failed
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# Deceased model
class Deceased(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    dob = db.Column(db.Date, nullable=True)
    dod = db.Column(db.Date, nullable=True)
    buried_date = db.Column(db.Date, nullable=True)
    price = db.Column(db.Float, nullable=True)
    age = db.Column(db.Integer, nullable=True)
    square_meter = db.Column(db.String(50), nullable=True)
    plot_id = db.Column(db.Integer, db.ForeignKey('plot.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    plot = db.relationship('Plot', backref='deceased')

# Create tables if not exist
with app.app_context():
    db.create_all()
    # Ensure Plot table contains expected columns (helps when DB was created before model changes)
    try:
        # list of expected columns and their SQL definitions for ALTER TABLE
        expected = {
            'id': 'INTEGER',
            'block': "TEXT",
            'row': "TEXT",
            'number': "TEXT DEFAULT ''",
            'status': "TEXT",
            'assigned_to': "TEXT",
            'reserved_date': "DATE",
            'square_meter': "TEXT",
            'price': "REAL"
        }
        # read existing columns
        inspector = inspect(db.engine)
        existing = set([col['name'] for col in inspector.get_columns('plot')])
        for col, coldef in expected.items():
            if col not in existing:
                try:
                    sql = f"ALTER TABLE plot ADD COLUMN {col} {coldef};"
                    db.session.execute(text(sql))
                    db.session.commit()
                    print(f"Added missing column {col} to plot table")
                except Exception as e:
                    db.session.rollback()
                    print(f"Failed to add column {col}: {e}")
    except Exception as e:
        print('Schema repair check failed:', e)

    # ensure admin table has email and phone columns (if DB was created earlier)
    try:
        inspector = inspect(db.engine)
        admin_existing = set([col['name'] for col in inspector.get_columns('admin')])
        if 'email' not in admin_existing:
            try:
                db.session.execute(text("ALTER TABLE admin ADD COLUMN email TEXT"))
                db.session.commit()
                print('Added admin.email column')
            except Exception:
                db.session.rollback()
        if 'phone' not in admin_existing:
            try:
                db.session.execute(text("ALTER TABLE admin ADD COLUMN phone TEXT"))
                db.session.commit()
                print('Added admin.phone column')
            except Exception:
                db.session.rollback()
    except Exception:
        pass

    # ensure user table has security question/answer columns for migration-less upgrades
    try:
        inspector = inspect(db.engine)
        user_existing = set([col['name'] for col in inspector.get_columns('user')])
        if 'security_question' not in user_existing:
            try:
                db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN security_question TEXT"))
                db.session.commit()
                print('Added user.security_question column')
            except Exception:
                db.session.rollback()
        if 'security_answer_hash' not in user_existing:
            try:
                db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN security_answer_hash TEXT"))
                db.session.commit()
                print('Added user.security_answer_hash column')
            except Exception:
                db.session.rollback()
    except Exception:
        pass

    # Ensure password_hash columns are large enough (Postgres only)
    try:
        if db.engine.dialect.name == 'postgresql':
            try:
                db.session.execute(text('ALTER TABLE "admin" ALTER COLUMN password_hash TYPE VARCHAR(256)'))
                db.session.commit()
                print('Ensured admin.password_hash is VARCHAR(256)')
            except Exception:
                db.session.rollback()
            try:
                db.session.execute(text('ALTER TABLE "user" ALTER COLUMN password_hash TYPE VARCHAR(256)'))
                db.session.commit()
                print('Ensured user.password_hash is VARCHAR(256)')
            except Exception:
                db.session.rollback()
    except Exception:
        pass

    # Create default admin account if not exists
    if not Admin.query.filter_by(username='admin').first():
        default_admin = Admin(
            username='admin',
            password_hash=generate_password_hash('admin123')
        )
        db.session.add(default_admin)
        db.session.commit()

@app.route('/')
def welcome():
    return render_template('welcome.html')

@app.route('/home')
def home():
    username = session.get('username')
    return render_template('home.html', username=username)

@app.route('/search_plot')
def search_plot():
    # expose plot data to the search map page so the SVG rects can be colored by status
    plots = []
    try:
        # For the public map page we always expose all plots so the SVG
        # can render available, reserved and occupied states (admin-marked
        # occupied/reserved should be visible on the map).
        raw = Plot.query.order_by(Plot.id.asc()).all()
        # convert to plain dicts so Jinja's tojson can serialize them
        for p in raw:
            plots.append({
                'id': p.id,
                'block': p.block,
                'row': p.row,
                'number': p.number,
                'status': p.status,
                'assigned_to': p.assigned_to,
                'reserved_date': p.reserved_date.isoformat() if p.reserved_date else '',
                'square_meter': p.square_meter,
                'price': p.price
            })
    except Exception:
        plots = []
    is_logged_in = 'user_id' in session
    return render_template('search_plot.html', plots=plots, is_logged_in=is_logged_in)


@app.route('/api/reserve', methods=['POST'])
def api_reserve():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Not logged in'}), 403
    data = request.get_json() or request.form
    plot_id = data.get('plot_id')
    block = data.get('block')
    row = data.get('row')
    if not plot_id:
        return jsonify({'success': False, 'error': 'Missing plot identifier'}), 400

    price = None
    try:
        p = Plot.query.get(int(plot_id))
        if p:
            price = p.price
            block = block or p.block
            row = row or p.row
    except Exception:
        pass

    try:
        existing = Reservation.query.filter_by(user_id=user_id, plot_id=int(plot_id), status='pending').first()
        if existing:
            return jsonify({'success': False, 'error': 'You already have a pending reservation for this plot', 'already_pending': True, 'reservation_id': existing.id}), 409
        r = Reservation(
            user_id=user_id,
            plot_id=int(plot_id),
            block=block,
            row=row,
            status='pending',
            price=price
        )
        db.session.add(r)
        db.session.commit()

        # Update plot status to reserved
        try:
            plot = Plot.query.get(int(plot_id))
            if plot and plot.status == 'available':
                plot.status = 'reserved'
                db.session.commit()
        except Exception:
            db.session.rollback()

        # create a notification for the user about the pending reservation (use plot number when available)
        try:
            try:
                plot_obj = Plot.query.get(int(plot_id)) if plot_id is not None else None
                plot_label = plot_obj.number if (plot_obj and getattr(plot_obj, 'number', None)) else str(plot_id)
            except Exception:
                plot_label = str(plot_id)
            note = Notification(user_id=user_id, message=f"Your reservation request for plot {plot_label} is pending.", status='pending')
            db.session.add(note)
            db.session.commit()
        except Exception:
            db.session.rollback()

        return jsonify({'success': True, 'reservation': {'id': r.id, 'plot_id': r.plot_id, 'block': r.block, 'row': r.row, 'status': r.status}})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# Admin settings route - view and update admin account info (username, email, phone, password)
@app.route('/admin/settings', methods=['GET', 'POST'])
def admin_settings():
    if not session.get('admin_id'):
        flash('Please log in as admin.', 'danger')
        return redirect(url_for('admin_login'))

    admin = Admin.query.get(session.get('admin_id'))
    if not admin:
        flash('Admin account not found.', 'danger')
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        # basic profile updates
        new_username = (request.form.get('username') or '').strip()
        new_email = (request.form.get('email') or '').strip()
        new_phone = (request.form.get('phone') or '').strip()

        if new_username and new_username != admin.username:
            # ensure uniqueness among admins
            if Admin.query.filter(Admin.username == new_username, Admin.id != admin.id).first():
                flash('Username already taken by another admin.', 'danger')
                return redirect(url_for('admin_settings'))
            admin.username = new_username
            session['admin_username'] = new_username

        admin.email = new_email or None
        admin.phone = new_phone or None

        # handle password change if requested
        current_pw = request.form.get('current_password') or ''
        new_pw = request.form.get('new_password') or ''
        confirm_pw = request.form.get('confirm_password') or ''
        if new_pw or confirm_pw or current_pw:
            # require all three fields
            if not current_pw or not new_pw or not confirm_pw:
                flash('To change password, fill current, new and confirm fields.', 'danger')
                return redirect(url_for('admin_settings'))
            if not check_password_hash(admin.password_hash, current_pw):
                flash('Current password is incorrect.', 'danger')
                return redirect(url_for('admin_settings'))
            if new_pw != confirm_pw:
                flash('New password and confirmation do not match.', 'danger')
                return redirect(url_for('admin_settings'))
            # update password
            admin.password_hash = generate_password_hash(new_pw)

        try:
            db.session.commit()
            flash('Settings updated successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Failed to update settings: {e}', 'danger')

        return redirect(url_for('admin_settings'))

    return render_template('admin/settings.html', admin=admin)


@app.route('/api/admin/reservations')
def api_admin_reservations():
    if not session.get('admin_id'):
        return jsonify({'success': False, 'error': 'Not authorized'}), 403
    res = Reservation.query.order_by(Reservation.reserved_at.desc()).all()
    out = []
    for r in res:
        user = User.query.get(r.user_id)
        plot = Plot.query.get(r.plot_id)
        out.append({
            'id': r.id,
            'user_id': r.user_id,
            'user_name': f"{user.first_name} {user.last_name}" if user else '',
            'plot_id': r.plot_id,
            'block': r.block,
            'row': r.row,
            'plot_number': plot.number if plot else '',
            'status': r.status,
            'price': r.price,
            'reserved_at': to_local_time(r.reserved_at).isoformat()
        })
    return jsonify({'success': True, 'reservations': out})


@app.route('/api/my/reservations')
def api_my_reservations():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Not logged in'}), 403
    res = Reservation.query.filter_by(user_id=user_id).order_by(Reservation.reserved_at.desc()).all()
    out = []
    for r in res:
        plot = Plot.query.get(r.plot_id)
        out.append({
            'id': r.id,
            'plot_id': r.plot_id,
            'block': r.block,
            'row': r.row,
            'plot_number': plot.number if plot else '',
            'status': r.status,
            'price': r.price,
            'reserved_at': to_local_time(r.reserved_at).isoformat()
        })
    return jsonify({'success': True, 'reservations': out})


@app.route('/api/my/reservation/<int:reservation_id>/cancel', methods=['POST'])
def api_my_cancel(reservation_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Not logged in'}), 403
    r = Reservation.query.get(reservation_id)
    if not r or r.user_id != user_id:
        return jsonify({'success': False, 'error': 'Reservation not found'}), 404
    if r.status != 'pending':
        return jsonify({'success': False, 'error': 'Only pending reservations can be cancelled'}), 400
    try:
        # free plot if linked
        if r.plot_id:
            p = Plot.query.get(r.plot_id)
            if p:
                p.status = 'available'
                p.assigned_to = None
        db.session.delete(r)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/reservation/<int:reservation_id>/confirm', methods=['POST'])
def api_admin_confirm(reservation_id):
    if not session.get('admin_id'):
        return jsonify({'success': False, 'error': 'Not authorized'}), 403
    r = Reservation.query.get(reservation_id)
    if not r:
        return jsonify({'success': False, 'error': 'Reservation not found'}), 404
    try:
        # confirm this reservation
        r.status = 'confirmed'

        # mark linked plot as reserved and assign to confirmed user
        if r.plot_id:
            p = Plot.query.get(r.plot_id)
            if p:
                p.status = 'reserved'
                p.assigned_to = f"{r.user_id}"

        # cancel any other pending reservations for the same plot
        canceled_infos = []
        try:
            others = Reservation.query.filter(Reservation.plot_id == r.plot_id, Reservation.status == 'pending', Reservation.id != r.id).all()
            for o in others:
                o.status = 'canceled'
                try:
                    plot_obj_o = Plot.query.get(o.plot_id) if o.plot_id is not None else None
                    plot_label_o = plot_obj_o.number if (plot_obj_o and getattr(plot_obj_o, 'number', None)) else str(o.plot_id)
                except Exception:
                    plot_label_o = str(o.plot_id)
                canceled_infos.append({'user_id': o.user_id, 'plot_label': plot_label_o})
        except Exception:
            # if anything goes wrong cancelling others, rollback will handle it below
            pass
        db.session.commit()
        # create cancel notifications after commit to avoid rollback wiping them
        try:
            for info in canceled_infos:
                try:
                    cancel_note = Notification(user_id=info['user_id'], message=f"Your reservation for plot {info['plot_label']} was canceled because another user was approved first.", status='canceled')
                    db.session.add(cancel_note)
                except Exception:
                    pass
            if canceled_infos:
                db.session.commit()
        except Exception:
            db.session.rollback()
        # notify the user (use plot number when available)
        try:
            try:
                plot_obj = Plot.query.get(r.plot_id) if r.plot_id is not None else None
                plot_label = plot_obj.number if (plot_obj and getattr(plot_obj, 'number', None)) else str(r.plot_id)
            except Exception:
                plot_label = str(r.plot_id)
            note = Notification(user_id=r.user_id, message=f"Your reservation for plot {plot_label} has been confirmed.", status='confirmed')
            db.session.add(note)
            db.session.commit()
        except Exception:
            db.session.rollback()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/reservation/<int:reservation_id>/fail', methods=['POST'])
def api_admin_fail(reservation_id):
    if not session.get('admin_id'):
        return jsonify({'success': False, 'error': 'Not authorized'}), 403
    r = Reservation.query.get(reservation_id)
    if not r:
        return jsonify({'success': False, 'error': 'Reservation not found'}), 404
    try:
        r.status = 'failed'
        # free up plot if linked
        if r.plot_id:
            p = Plot.query.get(r.plot_id)
            if p:
                p.status = 'available'
                p.assigned_to = None
        db.session.commit()
        # notify the user of failure (use plot number when available)
        try:
            try:
                plot_obj = Plot.query.get(r.plot_id) if r.plot_id is not None else None
                plot_label = plot_obj.number if (plot_obj and getattr(plot_obj, 'number', None)) else str(r.plot_id)
            except Exception:
                plot_label = str(r.plot_id)
            note = Notification(user_id=r.user_id, message=f"Your reservation for plot {plot_label} was not approved.", status='failed')
            db.session.add(note)
            db.session.commit()
        except Exception:
            db.session.rollback()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/reservation/<int:reservation_id>/status', methods=['POST'])
def api_admin_update_reservation_status(reservation_id):
    """Generic endpoint used by the admin UI to set a reservation's status.
    Accepts JSON { status: 'pending'|'confirmed'|'failed'|... }
    Will also update linked Plot.status and assigned_to when appropriate and
    create a Notification for the user.
    """
    if not session.get('admin_id'):
        return jsonify({'success': False, 'error': 'Not authorized'}), 403
    data = request.get_json() or request.form
    new_status = (data.get('status') or '').strip()
    if not new_status:
        return jsonify({'success': False, 'error': 'Missing status'}), 400
    r = Reservation.query.get(reservation_id)
    if not r:
        return jsonify({'success': False, 'error': 'Reservation not found'}), 404
    try:
        # handle common transitions
        if new_status == 'confirmed':
            r.status = 'confirmed'
            if r.plot_id:
                p = Plot.query.get(r.plot_id)
                if p:
                    p.status = 'reserved'
                    p.assigned_to = str(r.user_id)
            # cancel other pending reservations for same plot
            canceled_infos = []
            try:
                others = Reservation.query.filter(Reservation.plot_id == r.plot_id, Reservation.status == 'pending', Reservation.id != r.id).all()
                for o in others:
                    o.status = 'canceled'
                    try:
                        plot_obj = Plot.query.get(o.plot_id) if o.plot_id is not None else None
                        plot_label = plot_obj.number if (plot_obj and getattr(plot_obj, 'number', None)) else str(o.plot_id)
                    except Exception:
                        plot_label = str(o.plot_id)
                    canceled_infos.append({'user_id': o.user_id, 'plot_label': plot_label})
            except Exception:
                pass
            # will create notifications after commit below
        elif new_status == 'failed':
            r.status = 'failed'
            if r.plot_id:
                p = Plot.query.get(r.plot_id)
                if p:
                    p.status = 'available'
                    p.assigned_to = None
        elif new_status == 'pending':
            # revert to pending and free plot if it was reserved for this reservation
            r.status = 'pending'
            if r.plot_id:
                p = Plot.query.get(r.plot_id)
                if p and p.assigned_to == str(r.user_id):
                    p.status = 'available'
                    p.assigned_to = None
        else:
            # unknown/other statuses - just set it
            r.status = new_status

        db.session.commit()

        # notify the user about the status change
        try:
            try:
                plot_obj = Plot.query.get(r.plot_id) if r.plot_id is not None else None
                plot_label = plot_obj.number if (plot_obj and getattr(plot_obj, 'number', None)) else str(r.plot_id)
            except Exception:
                plot_label = str(r.plot_id)
            note = Notification(user_id=r.user_id, message=f"Your reservation for plot {plot_label} status updated to {r.status}.", status=r.status)
            db.session.add(note)
            db.session.commit()
        except Exception:
            db.session.rollback()

        # create cancel notifications for any reservations we canceled above (if present)
        try:
            if 'canceled_infos' in locals() and canceled_infos:
                for info in canceled_infos:
                    try:
                        cancel_note = Notification(user_id=info['user_id'], message=f"Your reservation for plot {info['plot_label']} was canceled because another user was approved first.", status='canceled')
                        db.session.add(cancel_note)
                    except Exception:
                        pass
                db.session.commit()
        except Exception:
            db.session.rollback()

        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['first_name'] = user.first_name
            session['last_name'] = user.last_name
            flash('Login successful!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')


@app.context_processor
def inject_notifications():
    user_id = session.get('user_id')
    if not user_id:
        return {}
    try:
        notes = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).limit(20).all()
        out = []
        for n in notes:
            out.append({'message': n.message, 'status': n.status or 'pending', 'time': n.created_at.strftime('%Y-%m-%d %H:%M')})
        return {'notifications': out, 'clear_notifications_url': url_for('clear_notifications'), 'notifications_url': url_for('api_notifications')}
    except Exception:
        return {'notifications': [], 'clear_notifications_url': '', 'notifications_url': ''}


@app.route('/clear_notifications', methods=['POST'])
def clear_notifications():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Not logged in'}), 403
    try:
        Notification.query.filter_by(user_id=user_id).delete()
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/notifications')
def api_notifications():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Not logged in'}), 403
    try:
        notes = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).limit(50).all()
        out = []
        for n in notes:
            out.append({'id': n.id, 'message': n.message, 'status': n.status or 'pending', 'time': to_local_time(n.created_at).isoformat()})
        return jsonify({'success': True, 'notifications': out})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/user/profile', methods=['GET', 'POST'])
def user_profile():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to view your profile.', 'danger')
        return redirect(url_for('login'))
    user = User.query.get(user_id)
    if request.method == 'POST':
        user.first_name = request.form['first_name']
        user.middle_name = request.form.get('middle_name', '')
        user.last_name = request.form['last_name']
        user.email = request.form['email']
        user.phone = request.form.get('phone', '')
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('user_profile'))
    return render_template('user/profile.html', user=user)

@app.route('/user/reservations')
def user_reservations():
    return render_template('/user/reservations.html')

@app.route('/user/owned_plots')
def user_owned_plots():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to view owned plots.', 'danger')
        return redirect(url_for('login'))

    # find plots assigned to this user (assigned_to stored as string user_id in admin confirm)
    try:
        plots = Plot.query.filter(Plot.assigned_to == str(user_id)).all()
    except Exception:
        plots = []
    return render_template('user/ownedPlots.html', plots=plots)


@app.route('/plots/occupy', methods=['POST'])
def plots_occupy():
    """Endpoint for a user or admin to mark a plot as occupied.
    Expects JSON: { plot: <number>, block: <block>, name, dob, dod, buried_date, age }
    """
    user_id = session.get('user_id')
    admin_id = session.get('admin_id')
    if not user_id and not admin_id:
        return jsonify({'success': False, 'message': 'Not logged in'}), 403


    data = request.get_json() or request.form
    # prefer plot_id (sent by the UI), but fall back to plot number
    plot_id = data.get('plot_id') or data.get('plotId') or data.get('plot_id')
    plot_number = data.get('plot') or data.get('plot_number')
    block = data.get('block')

    if not plot_id and not plot_number:
        return jsonify({'success': False, 'message': 'Missing plot identifier'}), 400

    try:
        p = None
        # lookup by id when provided
        if plot_id is not None and str(plot_id) != '':
            try:
                p = Plot.query.get(int(plot_id))
            except Exception:
                p = None

        # fallback: try to find plot by number and block if provided
        if not p:
            if block:
                p = Plot.query.filter_by(number=str(plot_number), block=block).first()
            else:
                p = Plot.query.filter_by(number=str(plot_number)).first()

        if not p:
            return jsonify({'success': False, 'message': 'Plot not found'}), 404

        # ensure current user actually owns this plot, or admin is doing it
        if not admin_id and str(user_id) != (p.assigned_to or ''):
            return jsonify({'success': False, 'message': 'Not authorized to occupy this plot'}), 403

        # extract deceased details from payload
        name = data.get('name') or data.get('deceasedName') or data.get('deceased_name')
        dob = data.get('dob') or data.get('deceasedDob') or data.get('deceased_dob')
        dod = data.get('dod') or data.get('deceasedDod') or data.get('deceased_dod')
        buried_date = data.get('buried_date') or data.get('deceasedBuried') or data.get('buriedDate')
        age = data.get('age') or data.get('deceasedAge') or data.get('deceased_age')

        # basic validation
        if not name:
            return jsonify({'success': False, 'message': 'Missing deceased name'}), 400

        dob_val = None
        dod_val = None
        buried_val = None
        try:
            if dob:
                dob_val = datetime.fromisoformat(dob).date()
            if dod:
                dod_val = datetime.fromisoformat(dod).date()
            if buried_date:
                buried_val = datetime.fromisoformat(buried_date).date()
        except Exception:
            # ignore parse errors and leave as None
            pass

        age_val = None
        try:
            age_val = int(age) if age not in (None, '') else None
        except Exception:
            age_val = None

        try:
            # create deceased record linked to this plot (use FK)
            deceased = Deceased(
                name=name,
                dob=dob_val,
                dod=dod_val,
                buried_date=buried_val,
                age=age_val,
                plot_id=int(p.id),
                square_meter=(p.square_meter or p.number)
            )
            db.session.add(deceased)

            # mark plot occupied but preserve assigned_to (ownership)
            p.status = 'occupied'

            # remove the reservation since plot is now occupied
            Reservation.query.filter_by(plot_id=p.id).delete()

            db.session.commit()

            # return a consistent response including plot display info
            plot_info = {'plot_id': p.id, 'plot_number': p.number, 'block': p.block, 'row': p.row, 'square_meter': p.square_meter}
            return jsonify({'success': True, 'deceased': {'id': deceased.id, 'name': deceased.name, 'plot_id': deceased.plot_id, 'plot': plot_info}})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password_hash, password):
            session['admin_id'] = admin.id
            session['admin_username'] = admin.username
            flash('Admin login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin username or password', 'danger')
    return render_template('login_admin.html')

# Admin dashboard route
@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_id'):
        flash('Please log in as admin.', 'danger')
        return redirect(url_for('loginAdmin'))
    # compute plot statistics
    try:
        total_plots = Plot.query.count()
        occupied_plots = Plot.query.filter(Plot.status != None).filter(Plot.status != '').filter(Plot.status.ilike('occupied')).count()
        # consider 'reserved' as not available; available = total - occupied - reserved
        reserved_plots = Plot.query.filter(Plot.status != None).filter(Plot.status != '').filter(Plot.status.ilike('reserved')).count()
        available_plots = total_plots - occupied_plots - reserved_plots
    except Exception:
        total_plots = occupied_plots = reserved_plots = available_plots = 0

    # fetch top 6 recent reservations
    recent_reservations = []
    try:
        recent = Reservation.query.order_by(Reservation.reserved_at.desc()).limit(6).all()
        for r in recent:
            user = User.query.get(r.user_id)
            plot = Plot.query.get(r.plot_id)
            recent_reservations.append({
                'id': r.id,
                'name': f"{user.first_name} {user.last_name}" if user else '',
                'block': r.block or (plot.block if plot else ''),
                'row': r.row or (plot.row if plot else ''),
                'plot_number': plot.number if plot else '',
                'reserved_at': r.reserved_at,
                'status': r.status
            })
    except Exception:
        recent_reservations = []

    return render_template('admin/dashboard.html', admin_username=session.get('admin_username'),
                           total_plots=total_plots, occupied_plots=occupied_plots,
                           available_plots=available_plots, reserved_plots=reserved_plots,
                           recent_reservations=recent_reservations)

@app.route('/admin/reservation')
def admin_reservation():
    if not session.get('admin_id'):
        flash('Please log in as admin.', 'danger')
        return redirect(url_for('loginAdmin'))
    return render_template('admin/reservation.html')

@app.route('/admin/deceased')
def admin_deceased():
    if not session.get('admin_id'):
        flash('Please log in as admin.', 'danger')
        return redirect(url_for('loginAdmin'))
    # supply existing deceased records and available plots for the template
    deceased_list = []
    try:
        raw = Deceased.query.order_by(Deceased.created_at.desc()).all()
        for d in raw:
            plot = Plot.query.get(d.plot_id)
            deceased_list.append({
                'id': d.id,
                'name': d.name,
                'dob': d.dob.isoformat() if d.dob else '',
                'dod': d.dod.isoformat() if d.dod else '',
                'price': d.price,
                'age': d.age,
                'plot_id': d.plot_id,
                'plot_number': plot.number if plot else '',
                'block': plot.block if plot else '',
                'row': plot.row if plot else '',
                'square_meter': plot.square_meter if plot else '',
                'created_at': to_local_time(d.created_at).isoformat()
            })
    except Exception:
        deceased_list = []

    # available plots: those with status available or empty
    plots = []
    try:
        rawp = Plot.query.filter((Plot.status == None) | (Plot.status == '') | (Plot.status == 'available')).order_by(Plot.number.asc()).all()
        for p in rawp:
            plots.append({ 'id': p.id, 'number': p.number, 'block': p.block, 'row': p.row, 'square_meter': p.square_meter })
    except Exception:
        plots = []

    return render_template('admin/deceasedRecords.html', deceased_records=deceased_list, available_plots=plots)


@app.route('/admin/deceased/add', methods=['POST'])
def admin_deceased_add():
    if not session.get('admin_id'):
        return jsonify({'success': False, 'error': 'Not authorized'}), 403

    data = request.get_json() or request.form
    try:
        name = data.get('name')
        dob = data.get('dob')
        dod = data.get('dod')
        price = data.get('price')
        age = data.get('age')
        plot_id = data.get('plot_id')

        if not name or not plot_id:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400

        dob_val = None
        dod_val = None
        try:
            if dob:
                dob_val = datetime.fromisoformat(dob).date()
            if dod:
                dod_val = datetime.fromisoformat(dod).date()
        except Exception:
            pass

        price_val = None
        try:
            price_val = float(price) if price not in (None, '') else None
        except Exception:
            price_val = None

        age_val = None
        try:
            age_val = int(age) if age not in (None, '') else None
        except Exception:
            age_val = None

        # ensure selected plot still available
        try:
            p = Plot.query.get(int(plot_id))
        except Exception:
            p = None

        if p:
            if p.status and p.status.lower() == 'occupied':
                return jsonify({'success': False, 'error': 'Plot already occupied'}), 409

        try:
            deceased = Deceased(
                name=name,
                dob=dob_val,
                dod=dod_val,
                price=price_val,
                age=age_val,
                plot_id=int(plot_id)
            )
            db.session.add(deceased)

            # Mark plot occupied if exists
            if p:
                p.status = 'occupied'
                p.assigned_to = None

            db.session.commit()
            # include plot display info in response
            plot_info = None
            if deceased.plot_id:
                pp = Plot.query.get(deceased.plot_id)
                if pp:
                    plot_info = {'plot_id': pp.id, 'plot_number': pp.number, 'block': pp.block, 'row': pp.row, 'square_meter': pp.square_meter}
            return jsonify({'success': True, 'deceased': {'id': deceased.id, 'name': deceased.name, 'plot_id': deceased.plot_id, 'plot': plot_info}})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/plot')
def admin_plot():
    if not session.get('admin_id'):
        flash('Please log in as admin.', 'danger')
        return redirect(url_for('loginAdmin'))
    plots = Plot.query.order_by(Plot.id.asc()).all()
    return render_template('admin/plotManagement.html', plots=plots)


@app.route('/admin/deceased/<int:deceased_id>/delete', methods=['POST'])
def admin_deceased_delete(deceased_id):
    if not session.get('admin_id'):
        return jsonify({'success': False, 'error': 'Not authorized'}), 403
    try:
        d = Deceased.query.get(deceased_id)
        if not d:
            return jsonify({'success': False, 'error': 'Not found'}), 404

        # free linked plot if exists: prefer plot_id (accurate FK), fall back to stored plot_number
        try:
            p = None
            # if Deceased has a plot_id FK, use it to find the plot
            if getattr(d, 'plot_id', None) is not None:
                try:
                    p = Plot.query.get(int(d.plot_id))
                except Exception:
                    p = None
            # fallback: older records may have stored a plot_number property
            if not p and getattr(d, 'plot_number', None):
                try:
                    p = Plot.query.filter_by(number=str(d.plot_number)).first()
                except Exception:
                    p = None
            if p:
                # clear 'occupied' state but keep ownership so the plot remains in the user's owned plots
                # set status to 'reserved' to reflect the previous confirmed reservation state
                try:
                    p.status = 'reserved'
                except Exception:
                    # fallback: set to string 'reserved'
                    p.status = 'reserved'
        except Exception:
            pass

        db.session.delete(d)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/plots')
def api_plots():
    try:
        # Apply same visibility rules as search_plot API:
        user_id = session.get('user_id')
        if session.get('admin_id'):
            raw = Plot.query.order_by(Plot.id.asc()).all()
        elif user_id:
            raw = Plot.query.filter(
                ((Plot.status == None) | (Plot.status == '') | (Plot.status != 'occupied')) | (Plot.assigned_to == str(user_id))
            ).order_by(Plot.id.asc()).all()
        else:
            raw = Plot.query.filter((Plot.status == None) | (Plot.status == '') | (Plot.status != 'occupied')).order_by(Plot.id.asc()).all()
        out = []
        for p in raw:
            name = ''
            date_reserved = ''
            if p.status and p.status.lower() == 'occupied':
                deceased = Deceased.query.filter_by(plot_id=p.id).first()
                if deceased:
                    name = deceased.name
                    date_reserved = deceased.buried_date.isoformat() if deceased.buried_date else ''
            elif p.status and p.status.lower() == 'reserved':
                reservation = Reservation.query.filter_by(plot_id=p.id).first()
                if reservation:
                    user = User.query.get(reservation.user_id)
                    if user:
                        name = f"{user.first_name} {user.last_name}"
                    date_reserved = reservation.reserved_at.isoformat() if reservation.reserved_at else ''
            out.append({
                'id': p.id,
                'block': p.block,
                'row': p.row,
                'number': p.number,
                'status': p.status,
                'square_meter': p.square_meter,
                'price': p.price,
                'name': name,
                'date_reserved': date_reserved
            })
        return jsonify({'success': True, 'plots': out})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/deceased/plot/<int:plot_id>')
def api_deceased_by_plot(plot_id):
    try:
        d = Deceased.query.filter_by(plot_id=plot_id).first()
        if not d:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        return jsonify({'success': True, 'deceased': {
            'id': d.id,
            'name': d.name,
            'dob': d.dob.isoformat() if d.dob else '',
            'dod': d.dod.isoformat() if d.dod else '',
            'age': d.age,
            'plot_id': d.plot_id
        }})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/contact')
def api_admin_contact():
    """Return primary admin contact details for public pages."""
    try:
        admin = Admin.query.order_by(Admin.id.asc()).first()
        if not admin:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        return jsonify({'success': True, 'email': admin.email or '', 'phone': admin.phone or ''})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/admin/deceased/<int:deceased_id>/edit', methods=['POST'])
def admin_deceased_edit(deceased_id):
    if not session.get('admin_id'):
        return jsonify({'success': False, 'error': 'Not authorized'}), 403
    data = request.get_json() or request.form
    try:
        d = Deceased.query.get(deceased_id)
        if not d:
            return jsonify({'success': False, 'error': 'Not found'}), 404

        name = data.get('name') or d.name
        dob = data.get('dob')
        dod = data.get('dod')
        price = data.get('price')
        age = data.get('age')
        plot_id = data.get('plot_id') or d.plot_id

        dob_val = None
        dod_val = None
        try:
            if dob: dob_val = datetime.fromisoformat(dob).date()
            if dod: dod_val = datetime.fromisoformat(dod).date()
        except Exception:
            pass

        # if plot changed, free old and occupy new
        old_plot_id = d.plot_id
        if plot_id and int(plot_id) != int(old_plot_id if old_plot_id is not None else -1):
            # free old
            try:
                if old_plot_id:
                    op = Plot.query.get(int(old_plot_id))
                    if op:
                        op.status = 'available'
                        op.assigned_to = None
            except Exception:
                pass
            # occupy new if available
            try:
                np = Plot.query.get(int(plot_id))
                if np and np.status and np.status.lower() == 'occupied':
                    return jsonify({'success': False, 'error': 'Target plot already occupied'}), 409
                if np:
                    np.status = 'occupied'
                    np.assigned_to = session.get('admin_id') and str(session.get('admin_id')) or np.assigned_to
            except Exception:
                pass

        d.name = name
        d.dob = dob_val or d.dob
        d.dod = dod_val or d.dod
        try:
            d.price = float(price) if price not in (None, '') else d.price
        except Exception:
            pass
        try:
            d.age = int(age) if age not in (None, '') else d.age
        except Exception:
            pass
        d.plot_id = int(plot_id) if plot_id is not None else d.plot_id

        db.session.commit()
        plot_info = None
        if d.plot_id:
            pp = Plot.query.get(d.plot_id)
            if pp:
                plot_info = {'plot_id': pp.id, 'plot_number': pp.number}
        return jsonify({'success': True, 'deceased': {'id': d.id, 'name': d.name, 'plot_id': d.plot_id, 'plot': plot_info}})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/admin/plot/add', methods=['POST'])
def admin_plot_add():
    if not session.get('admin_id'):
        return jsonify({'success': False, 'error': 'Not authorized'}), 403

    data = request.get_json() or request.form
    try:
        number = data.get('plotNumber') or data.get('number')
        block = data.get('plotBlock') or data.get('block')
        row = data.get('plotRow') or data.get('row')
        status = data.get('plotStatus') or data.get('status')
        assigned = data.get('plotAssigned') or data.get('assigned_to')
        reserved = data.get('plotReservedDate') or data.get('reserved_date')
        sqm = data.get('plotSquareMeter') or data.get('square_meter')
        price = data.get('plotPrice') or data.get('price')

        reserved_date = None
        if reserved:
            try:
                reserved_date = datetime.strptime(reserved, '%Y-%m-%d').date()
            except Exception:
                reserved_date = None

        price_val = None
        try:
            price_val = float(price) if price not in (None, '') else None
        except Exception:
            price_val = None

        plot = Plot(
            block=str(block) if block is not None else None,
            row=str(row) if row is not None else None,
            number=str(number),
            status=str(status) if status is not None else None,
            assigned_to=str(assigned) if assigned is not None else None,
            reserved_date=reserved_date,
            square_meter=str(sqm) if sqm is not None else None,
            price=price_val
        )
        db.session.add(plot)
        db.session.commit()

        return jsonify({'success': True, 'plot': {
            'id': plot.id,
            'block': plot.block,
            'row': plot.row,
            'number': plot.number,
            'status': plot.status,
            'assigned_to': plot.assigned_to,
            'reserved_date': plot.reserved_date.isoformat() if plot.reserved_date else '',
            'square_meter': plot.square_meter,
            'price': plot.price
        }})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/admin/plot/<int:plot_id>/edit', methods=['POST'])
def admin_plot_edit(plot_id):
    if not session.get('admin_id'):
        return jsonify({'success': False, 'error': 'Not authorized'}), 403
    data = request.get_json() or request.form
    try:
        p = Plot.query.get(plot_id)
        if not p:
            return jsonify({'success': False, 'error': 'Not found'}), 404

        # accept a few possible field names used by the UI
        p.block = data.get('plotBlock') or data.get('block') or p.block
        p.row = data.get('plotRow') or data.get('row') or p.row
        # number usually shouldn't change from the edit UI, but accept it if provided
        p.number = data.get('plotNumber') or data.get('number') or p.number
        p.status = data.get('plotStatus') or data.get('status') or p.status
        p.square_meter = data.get('plotSquareMeter') or data.get('square_meter') or p.square_meter
        price = data.get('plotPrice') or data.get('price')
        try:
            if price not in (None, ''):
                p.price = float(price)
        except Exception:
            pass

        db.session.commit()
        return jsonify({'success': True, 'plot': {
            'id': p.id,
            'block': p.block,
            'row': p.row,
            'number': p.number,
            'status': p.status,
            'square_meter': p.square_meter,
            'price': p.price
        }})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/admin/plot/<int:plot_id>/delete', methods=['POST'])
def admin_plot_delete(plot_id):
    if not session.get('admin_id'):
        return jsonify({'success': False, 'error': 'Not authorized'}), 403
    try:
        p = Plot.query.get(plot_id)
        if not p:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        db.session.delete(p)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# Register route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        first_name = request.form['first_name']
        middle_name = request.form.get('middle_name', '')
        last_name = request.form['last_name']
        email = request.form['email']
        phone = request.form.get('phone', '')
        security_question = request.form.get('security_question', '').strip()
        security_answer = request.form.get('security_answer', '').strip()
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        if password != confirm_password:
            # keep the entered fields except passwords (clear password inputs)
            flash('Passwords do not match', 'danger')
            return render_template('register.html',
                username=username,
                first_name=first_name,
                middle_name=middle_name,
                last_name=last_name,
                email=email,
                phone=phone
            )
        if User.query.filter_by(username=username).first():
            # preserve other fields so the user can pick a different username
            flash('Username already exists', 'danger')
            return render_template('register.html',
                username=username,
                first_name=first_name,
                middle_name=middle_name,
                last_name=last_name,
                email=email,
                phone=phone
            )
        if User.query.filter_by(email=email).first():
            # preserve other fields but clear the email so the user can enter a different one
            flash('Email already registered', 'danger')
            return render_template('register.html',
                username=username,
                first_name=first_name,
                middle_name=middle_name,
                last_name=last_name,
                email='',
                phone=phone
            )
        password_hash = generate_password_hash(password)
        # hash the security answer if provided
        sec_ans_hash = generate_password_hash(security_answer) if security_answer else None

        new_user = User(
            username=username,
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            email=email,
            phone=phone,
            password_hash=password_hash
        )
        # attach security fields after creation to avoid issues with older DB schemas
        new_user.security_question = security_question or None
        new_user.security_answer_hash = sec_ans_hash
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    """Step 1: ask for username. On POST, if user exists and has security question, show question form."""
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        if not username:
            flash('Please enter your username', 'danger')
            return redirect(url_for('forgot_password'))
        user = User.query.filter_by(username=username).first()
        if not user:
            flash('User not found', 'danger')
            return redirect(url_for('forgot_password'))
        if not user.security_question:
            flash('No security question set for this account. Contact admin for help.', 'danger')
            return redirect(url_for('forgot_password'))
        # render page to answer question and reset password
        return render_template('forgot_password_question.html', username=username, question=user.security_question)
    return render_template('forgot_password.html')


@app.route('/reset_password', methods=['POST'])
def reset_password():
    username = (request.form.get('username') or '').strip()
    answer = (request.form.get('security_answer') or '').strip()
    new_pw = request.form.get('new_password') or ''
    confirm_pw = request.form.get('confirm_password') or ''
    if not username:
        flash('Missing username', 'danger')
        return redirect(url_for('forgot_password'))
    user = User.query.filter_by(username=username).first()
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('forgot_password'))
    if new_pw != confirm_pw:
        flash('Passwords do not match', 'danger')
        return render_template('forgot_password_question.html', username=username, question=user.security_question)
    if not user.security_answer_hash or not check_password_hash(user.security_answer_hash, answer):
        flash('Incorrect answer to security question', 'danger')
        return render_template('forgot_password_question.html', username=username, question=user.security_question)
    # set new password
    user.password_hash = generate_password_hash(new_pw)
    db.session.commit()
    flash('Password reset successful. Please log in with your new password.', 'success')
    return redirect(url_for('login'))

@app.route('/user/logout')
def user_logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('Admin has been logged out.', 'info')
    return redirect(url_for('admin_login'))

if __name__ == '__main__':
    app.run(debug=True)
