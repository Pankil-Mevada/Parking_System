"""Real browser checks of public introduction and pending account access."""
import os, secrets, uuid
from parking_tools import ROOT
from identity_flow import create_user, otp, REALM, login
from identity_admin import IDENTITY, admin_token, request

def journey(case):
    os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'.tools/browsers')
    from playwright.sync_api import sync_playwright, expect
    user=create_user('approval-browser-'+secrets.token_hex(5))
    artifacts=ROOT/'.tools/browser-results'/case.run_id
    artifacts.mkdir(parents=True,exist_ok=True)
    realm_url=IDENTITY+'/admin/realms/'+REALM
    registration=request(realm_url,token=admin_token())['registrationAllowed']
    request(realm_url,{'registrationAllowed':True},admin_token(),method='PUT')
    with sync_playwright() as p:
        browser=p.chromium.launch()
        try:
            page=browser.new_page(viewport={'width':1366,'height':900})
            def forward(route):
                path=route.request.url.split('127.0.0.1:5173',1)[1]
                try:route.fulfill(response=route.fetch(url='http://127.0.0.1:18080'+path))
                except Exception:
                    try:route.abort()
                    except Exception:pass
            page.route('**/api/**',forward)
            page.goto('http://127.0.0.1:5173/')
            expect(page.locator('#product-intro')).to_be_visible()
            expect(page.locator('#location-section')).to_be_hidden()
            expect(page.locator('#overview')).to_be_hidden()
            expect(page.get_by_role('button',name='Sign in / register',exact=True)).to_have_count(1)
            expect(page.get_by_role('button',name='Create account',exact=True)).to_have_count(0)
            page.screenshot(path=str(artifacts/'product-introduction.png'),full_page=True)
            page.locator('#header-login').click()
            page.locator('#kc-registration a').click()
            expect(page.locator('#email')).to_be_visible()
            # The same entry supports provider registration and existing login.
            page.goto('http://127.0.0.1:5173/')
            page.locator('#header-login').click()
            page.locator('#username').fill(user['username'])
            page.locator('#password').fill(user['password'])
            page.locator('#kc-login').click()
            if os.environ.get('PARKING_TEST_PASSWORD_ONLY')!='1':
                page.locator('#otp').fill(otp(user['secret']));page.locator('#kc-login').click()
            expect(page.get_by_role('heading',name='Complete your account setup',exact=True)).to_be_visible(timeout=20000)
            page.get_by_label('Requested access',exact=True).select_option('employee')
            page.get_by_label('Building / parking location',exact=True).select_option(case.location)
            page.get_by_role('button',name='Submit access request',exact=True).click()
            expect(page.get_by_role('heading',name='Waiting for staff access',exact=True)).to_be_visible(timeout=20000)
            expect(page.get_by_role('button',name='Check approval status',exact=True)).to_be_visible()
            expect(page.locator('#product-intro')).to_be_hidden()
            expect(page.get_by_role('button',name='Submit access request',exact=True)).to_have_count(0)
            expect(page.locator('#location-section')).to_be_hidden()
            expect(page.get_by_role('link',name='My vehicle',exact=True)).to_have_count(0)
            expect(page.get_by_role('link',name='Check in a vehicle',exact=True)).to_have_count(0)
            page.screenshot(path=str(artifacts/'pending-account.png'),full_page=True)
            case.assertEqual(case.db.execute('SELECT registration_kind,approval_status FROM users WHERE email=%s',(user['email'],)).fetchone(),('employee','pending'))
            page.set_viewport_size({'width':390,'height':844})
            case.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            admin_context=browser.new_context(viewport={'width':1366,'height':900})
            admin=admin_context.new_page();admin.route('**/api/**',forward)
            admin.goto('http://127.0.0.1:5173/');admin.locator('#header-login').click()
            account=case.identities[4]
            admin.locator('#username').fill(account['username']);admin.locator('#password').fill(account['password']);admin.locator('#kc-login').click()
            if os.environ.get('PARKING_TEST_PASSWORD_ONLY')!='1':
                admin.locator('#otp').fill(otp(account['secret']));admin.locator('#kc-login').click()
            admin.get_by_role('link',name='Account approvals',exact=True).click()
            decision=admin.locator('.request-card').filter(has_text=user['email']).locator('form')
            expect(decision).to_be_visible(timeout=20000)
            decision.locator('select').first.select_option('approved')
            decision.locator('select').last.select_option('attendant')
            decision.locator('[name=reason]').fill('Browser approval of registered employee')
            with admin.expect_response(lambda response:response.url.endswith('/approvals') and response.request.method=='POST') as saved:
                decision.get_by_role('button',name='Save decision',exact=True).click()
            case.assertEqual(saved.value.status,200)
            page.get_by_role('button',name='Check approval status',exact=True).click()
            expect(page.get_by_role('link',name='Check in a vehicle',exact=True)).to_be_visible(timeout=20000)
            expect(page.get_by_role('link',name='My vehicle',exact=True)).to_have_count(0)
            for access,title in [('driver','Waiting for driver approval'),('owner','Administrator access not activated yet')]:
                applicant=create_user('unified-'+access+'-'+secrets.token_hex(5))
                context=browser.new_context(viewport={'width':1366,'height':900})
                waiting=context.new_page();waiting.route('**/api/**',forward)
                waiting.goto('http://127.0.0.1:5173/');waiting.locator('#header-login').click()
                waiting.locator('#username').fill(applicant['username']);waiting.locator('#password').fill(applicant['password']);waiting.locator('#kc-login').click()
                if os.environ.get('PARKING_TEST_PASSWORD_ONLY')!='1':
                    waiting.locator('#otp').fill(otp(applicant['secret']));waiting.locator('#kc-login').click()
                waiting.get_by_label('Requested access',exact=True).select_option(access)
                waiting.get_by_label('Building / parking location',exact=True).select_option(case.location)
                waiting.get_by_role('button',name='Submit access request',exact=True).click()
                expect(waiting.get_by_role('heading',name=title,exact=True)).to_be_visible(timeout=20000)
                expect(waiting.get_by_role('link',name='My vehicle',exact=True)).to_have_count(0)
                expect(waiting.get_by_role('link',name='Account approvals',exact=True)).to_have_count(0)
                waiting.get_by_role('button',name='Check approval status',exact=True).click()
                expect(waiting.get_by_role('heading',name=title,exact=True)).to_be_visible()
                row=case.db.execute('SELECT id,registration_kind,approval_status FROM users WHERE email=%s',(applicant['email'],)).fetchone()
                case.assertEqual(row[1:],('employee' if access=='owner' else 'driver','pending'))
                case.assertEqual(case.scalar('SELECT count(*) FROM staff_assignments WHERE user_id=%s',(row[0],)),0)
                from test_phase34 import api
                applicant_token=login(applicant)['access_token']
                case.assertEqual(api(applicant_token,'/api/locations')[0],403)
                waiting.screenshot(path=str(artifacts/(access+'-pending.png')),full_page=True)
                if access=='owner':
                    case.assertEqual(api(applicant_token,'/api/me/registration','POST',{'kind':'administrator'})[0],400)
                    # Trusted fixture provisioning represents owner bootstrap;
                    # public registration and browser hints cannot do this.
                    case.db.execute("UPDATE users SET approval_status='approved' WHERE id=%s",(row[0],))
                    case.db.execute('INSERT INTO staff_accounts(email,user_id,location_id,created_by) VALUES(%s,%s,%s,%s)',
                                    (applicant['email'],row[0],case.location,case.users[4]))
                    case.db.execute("INSERT INTO staff_assignments(user_id,location_id,role) VALUES(%s,%s,'operator_admin')",(row[0],case.location))
                    case.db.execute("INSERT INTO audit_events(actor_id,action,target_type,target_id,request_id,sanitized_changes) VALUES(%s,'test_owner_setup','user',%s,%s,'{}')",
                                    (case.users[4],row[0],str(uuid.uuid4())))
                    waiting.get_by_role('button',name='Check approval status',exact=True).click()
                    expect(waiting.get_by_role('link',name='Account approvals',exact=True)).to_be_visible(timeout=20000)
                context.close()
        except Exception:
            page.screenshot(path=str(artifacts/'approval-failure.png'),full_page=True)
            raise
        finally:
            browser.close()
            request(realm_url,{'registrationAllowed':registration},admin_token(),method='PUT')
