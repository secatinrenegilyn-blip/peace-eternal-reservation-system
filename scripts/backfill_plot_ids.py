"""Backfill script: map existing Reservation.plot_number and Deceased.plot_number (if present)
into Reservation.plot_id and Deceased.plot_id by matching Plot.number -> Plot.id.

This script is safe to run multiple times; it only sets plot_id where null and
reports how many rows were updated and any unmatched plot numbers.

It will not drop any columns. Run from project root using the project venv.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'instance', 'database.db')
DB_PATH = os.path.abspath(DB_PATH)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

def ensure_column(table, column, coltype='INTEGER'):
    cur.execute("PRAGMA table_info(%s)" % table)
    cols = [r[1] for r in cur.fetchall()]
    if column in cols:
        return True
    # SQLite cannot easily add NOT NULL foreign key; add simple column
    sql = f"ALTER TABLE {table} ADD COLUMN {column} {coltype};"
    print('Adding column:', column, 'to', table)
    cur.execute(sql)
    conn.commit()
    return True


def map_plot_numbers(table, src_col, dest_col):
    # find rows where dest_col is NULL and src_col not null
    cur.execute(f"SELECT id, {src_col} FROM {table} WHERE ({dest_col} IS NULL OR {dest_col} = '') AND {src_col} IS NOT NULL AND {src_col} != ''")
    rows = cur.fetchall()
    updated = 0
    unmatched = {}
    for rid, plotnum in rows:
        # try to find plot with matching number
        cur.execute("SELECT id FROM plot WHERE number = ?", (str(plotnum),))
        p = cur.fetchone()
        if p:
            plot_id = p[0]
            cur.execute(f"UPDATE {table} SET {dest_col} = ? WHERE id = ?", (plot_id, rid))
            updated += 1
        else:
            unmatched.setdefault(str(plotnum), 0)
            unmatched[str(plotnum)] += 1
    conn.commit()
    return updated, unmatched


def main():
    print('DB:', DB_PATH)
    # Ensure destination columns exist
    ensure_column('reservation', 'plot_id')
    ensure_column('deceased', 'plot_id')

    print('\nMapping reservation.plot_number -> reservation.plot_id')
    res_updated, res_unmatched = map_plot_numbers('reservation', 'plot_number', 'plot_id')
    print('Reservations updated:', res_updated)
    if res_unmatched:
        print('Unmatched reservation plot_numbers:')
        for k,v in res_unmatched.items():
            print('  ', k, '->', v)

    print('\nMapping deceased.plot_number -> deceased.plot_id')
    d_updated, d_unmatched = map_plot_numbers('deceased', 'plot_number', 'plot_id')
    print('Deceased updated:', d_updated)
    if d_unmatched:
        print('Unmatched deceased plot_numbers:')
        for k,v in d_unmatched.items():
            print('  ', k, '->', v)

    print('\nDone.')

if __name__ == '__main__':
    main()
