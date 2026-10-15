"""Grant the dedicated confidential driver-provisioning client its server-only roles."""
from identity_admin import IDENTITY,admin_token,environment,request

def configure_driver_service(realm):
    token=admin_token();base=IDENTITY+'/admin/realms/'+realm
    clients=request(base+'/clients?clientId=parking-driver-provisioner',token=token)
    value={'clientId':'parking-driver-provisioner','publicClient':False,'secret':environment()['OIDC_DRIVER_ADMIN_SECRET'],'standardFlowEnabled':False,'directAccessGrantsEnabled':False,'serviceAccountsEnabled':True}
    if not clients:
        request(base+'/clients',value,token)
        clients=request(base+'/clients?clientId=parking-driver-provisioner',token=token)
    client=clients[0]['id'];request(base+'/clients/'+client,value,token,method='PUT')
    user=request(base+'/clients/'+client+'/service-account-user',token=token)['id']
    management=request(base+'/clients?clientId=realm-management',token=token)[0]['id']
    roles=[request(base+'/clients/'+management+'/roles/'+role,token=token) for role in ('manage-users','view-users')]
    request(base+'/users/'+user+'/role-mappings/clients/'+management,roles,token)
