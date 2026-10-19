#include "parking.h"
#include "dashboard.h"
#include <algorithm>
#include <regex>

namespace parking {
namespace {
void audit(Database &db, const Identity &actor, const std::string &action,
           const std::string &type, const std::string &target, const std::string &requestId) {
    db.query("INSERT INTO audit_events(actor_id,action,target_type,target_id,request_id) VALUES($1::uuid,$2,$3,$4::uuid,$5::uuid)",
             {actor.user,action,type,target,requestId});
}
void lockUsers(Database &db, const Identity &actor, const std::string &owner, bool requireOwnerEnabled = true) {
    auto users = db.query("SELECT id::text,status,approval_status FROM users WHERE id IN ($1::uuid,$2::uuid) ORDER BY id FOR UPDATE", {actor.user,owner});
    for (int i=0; i<users.size(); ++i)
        if (users.get(i,"status") != "enabled" && (requireOwnerEnabled || users.get(i,"id")==actor.user)) throw ApiError(409,"account_disabled");
    if (!users.size()) throw ApiError(404,"user_not_found");
    for(int i=0;i<users.size();++i)if(users.get(i,"id")==actor.user && users.get(i,"approval_status")!="approved")throw ApiError(403,"account_approval_pending");
}
Json::Value vehicleJson(const Rows &rows, int i) {
    Json::Value v;
    for (auto field : {"id","user_id","registration_jurisdiction","normalized_registration","vehicle_type","make","model","color"})
        v[field] = rows.null(i,field) ? Json::Value() : Json::Value(rows.get(i,field));
    return v;
}
Json::Value sessionJson(const Rows &rows, int i) {
    Json::Value v;
    for (auto field : {"id","user_id","vehicle_id","space_id","checked_in_at","checked_out_at","registration_snapshot","registration_jurisdiction_snapshot"})
        v[field] = rows.null(i,field) ? Json::Value() : Json::Value(rows.get(i,field));
    return v;
}
std::string optional(const Json::Value &body, const char *key) {
    if (!body.isMember(key)) return "";
    if (body[key].isString() && body[key].asString().empty()) return "";
    return required(body,key,100);
}
Reply vehicle(Database &db, const Identity &actor, const drogon::HttpRequestPtr &req, const std::string &requestId,const std::string &owner="",const std::string &location="") {
    auto ownerId=owner.empty()?actor.user:owner;
    if(!location.empty())authorizeLocation(db,actor,location);
    if (req->method() == drogon::Get) {
        auto rows = db.query("SELECT * FROM vehicles WHERE user_id=$1::uuid AND disabled_at IS NULL", {ownerId});
        Json::Value result; result["vehicle"] = rows.size() ? vehicleJson(rows,0) : Json::Value(); return {200,result};
    }
    auto body = parseJson(std::string(req->body()));
    fields(body,{"registrationJurisdiction","registration","vehicleType","make","model","color","disabled"});
    if (body.isMember("disabled") && !body["disabled"].isBool()) throw ApiError(400,"invalid_disabled");
    bool disable = body.get("disabled",false).asBool();
    if (!disable && body.isMember("disabled")) throw ApiError(400,"omit_disabled_for_registration");
    auto jurisdiction = disable ? "" : required(body,"registrationJurisdiction",64);
    auto registration = disable ? "" : required(body,"registration",64);
    auto type = disable ? "" : required(body,"vehicleType",20);
    if (!disable && type != "car" && type != "van" && type != "motorcycle") throw ApiError(400,"invalid_vehicle_type");
    auto make=optional(body,"make"), model=optional(body,"model"), color=optional(body,"color");
    if (disable && body.size() != 1) throw ApiError(400,"disable_requires_only_disabled");
    db.begin(); lockUsers(db,actor,ownerId);
    if(!location.empty())authorizeLocation(db,actor,location);
    if(!db.query("SELECT 1 FROM users WHERE id=$1::uuid",{ownerId}).size())throw ApiError(404,"driver_not_found");
    if(db.query("SELECT 1 FROM users WHERE id=$1::uuid AND approval_status='approved'",{ownerId}).size()==0)throw ApiError(409,"driver_approval_pending");
    if(!disable && db.query("SELECT 1 FROM staff_accounts WHERE user_id=$1::uuid",{ownerId}).size())throw ApiError(409,"staff_account_cannot_register_driver_vehicle");
    auto old = db.query("SELECT id::text FROM vehicles WHERE user_id=$1::uuid AND disabled_at IS NULL ORDER BY id FOR UPDATE",{ownerId});
    if (db.query("SELECT 1 FROM parking_sessions WHERE user_id=$1::uuid AND checked_out_at IS NULL",{ownerId}).size()) throw ApiError(409,"end_session_before_vehicle_change");
    if (old.size()) db.query("UPDATE vehicles SET disabled_at=now(),updated_at=now() WHERE id=$1::uuid",{old.get(0,"id")});
    Json::Value result;
    if (!disable) {
        auto rows = db.query("INSERT INTO vehicles(user_id,registration_jurisdiction,normalized_registration,vehicle_type,make,model,color) "
                             "VALUES($1::uuid,upper(btrim($2)),normalize_registration($3),$4,$5,$6,$7) RETURNING *",
                             {ownerId,jurisdiction,registration,type,make,model,color});
        result["vehicle"] = vehicleJson(rows,0); audit(db,actor,"vehicle_registered","vehicle",rows.get(0,"id"),requestId);
    } else {
        result["vehicle"] = Json::Value(); if (old.size()) audit(db,actor,"vehicle_disabled","vehicle",old.get(0,"id"),requestId);
    }
    db.commit(); return {200,result};
}
void outbox(Database &db, const Identity &actor, const std::string &space, const std::string &session,
            const std::string &action, const std::string &requestId) {
    auto rows = db.query("UPDATE spaces SET version=version+1,updated_at=now() WHERE id=$1::uuid RETURNING location_id::text,version::text",{space});
    Json::Value payload; payload["spaceId"]=space; payload["version"]=Json::Int64(std::stoll(rows.get(0,"version")));
    db.query("INSERT INTO outbox_events(location_id,aggregate_id,aggregate_version,event_type,payload) VALUES($1::uuid,$2::uuid,$3::bigint,$4,$5::jsonb)",
             {rows.get(0,"location_id"),space,rows.get(0,"version"),action,jsonString(payload)});
    audit(db,actor,action,"parking_session",session,requestId);
}
Reply parkingAction(Database &db, const Identity &actor, const drogon::HttpRequestPtr &req,
                    const std::string &requestId, bool checkout, const std::string &sessionId) {
    auto body = req->body().empty() ? Json::Value(Json::objectValue) : parseJson(std::string(req->body()));
    fields(body,checkout ? std::vector<std::string>{} : std::vector<std::string>{"vehicleId","spaceId","comment"});
    if(body.isMember("comment") && (!body["comment"].isString() || body["comment"].asString().size()>500))throw ApiError(400,"invalid_comment");
    auto key = req->getHeader("idempotency-key");
    if (key.empty() || key.size()>200 || !std::all_of(key.begin(),key.end(),[](unsigned char c){return c>=33 && c<=126;})) throw ApiError(400,"idempotency_key_required");
    if (staffMfaRequired() && !actor.mfa) throw ApiError(403,"staff_mfa_required");
    if (!db.query("SELECT 1 FROM staff_assignments WHERE user_id=$1::uuid LIMIT 1",{actor.user}).size()) throw ApiError(403,"location_access_denied");
    auto operation=checkout ? "check-out" : "check-in";
    auto hash=sha256(std::string(operation)+"|"+sessionId+"|"+jsonString(body));
    db.begin();
    db.query("SELECT pg_advisory_xact_lock(hashtextextended($1,0))",{actor.user+"|"+operation+"|"+key});
    auto stored=db.query("SELECT request_hash,result::text FROM idempotency_records WHERE actor_id=$1::uuid AND operation=$2 AND key=$3",{actor.user,operation,key});
    if (stored.size() && stored.get(0,"request_hash") != hash) throw ApiError(409,"idempotency_key_reused");
    std::string vehicleId,spaceId,owner;
    if (checkout) {
        uuid(sessionId);
        auto row=db.query("SELECT user_id::text,vehicle_id::text,space_id::text FROM parking_sessions WHERE id=$1::uuid",{sessionId});
        if (!row.size()) throw ApiError(404,"session_not_found");
        vehicleId=row.get(0,"vehicle_id"); spaceId=row.get(0,"space_id"); owner=row.get(0,"user_id");
    } else {
        vehicleId=required(body,"vehicleId",36); spaceId=required(body,"spaceId",36); uuid(vehicleId); uuid(spaceId);
        auto row=db.query("SELECT user_id::text FROM vehicles WHERE id=$1::uuid",{vehicleId});
        if (!row.size()) throw ApiError(404,"vehicle_not_found");
        owner=row.get(0,"user_id");
    }
    // Same lock order in check-in/out, replacement and maintenance: sorted users,
    // vehicle, space, active session; assignment stays shared-locked until commit.
    lockUsers(db,actor,owner,!checkout);
    if(!checkout && !db.query("SELECT 1 FROM users WHERE id=$1::uuid AND approval_status='approved'",{owner}).size())throw ApiError(409,"driver_approval_pending");
    auto v=db.query("SELECT * FROM vehicles WHERE id=$1::uuid FOR UPDATE",{vehicleId});
    auto s=db.query("SELECT location_id::text,operational_status,supported_vehicle_type FROM spaces WHERE id=$1::uuid FOR UPDATE",{spaceId});
    if (!s.size()) throw ApiError(404,"space_not_found");
    authorizeLocation(db,actor,s.get(0,"location_id"));
    if (stored.size()) {
        auto original=parseJson(stored.get(0,"result")); db.commit(); return {original["status"].asInt(),original["body"]};
    }
    Rows result = [&]() {
        if (checkout) {
            auto active=db.query("SELECT * FROM parking_sessions WHERE id=$1::uuid FOR UPDATE",{sessionId});
            if (!active.null(0,"checked_out_at")) throw ApiError(409,"session_already_closed");
            return db.query("UPDATE parking_sessions SET checked_out_at=clock_timestamp(),checked_out_by=$1::uuid WHERE id=$2::uuid RETURNING *",{actor.user,sessionId});
        }
        if (!v.size() || v.get(0,"user_id") != owner || !v.null(0,"disabled_at")) throw ApiError(409,"vehicle_not_enabled");
        if (s.get(0,"operational_status") != "enabled") throw ApiError(409,"space_out_of_service");
        if (s.get(0,"supported_vehicle_type") != v.get(0,"vehicle_type")) throw ApiError(409,"vehicle_incompatible");
        return db.query("INSERT INTO parking_sessions(user_id,vehicle_id,space_id,checked_in_by,registration_jurisdiction_snapshot,registration_snapshot) "
                        "VALUES($1::uuid,$2::uuid,$3::uuid,$4::uuid,$5,$6) RETURNING *",
                        {owner,vehicleId,spaceId,actor.user,v.get(0,"registration_jurisdiction"),v.get(0,"normalized_registration")});
    }();
    outbox(db,actor,spaceId,result.get(0,"id"),operation,requestId);
    if(!checkout){Json::Value changes;changes["comment"]=body.get("comment","");changes["vehicleId"]=vehicleId;changes["spaceId"]=spaceId;
        db.query("INSERT INTO audit_events(actor_id,action,target_type,target_id,request_id,sanitized_changes) VALUES($1::uuid,'gate_entry_approved','parking_session',$2::uuid,$3::uuid,$4::jsonb)",{actor.user,result.get(0,"id"),requestId,jsonString(changes)});}

    Json::Value response; response["session"]=sessionJson(result,0);
    Json::Value saved; saved["status"]=checkout ? 200 : 201; saved["body"]=response;
    db.query("INSERT INTO idempotency_records(actor_id,operation,key,request_hash,result,expires_at) VALUES($1::uuid,$2,$3,$4,$5::jsonb,now()+interval '24 hours')",
             {actor.user,operation,key,hash,jsonString(saved)});
    db.commit(); return {saved["status"].asInt(),response};
}
}
Reply execute(Database &db, const Identity &actor, const drogon::HttpRequestPtr &req, const std::string &requestId) {
    auto path=req->path();
    if(path=="/api/locations") {
        Json::Value result;result["locations"]=Json::Value(Json::arrayValue);
        auto rows=db.query("SELECT id::text,name FROM locations ORDER BY name,id LIMIT 100");
        for(int i=0;i<rows.size();++i){Json::Value item;item["id"]=rows.get(i,"id");item["name"]=rows.get(i,"name");result["locations"].append(item);}
        return {200,result};
    }
    std::smatch approvalMatch;
    if(std::regex_match(path,approvalMatch,std::regex("/api/(admin|staff)/locations/([^/]+)/approvals"))) {
        auto location=approvalMatch[2].str();bool administrator=approvalMatch[1].str()=="admin";uuid(location);Json::Value result;
        if(req->method()==drogon::Get) {
            authorizeLocation(db,actor,location,administrator);result["requests"]=Json::Value(Json::arrayValue);
            auto offset=req->getParameter("offset");if(offset.empty())offset="0";
            auto search=req->getParameter("search");
            if(offset.size()>6 || !std::all_of(offset.begin(),offset.end(),[](unsigned char c){return c>='0' && c<='9';}) || std::stoul(offset)>100000 || search.size()>200)throw ApiError(400,"invalid_approval_filter");
            auto state=req->getParameter("status");if(state.empty())state="pending";
            if(state!="pending" && state!="approved" && state!="rejected")throw ApiError(400,"invalid_approval_status");
            const std::string scope="registration_kind IS NOT NULL AND (registration_location_id=$1::uuid OR registration_location_id IS NULL) AND ($2='true' OR registration_kind='driver')";
            auto counts=db.query("SELECT approval_status,count(*)::text AS total FROM users WHERE "+scope+" GROUP BY approval_status",{location,administrator?"true":"false"});
            for(auto key:{"pending","approved","rejected"})result["counts"][key]=0;
            for(int i=0;i<counts.size();++i)result["counts"][counts.get(i,"approval_status")]=std::stoi(counts.get(i,"total"));
            auto rows=db.query("SELECT id::text,display_name,email,registration_kind,approval_status,(SELECT normalized_registration FROM vehicles WHERE user_id=users.id AND disabled_at IS NULL LIMIT 1) AS vehicle_registration,(SELECT sanitized_changes->>'reason' FROM audit_events WHERE target_id=users.id AND action='account_approval_decided' ORDER BY occurred_at DESC,id DESC LIMIT 1) AS decision_reason FROM users WHERE "+scope+" AND approval_status=$3 AND ($4='' OR strpos(lower(email),lower($4))>0 OR strpos(lower(display_name),lower($4))>0) ORDER BY created_at,id LIMIT 100 OFFSET $5::integer",{location,administrator?"true":"false",state,search,offset});
            for(int i=0;i<rows.size();++i){Json::Value item;for(auto key:{"id","display_name","email","registration_kind","approval_status","vehicle_registration","decision_reason"})item[key]=rows.get(i,key);result["requests"].append(item);}
            db.query("INSERT INTO audit_events(actor_id,action,target_type,target_id,request_id,sanitized_changes) VALUES($1::uuid,'approval_requests_read','location',$2::uuid,$3::uuid,'{}')",{actor.user,location,requestId});
        } else {
            auto body=parseJson(std::string(req->body()));fields(body,{"userId","decision","role","reason","verificationConfirmed"});auto target=required(body,"userId",36);uuid(target);auto reason=required(body,"reason",500);auto decision=required(body,"decision",20);
            if(decision!="approved" && decision!="rejected")throw ApiError(400,"invalid_decision");
            db.begin();lockUsers(db,actor,target);authorizeLocation(db,actor,location,administrator);
            auto row=db.query("SELECT registration_kind,approval_status,status,registration_location_id::text FROM users WHERE id=$1::uuid",{target});
            if(!row.size() || row.get(0,"approval_status")!="pending" || row.get(0,"registration_kind").empty() || row.get(0,"status")!="enabled")throw ApiError(409,"request_not_pending");
            if(!row.get(0,"registration_location_id").empty() && row.get(0,"registration_location_id")!=location)throw ApiError(403,"location_forbidden");
            if(!administrator && (row.get(0,"registration_kind")!="driver" || body.isMember("role")))throw ApiError(403,"driver_approval_only");
            if(!administrator && decision=="approved" && (!body["verificationConfirmed"].isBool() || !body["verificationConfirmed"].asBool()))throw ApiError(400,"driver_verification_required");
            if(decision=="approved" && row.get(0,"registration_kind")=="employee") {
                auto role=required(body,"role",30);if(role!="attendant" && role!="operator_admin")throw ApiError(400,"invalid_role");
                if(db.query("SELECT 1 FROM vehicles WHERE user_id=$1::uuid UNION ALL SELECT 1 FROM parking_sessions WHERE user_id=$1::uuid LIMIT 1",{target}).size())throw ApiError(409,"driver_history_requires_separate_employee_account");
                db.query("INSERT INTO staff_accounts(email,user_id,location_id,created_by) SELECT lower(btrim(email)),id,$2::uuid,$3::uuid FROM users WHERE id=$1::uuid ON CONFLICT(user_id) DO NOTHING",{target,location,actor.user});
                db.query("INSERT INTO staff_assignments(user_id,location_id,role) VALUES($1::uuid,$2::uuid,$3) ON CONFLICT(user_id,location_id) DO UPDATE SET role=excluded.role",{target,location,role});
            }
            db.query("UPDATE users SET approval_status=$2,registration_location_id=COALESCE(registration_location_id,$3::uuid) WHERE id=$1::uuid",{target,decision,location});
            db.query("INSERT INTO audit_events(actor_id,action,target_type,target_id,request_id,sanitized_changes) VALUES($1::uuid,'account_approval_decided','user',$2::uuid,$3::uuid,$4::jsonb)",{actor.user,target,requestId,jsonString(body)});db.commit();result["decision"]=decision;
        }
        return {200,result};
    }
    if (path=="/api/me/vehicle") return vehicle(db,actor,req,requestId);
    if (path=="/api/staff/check-ins") return parkingAction(db,actor,req,requestId,false,"");
    std::smatch match;
    if(std::regex_match(path,match,std::regex("/api/staff/locations/([^/]+)/drivers/([^/]+)/vehicle"))) {
        auto location=match[1].str(),owner=match[2].str();uuid(location);uuid(owner);return vehicle(db,actor,req,requestId,owner,location);
    }
    if (std::regex_match(path,match,std::regex("/api/staff/sessions/([^/]+)/check-out"))) return parkingAction(db,actor,req,requestId,true,match[1]);
    Json::Value response;
    if (path=="/api/me") {
        response["id"]=actor.user; response["mfa"]=actor.mfa; response["assignments"]=Json::Value(Json::arrayValue);
        response["staffMfaRequired"]=staffMfaRequired();
        auto profile=db.query("SELECT approval_status,registration_kind,registration_location_id::text FROM users WHERE id=$1::uuid",{actor.user});
        response["approvalStatus"]=profile.get(0,"approval_status");response["registrationKind"]=profile.get(0,"registration_kind");
        response["registrationLocationId"]=profile.get(0,"registration_location_id");
        response["accountType"]=db.query("SELECT 1 FROM staff_accounts WHERE user_id=$1::uuid",{actor.user}).size()?"staff":"driver";
        auto rows=db.query("SELECT location_id::text,role FROM staff_assignments WHERE user_id=$1::uuid ORDER BY location_id",{actor.user});
        for(int i=0;i<rows.size();++i) { Json::Value item; item["locationId"]=rows.get(i,"location_id"); item["role"]=rows.get(i,"role"); response["assignments"].append(item); }
    } else if(path=="/api/me/registration-locations") {
        response["locations"]=Json::Value(Json::arrayValue);
        auto rows=db.query("SELECT id::text,name FROM locations ORDER BY name,id LIMIT 100");
        for(int i=0;i<rows.size();++i){Json::Value item;item["id"]=rows.get(i,"id");item["name"]=rows.get(i,"name");response["locations"].append(item);}
    } else if(path=="/api/me/registration") {
        auto body=parseJson(std::string(req->body()));fields(body,{"kind","locationId"});auto kind=required(body,"kind",20);
        if(kind!="driver" && kind!="employee")throw ApiError(400,"invalid_account_kind");
        db.begin();
        auto row=db.query("SELECT registration_kind,approval_status FROM users WHERE id=$1::uuid FOR UPDATE",{actor.user});
        if(row.get(0,"approval_status")!="pending" || !row.get(0,"registration_kind").empty())throw ApiError(409,"registration_already_submitted");
        auto location=optional(body,"locationId");
        if(!location.empty()){uuid(location);if(!db.query("SELECT 1 FROM locations WHERE id=$1::uuid",{location}).size())throw ApiError(400,"invalid_location");}
        else {auto places=db.query("SELECT id::text FROM locations ORDER BY id LIMIT 2");if(places.size()==1)location=places.get(0,"id");}
        db.query("UPDATE users SET registration_kind=$2,registration_location_id=NULLIF($3,'')::uuid WHERE id=$1::uuid",{actor.user,kind,location});
        Json::Value change;change["kind"]=kind;
        db.query("INSERT INTO audit_events(actor_id,action,target_type,target_id,request_id,sanitized_changes) VALUES($1::uuid,'registration_submitted','user',$1::uuid,$2::uuid,$3::jsonb)",{actor.user,requestId,jsonString(change)});
        db.commit();response["pending"]=true;
    } else if(path=="/api/me/staff-application") {
        auto body=parseJson(std::string(req->body()));fields(body,{"locationId","reason"});
        auto location=required(body,"locationId",36);uuid(location);auto reason=required(body,"reason",500);
        db.begin();lockUsers(db,actor,actor.user);
        if(db.query("SELECT 1 FROM vehicles WHERE user_id=$1::uuid",{actor.user}).size() || db.query("SELECT 1 FROM parking_sessions WHERE user_id=$1::uuid",{actor.user}).size())throw ApiError(409,"driver_history_requires_separate_employee_account");
        auto email=db.query("SELECT lower(btrim(email)) AS email FROM users WHERE id=$1::uuid",{actor.user}).get(0,"email");
        db.query("INSERT INTO staff_accounts(email,user_id,location_id,created_by) VALUES($1,$2::uuid,$3::uuid,$2::uuid)",{email,actor.user,location});
        Json::Value changes;changes["reason"]=reason;
        db.query("INSERT INTO audit_events(actor_id,action,target_type,target_id,request_id,sanitized_changes) VALUES($1::uuid,'staff_access_requested','location',$2::uuid,$3::uuid,$4::jsonb)",{actor.user,location,requestId,jsonString(changes)});
        db.commit();response["requested"]=true;
    } else if (path=="/api/auth/logout") {
        db.query("INSERT INTO revoked_auth_sessions(provider_session_id,expires_at) VALUES($1,now()+interval '12 hours') ON CONFLICT DO NOTHING",{actor.session}); response["loggedOut"]=true;
    } else if (path=="/api/me/parking-session" || path=="/api/me/parking-history") {
        bool history=path=="/api/me/parking-history";
        auto offsetText=req->getParameter("offset");
        if (offsetText.empty()) offsetText="0";
        if (offsetText.size()>6 || !std::all_of(offsetText.begin(),offsetText.end(),[](unsigned char c){return c>='0' && c<='9';})) throw ApiError(400,"invalid_offset");
        auto rows=db.query("SELECT * FROM parking_sessions WHERE user_id=$1::uuid " + std::string(history ? "" : "AND checked_out_at IS NULL ") +
                           "ORDER BY checked_in_at DESC,id LIMIT 50 OFFSET $2::integer",{actor.user,offsetText});
        if (history) { response["sessions"]=Json::Value(Json::arrayValue); for(int i=0;i<rows.size();++i) response["sessions"].append(sessionJson(rows,i)); }
        else response["session"]=rows.size() ? sessionJson(rows,0) : Json::Value();
    } else if (std::regex_match(path,match,std::regex("/api/admin/locations/([^/]+)/staff"))) {
        auto location=match[1].str(); uuid(location);
        auto body=parseJson(std::string(req->body())); fields(body,{"userId","role","reason"});
        auto target=required(body,"userId",36); uuid(target);
        auto role=required(body,"role",20); auto reason=required(body,"reason",500);
        if(role!="attendant" && role!="operator_admin" && role!="none") throw ApiError(400,"invalid_role");
        db.begin(); lockUsers(db,actor,target); authorizeLocation(db,actor,location,true);
        if(!db.query("SELECT 1 FROM users WHERE id=$1::uuid",{target}).size()) throw ApiError(404,"user_not_found");
        if(role!="none" && !db.query("SELECT 1 FROM staff_accounts WHERE user_id=$1::uuid AND (location_id=$2::uuid OR EXISTS(SELECT 1 FROM staff_assignments WHERE user_id=$1::uuid AND location_id=$2::uuid))",{target,location}).size())throw ApiError(409,"driver_account_cannot_be_assigned_staff_role");
        if(role=="none") db.query("DELETE FROM staff_assignments WHERE user_id=$1::uuid AND location_id=$2::uuid",{target,location});
        else db.query("INSERT INTO staff_assignments(user_id,location_id,role) VALUES($1::uuid,$2::uuid,$3) ON CONFLICT(user_id,location_id) DO UPDATE SET role=excluded.role",{target,location,role});
        Json::Value changes; changes["userId"]=target; changes["role"]=role; changes["reason"]=reason;
        db.query("INSERT INTO audit_events(actor_id,action,target_type,target_id,request_id,sanitized_changes) VALUES($1::uuid,'staff_assignment','location',$2::uuid,$3::uuid,$4::jsonb)",{actor.user,location,requestId,jsonString(changes)});
        db.commit(); response["role"]=role;
    } else if (std::regex_match(path,match,std::regex("/api/staff/locations/([^/]+)/spaces"))) {
        auto location=match[1].str(); uuid(location); db.begin(); lockUsers(db,actor,actor.user); authorizeLocation(db,actor,location);
        auto rows=db.query("SELECT s.id::text,s.label,s.operational_status,p.id::text AS session_id,p.registration_snapshot,p.checked_in_at::text,u.display_name,u.email "
                           "FROM spaces s LEFT JOIN parking_sessions p ON p.space_id=s.id AND p.checked_out_at IS NULL LEFT JOIN users u ON u.id=p.user_id "
                           "WHERE s.location_id=$1::uuid ORDER BY s.label,s.id LIMIT 500",{location});
        response["spaces"]=Json::Value(Json::arrayValue);
        for(int i=0;i<rows.size();++i) {
            Json::Value item; for(auto field:{"id","label","operational_status","session_id","registration_snapshot","checked_in_at","display_name","email"}) item[field]=rows.null(i,field)?Json::Value():Json::Value(rows.get(i,field));
            item["occupancy"]=rows.null(i,"session_id")?"empty":"occupied"; response["spaces"].append(item);
        }
        audit(db,actor,"staff_spaces_read","location",location,requestId); db.commit();
    } else if (std::regex_match(path,match,std::regex("/api/admin/spaces/([^/]+)/status"))) {
        auto space=match[1].str(); uuid(space); auto body=parseJson(std::string(req->body())); fields(body,{"status","reason"});
        auto state=required(body,"status",20); auto reason=required(body,"reason",500);
        if (state!="enabled" && state!="out_of_service") throw ApiError(400,"invalid_status");
        db.begin(); lockUsers(db,actor,actor.user);
        auto row=db.query("SELECT location_id::text FROM spaces WHERE id=$1::uuid FOR UPDATE",{space});
        if(!row.size()) throw ApiError(404,"space_not_found");
        authorizeLocation(db,actor,row.get(0,"location_id"),true);
        if(db.query("SELECT 1 FROM parking_sessions WHERE space_id=$1::uuid AND checked_out_at IS NULL",{space}).size()) throw ApiError(409,"space_occupied");
        db.query("UPDATE spaces SET operational_status=$2 WHERE id=$1::uuid",{space,state});
        auto version=db.query("UPDATE spaces SET version=version+1,updated_at=now() WHERE id=$1::uuid RETURNING version::text",{space});
        Json::Value changes; changes["reason"]=reason; changes["status"]=state;
        db.query("INSERT INTO audit_events(actor_id,action,target_type,target_id,request_id,sanitized_changes) VALUES($1::uuid,'space_status','space',$2::uuid,$3::uuid,$4::jsonb)",{actor.user,space,requestId,jsonString(changes)});
        Json::Value event; event["spaceId"]=space; event["status"]=state;
        db.query("INSERT INTO outbox_events(location_id,aggregate_id,aggregate_version,event_type,payload) VALUES($1::uuid,$2::uuid,$3::bigint,'space_status',$4::jsonb)",{row.get(0,"location_id"),space,version.get(0,"version"),jsonString(event)});
        db.commit(); response["status"]=state;
    } else return dashboard(db,actor,req,requestId);
    return {200,response};
}
}
