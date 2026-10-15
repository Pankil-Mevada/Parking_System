"""Real browser checks of public introduction and pending account access."""
import os, secrets
from parking_tools import ROOT
from identity_flow import create_user, otp

def journey(case):
    os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'.tools/browsers')
    from playwright.sync_api import sync_playwright, expect
    user=create_user('approval-browser-'+secrets.token_hex(5))
    artifacts=ROOT/'.tools/browser-results'/case.run_id
    artifacts.mkdir(parents=True,exist_ok=True)
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
            page.screenshot(path=str(artifacts/'product-introduction.png'),full_page=True)
            page.get_by_role('button',name='Create account',exact=True).click()
            expect(page.get_by_label('I am registering as')).to_be_visible()
            page.get_by_label('I am registering as').select_option('employee')
            page.get_by_role('button',name='Cancel',exact=True).click()
            page.locator('#header-login').click()
            page.locator('#username').fill(user['username'])
            page.locator('#password').fill(user['password'])
            page.locator('#kc-login').click()
            if os.environ.get('PARKING_TEST_PASSWORD_ONLY')!='1':
                page.locator('#otp').fill(otp(user['secret']));page.locator('#kc-login').click()
            expect(page.get_by_role('heading',name='Your approval is pending',exact=True)).to_be_visible(timeout=20000)
            page.get_by_label('Account type',exact=True).select_option('employee')
            page.get_by_role('button',name='Submit for approval',exact=True).click()
            expect(page.get_by_role('heading',name='Your approval is pending',exact=True)).to_be_visible(timeout=20000)
            expect(page.get_by_role('button',name='Check approval status',exact=True)).to_be_visible()
            expect(page.locator('#product-intro')).to_be_hidden()
            expect(page.get_by_role('button',name='Submit for approval',exact=True)).to_have_count(0)
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
            decision=admin.get_by_role('heading',name='Synthetic Test · '+user['email']+' · employee',exact=True).locator('..')
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
        except Exception:
            page.screenshot(path=str(artifacts/'approval-failure.png'),full_page=True)
            raise
        finally:browser.close()
