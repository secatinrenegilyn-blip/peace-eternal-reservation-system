import os
import sys

# ensure repo root is on sys.path so we can import web.py when running from scripts/
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from web import app, db, User, Admin, Plot, Reservation, Deceased


def clear_db():
    with app.app_context():
        # counts before
        user_count = User.query.count()
        admin_count = Admin.query.count()
        plot_count = Plot.query.count()
        reservation_count = Reservation.query.count()
        deceased_count = Deceased.query.count()

        print(f"Before: users={user_count}, admins={admin_count}, plots={plot_count}, reservations={reservation_count}, deceased={deceased_count}")

        # delete reservations
        try:
            del_res = Reservation.query.delete()
            db.session.commit()
            print(f"Deleted {del_res} reservations")
        except Exception as e:
            db.session.rollback()
            print('Failed to delete reservations:', e)

        # delete deceased
        try:
            del_dec = Deceased.query.delete()
            db.session.commit()
            print(f"Deleted {del_dec} deceased records")
        except Exception as e:
            db.session.rollback()
            print('Failed to delete deceased records:', e)

        # delete plots
        try:
            del_plots = Plot.query.delete()
            db.session.commit()
            print(f"Deleted {del_plots} plots")
        except Exception as e:
            db.session.rollback()
            print('Failed to delete plots:', e)

        # delete users except admin
        try:
            admins = [a.username for a in Admin.query.all()]
            # remove users whose username is NOT in admins
            del_users = User.query.filter(~User.username.in_(admins)).delete(synchronize_session=False)
            db.session.commit()
            print(f"Deleted {del_users} users (non-admin)")
        except Exception as e:
            db.session.rollback()
            print('Failed to delete users:', e)

        # final counts
        user_count = User.query.count()
        admin_count = Admin.query.count()
        plot_count = Plot.query.count()
        reservation_count = Reservation.query.count()
        deceased_count = Deceased.query.count()
        print(f"After: users={user_count}, admins={admin_count}, plots={plot_count}, reservations={reservation_count}, deceased={deceased_count}")

if __name__ == '__main__':
    clear_db()
