"""Apply additive access/location migration to the local main DB, preserving records."""
from parking_tools import ROOT, cli
from ops_tools import postgres


def main():
    with postgres() as db:
        db.execute('SELECT pg_advisory_xact_lock(726193001)')
        for version,file in [('008','008_access_and_location.sql'),('009','009_location_names.sql')]:
            if db.execute('SELECT 1 FROM schema_migrations WHERE version=%s',(version,)).fetchone():continue
            db.execute((ROOT/'database/migrations'/file).read_text(encoding='utf-8'))
            db.execute('INSERT INTO schema_migrations(version) VALUES(%s)',(version,))
    print('Applied additive access/location migration. Existing records preserved.')


if __name__=='__main__':
    cli(main)
