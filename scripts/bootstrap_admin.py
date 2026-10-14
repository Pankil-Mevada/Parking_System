"""Explicit local-owner bootstrap after verified login. No default privileged account."""
import argparse
import uuid
from parking_tools import cli, docker


def main():
    parser = argparse.ArgumentParser(description='Grant the first local operator admin at one location. Requires local database-owner access.')
    parser.add_argument('--user-id', required=True, type=uuid.UUID)
    parser.add_argument('--location-id', required=True, type=uuid.UUID)
    args = parser.parse_args()
    # UUID parsing supplies canonical identifiers; no arbitrary SQL fragments.
    sql = f"""\set ON_ERROR_STOP on
BEGIN;
SELECT id FROM users WHERE id='{args.user_id}' AND status='enabled' FOR UPDATE;
INSERT INTO staff_assignments(user_id,location_id,role)
VALUES('{args.user_id}','{args.location_id}','operator_admin')
ON CONFLICT(user_id,location_id) DO UPDATE SET role='operator_admin';
INSERT INTO audit_events(actor_id,action,target_type,target_id,request_id)
VALUES('{args.user_id}','local_owner_bootstrap','location','{args.location_id}',gen_random_uuid());
COMMIT;
"""
    docker(['compose', 'exec', '-T', 'db', 'sh', '-c',
            'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'], input=sql, text=True)
    print('Local operator assignment recorded. Other roles use the authorized staff-assignment API.')


if __name__ == '__main__':
    cli(main)
