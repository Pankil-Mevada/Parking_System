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
    case.db.execute("INSERT INTO staff_assignments(user_id,location_id,role) VALUES(%s,%s,'attendant')",(staff_id,case.location))
    admin_id=case.db.execute('INSERT INTO users(identity_provider_reference,display_name,email) VALUES(%s,%s,%s) RETURNING id',(IDENTITY+'/realms/'+REALM+'|'+browser_admin['id'],'Browser Admin',browser_admin['username'])).fetchone()[0]
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
                    response=route.fetch(url=upstream+path)
                    route.fulfill(response=response)
                page.route('**/api/**',forward)
                page.goto('http://127.0.0.1:5173/')
                page.locator('#account-login').click()
                page.locator('#username').fill(user['username'])
                page.locator('#password').fill(user['password'])
                page.locator('#kc-login').click()
                page.locator('#otp').fill(otp(user['secret']))
                page.locator('#kc-login').click()
                expect(page.locator('#account-message')).to_contain_text('Signed in',timeout=20000)
                expect(page.locator('.parking-workspace')).to_be_visible()
                return page
            d=open_page(driver,browser_driver)
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
            s=open_page(staff,browser_staff,peer=True)
            s.get_by_label('Dashboard role').select_option('attendant')
            expect(s.locator('.workspace-status')).to_contain_text('Connected',timeout=15000)
            lookup=s.get_by_role('heading',name='Check in a registered vehicle').locator('..')
            lookup.locator('[name=jurisdiction]').fill('TEST')
            lookup.locator('[name=registration]').fill('BROWSER123')
            lookup.get_by_role('button',name='Find vehicle').click()
            s.get_by_role('button',name='Confirm check-in…').click()
            start=time.monotonic()
            s.get_by_role('dialog',name='Confirm parking action').get_by_role('button',name='Confirm',exact=True).click()
            expect(d.locator('.session-panel')).to_contain_text('BROWSER123',timeout=10000)
            arrival=time.monotonic()-start
            expect(s.locator('.space-card.occupied')).to_contain_text('BROWSER123')
            # Disconnect a real browser client, then verify committed state is recovered.
            disconnected['driver']=True;driver.set_offline(True)
            expect(d.locator('.workspace-status')).to_contain_text('Disconnected',timeout=10000)
            s.get_by_role('button',name='Check out',exact=True).click()
            s.get_by_role('dialog',name='Confirm parking action').get_by_role('button',name='Confirm',exact=True).click()
            expect(s.locator('.space-card.occupied')).to_have_count(0)
            disconnected['driver']=False;driver.set_offline(False)
            expect(d.locator('.session-panel')).to_contain_text('not currently parked',timeout=20000)
            expect(d.get_by_role('heading',name='Your parking history').locator('..')).to_contain_text('BROWSER123')
            d.screenshot(path=str(artifacts/'driver-desktop.png'),full_page=True)
            s.screenshot(path=str(artifacts/'staff-desktop.png'),full_page=True)
            d.set_viewport_size({'width':390,'height':844})
            d.screenshot(path=str(artifacts/'driver-mobile.png'),full_page=True)
            assert d.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile page overflows viewport'
            a=open_page(admin_context,browser_admin)
            a.get_by_label('Dashboard role').select_option('operator_admin')
            expect(a.locator('.workspace-status')).to_contain_text('Connected',timeout=15000)
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
