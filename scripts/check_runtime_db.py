"""Verify the runtime account can read and cannot rewrite audit/schema records."""
from parking_tools import ROOT,cli
from ops_tools import postgres

def main():
    # Initializes the retained Python dependency path, then closes the owner connection.
    postgres().close()
    import psycopg
    path=ROOT/'.tools/secrets/runtime-database-url'
    with psycopg.connect(path.read_text().replace('host=db ','host=127.0.0.1 ')) as db:
        db.execute('SELECT count(*) FROM locations').fetchone()
        for statement in ('UPDATE audit_events SET action=action WHERE false','DELETE FROM audit_events WHERE false','CREATE TABLE forbidden_runtime_change(id int)'):
            try:
                with db.transaction():db.execute(statement)
            except psycopg.errors.InsufficientPrivilege:pass
            else:raise RuntimeError('Runtime account received an unwanted permission.')
    print('Runtime login: read allowed; audit UPDATE/DELETE and schema creation denied.')

if __name__=='__main__':cli(main)
