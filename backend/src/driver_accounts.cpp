#include "driver_accounts.h"
#include <regex>

namespace parking {
Reply createDriver(Database &db,const Identity &actor,const drogon::HttpRequestPtr &req,const AuthConfig &config,const std::string &requestId) {
    std::smatch match;std::regex_match(req->path(),match,std::regex("/api/staff/locations/([^/]+)/drivers"));
    auto location=match[1].str();uuid(location);authorizeLocation(db,actor,location);
    auto body=parseJson(std::string(req->body()));fields(body,{"email","firstName","lastName"});
    auto email=required(body,"email",200),first=required(body,"firstName",100),last=required(body,"lastName",100);
    if(!std::regex_match(email,std::regex("[^\\s@]+@[^\\s@]+\\.[^\\s@]+")))throw ApiError(400,"invalid_email");
    auto key=req->getHeader("idempotency-key");if(key.empty() || key.size()>200)throw ApiError(400,"idempotency_key_required");
    if(config.driverSecret.empty())throw ApiError(503,"driver_account_service_not_configured");
    auto hash=sha256(jsonString(body)),operation="create_driver:"+location;
    db.begin();
    db.query("SELECT pg_advisory_xact_lock(hashtextextended($1,519))",{actor.user+operation+key});
    // Coordinate email ownership with login and employee enrollment.
    db.query("SELECT pg_advisory_xact_lock(hashtextextended(lower(btrim($1)),518))",{email});
    if(!db.query("SELECT id FROM users WHERE id=$1::uuid AND status='enabled' FOR UPDATE",{actor.user}).size())throw ApiError(403,"account_disabled");
    authorizeLocation(db,actor,location);
    auto stored=db.query("SELECT request_hash,result::text FROM idempotency_records WHERE actor_id=$1::uuid AND operation=$2 AND key=$3",{actor.user,operation,key});
    Json::Value result;
    if(stored.size()) {
        if(stored.get(0,"request_hash")!=hash)throw ApiError(409,"idempotency_key_reused");
        result=parseJson(stored.get(0,"result"));
        if(result["setupEmailSent"].asBool()){db.commit();return {200,result};}
    } else if(db.query("SELECT 1 FROM staff_accounts WHERE email=lower(btrim($1))",{email}).size() || db.query("SELECT 1 FROM users WHERE lower(btrim(email))=lower(btrim($1))",{email}).size())throw ApiError(409,"account_exists_find_driver_instead");
    auto client=drogon::HttpClient::newHttpClient(config.host);
    auto tokenRequest=drogon::HttpRequest::newHttpFormPostRequest();tokenRequest->setPath("/realms/"+config.realm+"/protocol/openid-connect/token");
    tokenRequest->setParameter("grant_type","client_credentials");tokenRequest->setParameter("client_id","parking-driver-provisioner");tokenRequest->setParameter("client_secret",config.driverSecret);
    auto tokenResponse=client->sendRequest(tokenRequest,5.);
    if(tokenResponse.first!=drogon::ReqResult::Ok || !tokenResponse.second || tokenResponse.second->statusCode()!=drogon::k200OK || !tokenResponse.second->getJsonObject())throw ApiError(503,"driver_account_service_unavailable");
    auto token=(*tokenResponse.second->getJsonObject())["access_token"].asString();if(token.empty())throw ApiError(503,"driver_account_service_unavailable");
    auto call=[&](drogon::HttpMethod method,const std::string &path,const Json::Value &data=Json::Value()) {
        auto request=drogon::HttpRequest::newHttpRequest();request->setMethod(method);request->setPath(path);request->setPathEncode(false);request->addHeader("Authorization","Bearer "+token);
        if(!data.isNull()){request->setContentTypeCode(drogon::CT_APPLICATION_JSON);request->setBody(jsonString(data));}
        auto response=client->sendRequest(request,5.);
        if(response.first!=drogon::ReqResult::Ok || !response.second)throw ApiError(503,"driver_account_service_unavailable");
        return response.second;
    };
    auto base="/admin/realms/"+config.realm+"/users";
    if(!stored.size()) {
        auto marker=sha256(actor.user+operation+key+hash);
        Json::Value user;user["username"]=email;user["email"]=email;user["firstName"]=first;user["lastName"]=last;user["enabled"]=true;user["emailVerified"]=false;
        user["requiredActions"]=Json::Value(Json::arrayValue);user["requiredActions"].append("VERIFY_EMAIL");user["requiredActions"].append("UPDATE_PASSWORD");
        user["attributes"]["parking_provision_request"]=Json::Value(Json::arrayValue);user["attributes"]["parking_provision_request"].append(marker);
        auto created=call(drogon::Post,base,user);
        if(created->statusCode()!=drogon::k201Created && created->statusCode()!=drogon::k409Conflict)throw ApiError(503,"driver_account_creation_failed");
        auto found=call(drogon::Get,base+"?email="+drogon::utils::urlEncode(email)+"&exact=true&max=2");
        auto users=found->getJsonObject();if(found->statusCode()!=drogon::k200OK || !users || !users->isArray() || users->size()!=1)throw ApiError(503,"driver_account_lookup_failed");
        const auto &provider=(*users)[0];
        if(created->statusCode()==drogon::k409Conflict && provider["attributes"]["parking_provision_request"][0].asString()!=marker)throw ApiError(409,"account_exists_find_driver_instead");
        auto subject=provider["id"].asString();uuid(subject);
        auto owner=db.query("INSERT INTO users(identity_provider_reference,display_name,email,registration_kind,registration_location_id) VALUES($1,$2,lower(btrim($3)),'driver',$4::uuid) RETURNING id::text",{config.issuer+"|"+subject,first+" "+last,email,location});
        result["userId"]=owner.get(0,"id");result["email"]=email;result["setupEmailSent"]=false;result["providerId"]=subject;
        Json::Value changes;changes["userId"]=result["userId"];
        db.query("INSERT INTO audit_events(actor_id,action,target_type,target_id,request_id,sanitized_changes) VALUES($1::uuid,'driver_account_created','location',$2::uuid,$3::uuid,$4::jsonb)",{actor.user,location,requestId,jsonString(changes)});
        db.query("INSERT INTO idempotency_records(actor_id,operation,key,request_hash,result,expires_at) VALUES($1::uuid,$2,$3,$4,$5::jsonb,now()+interval '24 hours')",{actor.user,operation,key,hash,jsonString(result)});
    }
    db.commit(); // Never delete the created account if email delivery fails.
    Json::Value actions(Json::arrayValue);actions.append("VERIFY_EMAIL");actions.append("UPDATE_PASSWORD");
    auto sent=call(drogon::Put,base+"/"+result["providerId"].asString()+"/execute-actions-email?client_id=parking-web&lifespan=900&redirect_uri="+drogon::utils::urlEncode(config.origin+"/"),actions);
    if(sent->statusCode()==drogon::k204NoContent) {
        result["setupEmailSent"]=true;
        db.query("UPDATE idempotency_records SET result=$4::jsonb WHERE actor_id=$1::uuid AND operation=$2 AND key=$3",{actor.user,operation,key,jsonString(result)});
    }
    return {200,result};
}
}
