"""Real Chromium + real Keycloak and parking APIs; test proxy routes only to the
isolated API ports instead of changing the development database. No mock data.
"""
import os
import time
from pathlib import Path
from parking_tools import ROOT
from identity_flow import otp, create_user, REALM
from identity_admin import IDENTITY
import secrets

def journey(case):
    # Fresh accounts ensure the browser consumes each authenticator code once.
    browser_driver=create_user('browser-driver-'+secrets.token_hex(6))
    browser_staff=create_user('browser-staff-'+secrets.token_hex(6))
    browser_admin=create_user('browser-admin-'+secrets.token_hex(6))
    staff_id=case.db.execute('INSERT INTO users(identity_provider_reference,display_name,email) VALUES(%s,%s,%s) RETURNING id',(IDENTITY+'/realms/'+REALM+'|'+browser_staff['id'],'Browser Staff',browser_staff['username'])).fetchone()[0]
    case.db.execute('INSERT INTO staff_accounts(email,user_id,location_id,created_by) VALUES(%s,%s,%s,%s)',(browser_staff['username'],staff_id,case.location,staff_id))
    case.db.execute("INSERT INTO staff_assignments(user_id,location_id,role) VALUES(%s,%s,'attendant')",(staff_id,case.location))
    admin_id=case.db.execute('INSERT INTO users(identity_provider_reference,display_name,email) VALUES(%s,%s,%s) RETURNING id',(IDENTITY+'/realms/'+REALM+'|'+browser_admin['id'],'Browser Admin',browser_admin['username'])).fetchone()[0]
    case.db.execute('INSERT INTO staff_accounts(email,user_id,location_id,created_by) VALUES(%s,%s,%s,%s)',(browser_admin['username'],admin_id,case.location,admin_id))
    case.db.execute("INSERT INTO staff_assignments(user_id,location_id,role) VALUES(%s,%s,'operator_admin')",(admin_id,case.location))
    os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'.tools/browsers')
    from playwright.sync_api import sync_playwright, expect
    artifacts=ROOT/'.tools/browser-results'/case.run_id
    artifacts.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch()
        try:
            driver=browser.new_context(viewport={'width':1280,'height':900})
            staff=browser.new_context(viewport={'width':1280,'height':900})
            admin_context=browser.new_context(viewport={'width':1280,'height':900})
            disconnected={'driver':False}
            def open_page(context,user,peer=False):
                page=context.new_page()
                def forward(route):
                    # route.fetch is an out-of-browser proxy and does not inherit
                    # browser offline mode. Abort the proxy too during this outage.
                    if context is driver and disconnected['driver']:
                        route.abort('internetdisconnected');return
                    path=route.request.url.split('127.0.0.1:5173',1)[1]
                    upstream='http://127.0.0.1:'+('18081' if peer else '18080')
                    try:
                        response=route.fetch(url=upstream+path)
                        route.fulfill(response=response)
                    except Exception:
                        # Browser shutdown/offline can cancel a routed request.
                        # Never print Playwright's request dump (contains bearer headers).
                        try:route.abort('failed')
                        except Exception:pass
                page.route('**/api/**',forward)
                page.goto('http://127.0.0.1:5173/')
                page.locator('#account-login').click()
                page.locator('#username').fill(user['username'])
                page.locator('#password').fill(user['password'])
                page.locator('#kc-login').click()
                if os.environ.get('PARKING_TEST_PASSWORD_ONLY')!='1':
                    page.locator('#otp').fill(otp(user['secret']))
                    page.locator('#kc-login').click()
                expect(page.locator('#account-message')).to_contain_text('Signed in',timeout=20000)
                expect(page.locator('.parking-workspace')).to_be_visible()
                return page
            d=open_page(driver,browser_driver)
            expect(d.get_by_role('link',name='Staff accounts',exact=True)).to_have_count(0)
            d.get_by_role('link',name='My vehicle',exact=True).click()
            d.locator('#vehicle-open').click()
            expect(d.locator('#vehicle-dialog')).to_be_visible()
            d.locator('[name=registrationJurisdiction]').fill('TEST')
            d.locator('[name=registration]').fill('BROWSER123')
            d.locator('[name=make]').fill('Synthetic')
            d.locator('[name=model]').fill('Browser car')
            d.locator('[name=color]').fill('Blue')
            # Keyboard-accessible native dialog: Escape closes, opening again restores fields.
            d.keyboard.press('Escape')
            expect(d.locator('#vehicle-dialog')).not_to_be_visible()
            d.locator('#vehicle-open').click()
            d.get_by_role('button',name='Save registered vehicle',exact=True).click()
            expect(d.locator('#account-vehicle')).to_contain_text('BROWSER123')
            d.get_by_role('link',name='My dashboard',exact=True).click()
            expect(d.locator('#account-section')).not_to_be_visible()
            expect(d.locator('.staff-panel')).not_to_be_visible()
            s=open_page(staff,browser_staff,peer=True)
            s.get_by_label('Switch workspace',exact=True).select_option('attendant')
            expect(s.locator('.workspace-status')).to_contain_text('Connected',timeout=15000)
            expect(s.get_by_role('link',name='Staff accounts',exact=True)).to_have_count(0)
            s.get_by_role('link',name='Check in a vehicle',exact=True).click()
            lookup=s.get_by_role('heading',name='Check in a registered vehicle').locator('..')
            lookup.locator('[name=jurisdiction]').fill('TEST')
            lookup.locator('[name=registration]').fill('BROWSER123')
            lookup.get_by_role('button',name='Find vehicle').click()
            s.get_by_role('button',name='Confirm check-in…').click()
            start=time.monotonic()
            s.get_by_role('dialog',name='Confirm parking action').get_by_role('button',name='Confirm',exact=True).click()
            expect(d.locator('.session-panel')).to_contain_text('BROWSER123',timeout=10000)
            arrival=time.monotonic()-start
            s.get_by_role('link',name='Space occupancy',exact=True).click()
            expect(s.locator('.space-card.occupied')).to_contain_text('BROWSER123')
            # Disconnect a real browser client, then verify committed state is recovered.
            disconnected['driver']=True;driver.set_offline(True)
            expect(d.locator('.workspace-status')).to_contain_text('Disconnected',timeout=10000)
            s.get_by_role('link',name='Check out a vehicle',exact=True).click()
            s.get_by_role('button',name='Check out',exact=True).click()
            s.get_by_role('dialog',name='Confirm parking action').get_by_role('button',name='Confirm',exact=True).click()
            expect(s.locator('.space-card.occupied')).to_have_count(0)
            disconnected['driver']=False;driver.set_offline(False)
            expect(d.locator('.session-panel')).to_contain_text('not currently parked',timeout=20000)
            d.get_by_role('link',name='My parking history',exact=True).click()
            expect(d.get_by_role('heading',name='Your parking history').locator('..')).to_contain_text('BROWSER123')
            d.screenshot(path=str(artifacts/'driver-desktop.png'),full_page=True)
            s.screenshot(path=str(artifacts/'staff-desktop.png'),full_page=True)
            d.set_viewport_size({'width':390,'height':844})
            d.screenshot(path=str(artifacts/'driver-mobile.png'),full_page=True)
            assert d.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile page overflows viewport'
            if os.environ.get('PARKING_TEST_PASSWORD_ONLY')=='1':
                from identity_flow import captured_action_link
                from identity_admin import request,admin_token
                email='browser-created-'+secrets.token_hex(6)+'@example.test'
                s.get_by_role('link',name='Driver accounts & vehicles',exact=True).click()
                expect(s.get_by_role('link',name='My vehicle',exact=True)).to_have_count(0)
                create=s.get_by_role('heading',name='Create a driver account',exact=True).locator('..')
                create.locator('[name=email]').fill(email);create.locator('[name=firstName]').fill('Synthetic');create.locator('[name=lastName]').fill('New driver')
                create.get_by_role('button',name='Create driver and send setup email',exact=True).click()
                expect(s.locator('.staff-panel')).to_contain_text('Driver account created.',timeout=15000)
                find=s.get_by_role('heading',name='Find a driver to register or manage a vehicle',exact=True).locator('..')
                find.locator('[name=email]').fill(email);find.get_by_role('button',name='Find driver',exact=True).click()
                registration=s.get_by_role('heading',name='Register vehicle for this driver',exact=True).locator('..')
                registration.locator('[name=registrationJurisdiction]').fill('TEST');registration.locator('[name=registration]').fill('ONBOARD987')
                registration.get_by_role('button',name='Save driver vehicle',exact=True).click()
                expect(registration).to_contain_text('Saved by the server.')
                # Actual Mailpit action link: driver verifies email and sets a private password.
                setup_context=browser.new_context();setup=setup_context.new_page()
                setup.goto(captured_action_link({'username':email}))
                password=secrets.token_urlsafe(24);password_set=False
                for _ in range(5):
                    if setup.locator('[name=password-new]').count():
                        setup.locator('[name=password-new]').fill(password);setup.locator('[name=password-confirm]').fill(password)
                        setup.locator('input[type=submit],button[type=submit]').first.click();password_set=True;break
                    links=setup.locator('a[href*="/login-actions/"]')
                    if links.count():links.first.click()
                    else:break
                assert password_set,'Driver password-setup form was not reached'
                provider=request(IDENTITY+'/admin/realms/'+REALM+'/users?email='+email+'&exact=true',token=admin_token())[0]
                assert provider['emailVerified'],'Driver setup did not verify the email'
                new_context=browser.new_context(viewport={'width':1280,'height':900})
                new_driver=open_page(new_context,{'username':email,'password':password})
                new_driver.get_by_role('link',name='My vehicle',exact=True).click()
                expect(new_driver.locator('#account-vehicle')).to_contain_text('ONBOARD987')
                new_driver.get_by_role('link',name='My dashboard',exact=True).click()
                s.get_by_role('link',name='Check in a vehicle',exact=True).click()
                lookup=s.get_by_role('heading',name='Check in a registered vehicle',exact=True).locator('..')
                lookup.locator('[name=jurisdiction]').fill('TEST');lookup.locator('[name=registration]').fill('ONBOARD987');lookup.get_by_role('button',name='Find vehicle',exact=True).click()
                s.get_by_role('button',name='Confirm check-in…',exact=True).click()
                s.get_by_role('dialog',name='Confirm parking action').get_by_role('button',name='Confirm',exact=True).click()
                expect(new_driver.locator('.session-panel')).to_contain_text('ONBOARD987',timeout=10000)
                s.get_by_role('link',name='Check out a vehicle',exact=True).click();s.get_by_role('button',name='Check out',exact=True).click()
                s.get_by_role('dialog',name='Confirm parking action').get_by_role('button',name='Confirm',exact=True).click()
                expect(new_driver.locator('.session-panel')).to_contain_text('not currently parked',timeout=10000)
                s.get_by_role('link',name='Driver accounts & vehicles',exact=True).click()
                s.screenshot(path=str(artifacts/'staff-driver-onboarding.png'),full_page=True)
            a=open_page(admin_context,browser_admin)
            a.get_by_label('Switch workspace',exact=True).select_option('operator_admin')
            expect(a.locator('.workspace-status')).to_contain_text('Connected',timeout=15000)
            expect(a.get_by_role('link',name='Audit records',exact=True)).to_be_visible()
            a.get_by_role('link',name='Floors & spaces',exact=True).click()
            expect(a.get_by_role('heading',name='Location settings',exact=True,level=3)).not_to_be_visible()
            floor_form=a.get_by_role('heading',name='Add a floor / zone',exact=True).locator('..')
            floor_form.locator('[name=label]').fill('Browser first floor')
            floor_form.locator('[name=reason]').fill('Browser acceptance test')
            floor_form.get_by_role('button',name='Save',exact=True).click()
            expect(a.get_by_label('Floor filter')).to_contain_text('Browser first floor')
            add_space=a.get_by_role('heading',name='Add a numbered space',exact=True).locator('..')
            expect(add_space.locator('[name=zoneId]')).to_contain_text('Browser first floor')
            add_space.locator('[name=label]').fill('B-01')
            add_space.locator('[name=reason]').fill('Browser acceptance test')
            add_space.get_by_role('button',name='Save',exact=True).click()
            expect(a.locator('.space-grid')).to_contain_text('B-01')
            a.get_by_role('link',name='Location settings',exact=True).click()
            expect(a.get_by_role('heading',name='Location settings',exact=True,level=3)).to_be_visible()
            expect(a.get_by_role('heading',name='Add a floor / zone',exact=True)).not_to_be_visible()
            a.get_by_role('link',name='Drivers',exact=True).click()
            expect(a.get_by_role('heading',name='Find a user / vehicle',exact=True)).to_be_visible()
            find_driver=a.get_by_role('heading',name='Find a user / vehicle',exact=True).locator('..')
            find_driver.locator('[name=email]').fill(browser_driver['email'])
            find_driver.get_by_role('button',name='Find user',exact=True).click()
            expect(a.locator('.admin-panel div[data-view=drivers]')).to_contain_text('BROWSER123')
            expect(a.locator('.admin-panel [data-view=drivers] select[name=role]')).to_have_count(0)
            a.get_by_role('link',name='Staff accounts',exact=True).click()
            expect(a.get_by_role('heading',name='Approve a new staff account',exact=True)).to_be_visible()
            expect(a.get_by_role('heading',name='Find a user / vehicle',exact=True)).not_to_be_visible()
            employee=create_user('browser-employee-'+secrets.token_hex(6))
            employee_email=employee['email']
            employee_context=browser.new_context(viewport={'width':1280,'height':900})
            e=open_page(employee_context,employee)
            e.get_by_role('link',name='My vehicle',exact=True).click()
            e.get_by_role('button',name='Request staff access (employees only)',exact=True).click()
            application=e.get_by_role('dialog',name='Request staff access',exact=True)
            application.get_by_label('Work location',exact=True).select_option(case.location)
            application.get_by_label('Reason / employee details',exact=True).fill('Synthetic staff application after registration')
            application.get_by_role('button',name='Send staff access request',exact=True).click()
            expect(application).to_contain_text('Staff request saved.')
            application.get_by_role('button',name='Close',exact=True).click()
            e.get_by_role('button',name='Refresh now',exact=True).click()
            expect(e.locator('.workspace-status')).to_contain_text('ask your administrator to assign a location role')
            expect(e.locator('#vehicle-open')).not_to_be_visible()
            a.get_by_role('button',name='Refresh now',exact=True).click()
            expect(a.get_by_role('heading',name='Location role for '+employee_email,exact=True)).to_be_visible(timeout=20000)
            employee_role=a.get_by_role('heading',name='Location role for '+employee_email,exact=True).locator('..')
            employee_role.locator('select[name=role]').select_option('attendant')
            employee_role.locator('[name=reason]').fill('Synthetic employee location assignment')
            with a.expect_response(lambda response: response.url.endswith('/staff') and response.request.method=='POST') as assigned:
                employee_role.get_by_role('button',name='Save',exact=True).click()
            assert assigned.value.status==200, 'Employee role was not confirmed by the server'
            expect(a.get_by_role('heading',name='Employee accounts and location roles').locator('..')).to_contain_text('attendant')
            e.get_by_role('button',name='Refresh now',exact=True).click()
            expect(e.locator('.workspace-status')).to_contain_text('Connected',timeout=20000)
            expect(e.get_by_role('link',name='My vehicle',exact=True)).to_have_count(0)
            expect(e.get_by_role('link',name='Check in a vehicle',exact=True)).to_be_visible()
            a.get_by_role('link',name='Audit records',exact=True).click()
            expect(a.get_by_role('heading',name='Search audit records',exact=True)).to_be_visible()
            expect(a.get_by_role('heading',name='Find a user / vehicle',exact=True)).not_to_be_visible()
            a.get_by_role('link',name='Floors & spaces',exact=True).click()
            a.evaluate('window.scrollTo(0,0)')
            a.screenshot(path=str(artifacts/'admin-desktop.png'),full_page=True)
            s.set_viewport_size({'width':390,'height':844})
            s.screenshot(path=str(artifacts/'staff-mobile.png'),full_page=True)
            assert s.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Staff mobile page overflows viewport'
            print(f'Browser arrival confirmation -> driver update: {arrival:.3f}s (local Chromium, two API instances)')
        except Exception:
            for index,context in enumerate(browser.contexts):
                for page in context.pages:
                    try:page.screenshot(path=str(artifacts/f'failure-context-{index}.png'),full_page=True)
                    except Exception:pass
            raise
        finally:
            browser.close()
