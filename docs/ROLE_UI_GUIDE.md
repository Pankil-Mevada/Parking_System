# Driver, staff and administrator — manual testing

Historical baseline before mandatory account approval: 44 strict-baseline checks passed (1 password-only check reserved
for separate execution); all 7 password-only checks passed, including real Chromium
driver setup email/password, staff signup/approval, vehicle registration and parking.
Latest password-only retained run: `b5a4ba1a-5fc8-4d10-846b-8543d29d9ef9`.

Current local login uses **email and password only**. Microsoft Authenticator and
other OTP apps are not required. Email verification remains enabled; messages
arrive in local Mailpit at http://127.0.0.1:8025, not a real inbox.
The header contains the single **Sign in / register** button. The account/vehicle
section does not duplicate it. Staff registration remains a separate employee
onboarding action requiring administrator approval.

## Start and sign in

```text
cd C:\Users\Pankil\Documents\ChatGPT\Parking_System
py scripts/start_dev.py
```

Keep the startup terminal open and visit http://127.0.0.1:5173. Sign out and back
in if you still have an old login screen open. Existing accounts/passwords remain.
Use separate browser profiles/sessions to test different roles simultaneously.

## Register and approve all account types

1. Signed-out visitors see only the product introduction. Select **Create account**.
2. Choose **Driver / user** or **Employee**, then complete registration and Mailpit
   email verification. Public registration cannot choose an administrator role.
3. Both types see **Your approval is pending** and no parking data or controls.
   Direct provider registration asks for account type on first return to the app.
4. Administrator: open **Account approvals**, review name/email/type, choose Approve
   or Reject, enter a reason, and save. For employees, select Attendant or Operator
   administrator for the selected location. Never grant admin privileges routinely.
5. Applicant clicks **Check approval status** or signs in again. Approved drivers
   get their vehicle/session pages; employees get only assigned location controls.
6. Administrator setup requires no approval: run
   `py scripts/grant_local_admin.py --email admin@gmail.com --create`, open the
   Mailpit setup email, verify email and choose a private password. Then sign in
   directly as administrator. Do not register the owner as a pending employee.
   Other accounts still need UI approval.

Employee selection grants no privileges. Existing vehicle/session history cannot
be converted into an employee identity. No personal vehicle under employee accounts.

## Staff: create a driver and register their vehicle

1. Sign in as staff, choose the assigned location, and open **Driver accounts & vehicles**.
2. Under **Create a driver account**, enter the driver's email, first name and last name.
3. Click **Create driver and send setup email**. Staff never chooses or sees the
   driver's password. If email fails, the account is retained; retry the same form.
4. The driver opens their setup email in Mailpit, verifies email and chooses their
   own password. Use a separate browser session from staff/admin.
5. The administrator first approves this new driver in **Account approvals**.
   Under **Find a driver to register or manage a vehicle**, enter the driver's name or exact
   email and click **Find driver**.
6. Complete **Register vehicle for this driver**, for example jurisdiction `IN-GJ`,
   registration `GJ08AB1234`, vehicle type Car, make Maruti, model Swift, color White.
7. Click **Save driver vehicle**. It belongs to the driver, not the signed-in staff.
   Only one enabled vehicle is allowed. Replacement preserves history and requires
   checkout first. The disable control is also blocked during active parking.

For an already-created driver, use Find driver. An account registered in Keycloak
but never signed into the parking app may need one first login before lookup.
Staff has no personal **My vehicle** page. Their pages are **Space occupancy**,
**Driver accounts & vehicles**, **Check in a vehicle**, and **Check out a vehicle**.

## Check-in, driver status, and checkout

1. Staff opens **Check in a vehicle**, enters exact jurisdiction/registration, and
   clicks **Find vehicle**. Select a compatible empty space and confirm actual arrival.
2. Staff **Space occupancy** shows floors, space labels and occupied/empty/out-of-service
   status, with authorized owner/vehicle details. Counts come from confirmed sessions.
3. Driver signs in using their email/password. **My dashboard** shows their space,
   location, arrival time and elapsed duration; **My vehicle** shows the vehicle saved
   by staff. Drivers cannot check themselves in/out.
4. Staff opens **Check out a vehicle** and confirms departure. The space becomes
   available, the driver's current session ends, and **My parking history** retains it.

Saving a vehicle does not reserve a space or start parking. Staff still confirms
physical arrival/departure; cameras/RFID remain future phase 8 work.

## Administrator

- **Drivers:** driver account/vehicle management; no staff-role controls.
- **Staff accounts:** pending employee requests and assigned employee roles only.
- **Floors & spaces / Location settings:** configuration and maintenance status.
- **Audit records:** authorized, searchable audit history.
- **Check-in / check-out:** parking operations at assigned locations.

Initial local owner bootstrap, after verified registration and first app login:
`py scripts/grant_local_admin.py --email YOUR_ADMIN_EMAIL`. No OTP is required in
local password-only mode. Use an employee account without an enabled driver vehicle.

## Checks

```text
py scripts/test_phase34.py
py scripts/test_phase34.py --password-only --test-name test_36 --test-name test_4
py scripts/pnpm.py build
```

The first command preserves the strict-MFA regression baseline in an isolated test
realm; it does not re-enable OTP in the normal parking realm. The second tests local
password-only mode, browser driver onboarding, staff applications and authorization.
All committed test data/realms remain for inspection. No automatic deletion occurs.

For optional runtime database accounts, refresh grants with
`py scripts/setup_runtime_db.py --refresh-grants`; credentials are unchanged.
The database viewer (`py scripts/view_database.py --start`, port 8090) is a read-only
development tool, separate from role workspaces.
