"""Configure real Gmail SMTP privately. No email is sent by this command."""
import argparse
import getpass
import re
import warnings
import smtplib
import ssl
from identity_admin import IDENTITY, admin_token, request, wait_identity, environment
from parking_tools import cli


def gmail_settings(sender, password):
    if not re.fullmatch(r'[A-Za-z0-9._%+-]+@gmail\.com',sender):
        raise RuntimeError('Provide the Gmail account you own as --sender.')
    password=''.join(password.split())
    if not re.fullmatch(r'[A-Za-z]{16}',password):
        raise RuntimeError('Enter the 16-letter Gmail app password, not the normal account password.')
    return {'host':'smtp.gmail.com','port':'587','from':sender,'fromDisplayName':'Vehicle Parking System',
            'replyTo':sender,'user':sender,'password':password,'auth':'true','starttls':'true','ssl':'false'}


def main():
    parser=argparse.ArgumentParser(description='Configure real mail for the parking realm; synthetic test realms still use Mailpit.')
    parser.add_argument('--sender',default=environment().get('SMTP_SENDER',''))
    args=parser.parse_args()
    if not args.sender or args.sender.startswith('REPLACE_WITH_'):
        args.sender=input('Sender Gmail address you own: ').strip()
    print('Configure mail from',args.sender,'for accounts registered in the parking realm.')
    print('Generate a Gmail app password first. Input is hidden; nothing is stored in Git or printed.')
    # Refuse an environment where getpass would echo the secret.
    with warnings.catch_warnings():
        warnings.simplefilter('error',getpass.GetPassWarning)
        try:
            password=getpass.getpass('Gmail app password: ')
        except getpass.GetPassWarning:
            raise RuntimeError('Run this command in your own interactive terminal for hidden password input.') from None
    settings=gmail_settings(args.sender,password)
    try:
        with smtplib.SMTP(settings['host'],int(settings['port']),timeout=15) as smtp:
            smtp.ehlo(); smtp.starttls(context=ssl.create_default_context()); smtp.ehlo()
            smtp.login(settings['user'],settings['password'])
    except (smtplib.SMTPException,OSError):
        raise RuntimeError('Could not authenticate to Gmail over TLS. Check the app password, account policy and network; existing mail settings were not changed.') from None
    wait_identity()
    request(IDENTITY+'/admin/realms/parking',{'smtpServer':settings},admin_token(),method='PUT')
    print('Gmail SMTP configured in the local identity service. No email sent by this setup command.')
    print('Register/verify your own account to test delivery. Automated synthetic tests continue using Mailpit.')


if __name__ == '__main__':
    cli(main)
