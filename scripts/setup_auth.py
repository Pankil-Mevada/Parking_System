"""Generate local identity secrets without printing them; never overwrite existing values."""
import secrets
from parking_tools import ROOT, cli


def main():
    path = ROOT / '.env'
    if not path.is_file():
        raise RuntimeError('Create .env from .env.example and configure database credentials first.')
    values = path.read_text(encoding='utf-8')
    for name, value in [('OIDC_CLIENT_SECRET', secrets.token_urlsafe(48)),
                        ('OIDC_ADMIN_USER', 'parking-setup-admin'),
                        ('OIDC_ADMIN_PASSWORD', secrets.token_urlsafe(32))]:
        lines = values.splitlines()
        existing = next((line for line in lines if line.startswith(name + '=')), None)
        if existing is None:
            values = values.rstrip() + '\n' + name + '=' + value + '\n'
        elif 'REPLACE_WITH_' in existing:
            values = values.replace(existing, name + '=' + value)
    path.write_text(values, encoding='utf-8')
    print('Local identity secrets configured in ignored .env; no credentials printed.')


if __name__ == '__main__':
    cli(main)
