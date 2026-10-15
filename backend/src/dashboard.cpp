#include "dashboard.h"
#include <algorithm>
#include <regex>

namespace parking {
namespace {
Json::Value objects(const Rows &rows, std::initializer_list<const char *> fields) {
    Json::Value list(Json::arrayValue);
    for(int i=0;i<rows.size();++i) {
        Json::Value item;
        for(auto field:fields) item[field]=rows.null(i,field)?Json::Value():Json::Value(rows.get(i,field));
        list.append(item);
    }
    return list;
}
std::string boundedNumber(std::string text, const char *error, size_t length=6) {
    if(text.empty()) return "0";
    if(text.size()>length || !std::all_of(text.begin(),text.end(),[](unsigned char c){return c>='0' && c<='9';})) throw ApiError(400,error);
    return text;
}
void record(Database &db,const Identity &actor,const std::string &action,const std::string &type,
            const std::string &target,const std::string &requestId,Json::Value changes=Json::Value(Json::objectValue)) {
    db.query("INSERT INTO audit_events(actor_id,action,target_type,target_id,request_id,sanitized_changes) VALUES($1::uuid,$2,$3,$4::uuid,$5::uuid,$6::jsonb)",
             {actor.user,action,type,target,requestId,jsonString(changes)});
}
void lockActor(Database &db,const Identity &actor) {
    auto row=db.query("SELECT status FROM users WHERE id=$1::uuid FOR UPDATE",{actor.user});
    if(!row.size() || row.get(0,"status")!="enabled") throw ApiError(403,"account_disabled");
}
void notify(Database &db,const std::string &space) {
    auto row=db.query("UPDATE spaces SET version=version+1,updated_at=now() WHERE id=$1::uuid RETURNING location_id::text,version::text",{space});
    if(row.size()) db.query("INSERT INTO outbox_events(location_id,aggregate_id,aggregate_version,event_type,payload) VALUES($1::uuid,$2::uuid,$3::bigint,'configuration','{}')",
                          {row.get(0,"location_id"),space,row.get(0,"version")});
}
}
void publishOutbox(Database &db) {
    db.begin();
    // Only one publisher assigns delivery cursors at a time. A late commit with
    // a lower outbox ID is picked up on the next pass without being skipped.
    db.query("SELECT pg_advisory_xact_lock(726193006)");
    auto pending=db.query("SELECT id::text,location_id::text,aggregate_id::text,aggregate_version::text FROM outbox_events WHERE published_at IS NULL ORDER BY id LIMIT 500 FOR UPDATE");
    for(int i=0;i<pending.size();++i) {
        db.query("INSERT INTO delivery_events(outbox_id,location_id,aggregate_id,aggregate_version) VALUES($1::bigint,$2::uuid,$3::uuid,$4::bigint) ON CONFLICT(outbox_id) DO NOTHING",
                 {pending.get(i,"id"),pending.get(i,"location_id"),pending.get(i,"aggregate_id"),pending.get(i,"aggregate_version")});
        db.query("UPDATE outbox_events SET published_at=now(),attempts=attempts+1 WHERE id=$1::bigint",{pending.get(i,"id")});
    }
    db.commit();
}
Reply dashboard(Database &db,const Identity &actor,const drogon::HttpRequestPtr &req,const std::string &requestId) {
    auto path=req->path(); std::smatch match; Json::Value result;
    if(path=="/api/me/dashboard") {
        auto rows=db.query("SELECT p.id::text,p.space_id::text,p.checked_in_at::text,p.checked_out_at::text,p.registration_snapshot,s.label AS space,z.label AS floor,l.name AS location FROM parking_sessions p JOIN spaces s ON s.id=p.space_id LEFT JOIN zones z ON z.id=s.zone_id JOIN locations l ON l.id=s.location_id WHERE p.user_id=$1::uuid ORDER BY p.checked_in_at DESC,p.id LIMIT 50 OFFSET $2::integer",{actor.user,boundedNumber(req->getParameter("offset"),"invalid_offset")});
        result["history"]=objects(rows,{"id","space_id","checked_in_at","checked_out_at","registration_snapshot","space","floor","location"});
        auto current=db.query("SELECT p.id::text,p.space_id::text,p.checked_in_at::text,p.checked_out_at::text,p.registration_snapshot,s.label AS space,z.label AS floor,l.name AS location FROM parking_sessions p JOIN spaces s ON s.id=p.space_id LEFT JOIN zones z ON z.id=s.zone_id JOIN locations l ON l.id=s.location_id WHERE p.user_id=$1::uuid AND p.checked_out_at IS NULL",{actor.user});
        result["current"]=current.size()?objects(current,{"id","space_id","checked_in_at","checked_out_at","registration_snapshot","space","floor","location"})[0]:Json::Value();
        return {200,result};
    }
    if(path=="/api/admin/locations" && req->method()==drogon::Post) {
        auto body=parseJson(std::string(req->body())); fields(body,{"name","timezone","reason"});
        auto name=required(body,"name",200),timezone=required(body,"timezone",100); required(body,"reason",500);
        db.begin(); lockActor(db,actor);
        if(!actor.mfa || !db.query("SELECT 1 FROM staff_assignments WHERE user_id=$1::uuid AND role='operator_admin' FOR SHARE",{actor.user}).size()) throw ApiError(403,"administrator_required");
        if(!db.query("SELECT 1 FROM pg_timezone_names WHERE name=$1",{timezone}).size()) throw ApiError(400,"invalid_timezone");
        auto row=db.query("INSERT INTO locations(name,timezone) VALUES($1,$2) RETURNING id::text",{name,timezone}); auto id=row.get(0,"id");
        db.query("INSERT INTO staff_assignments(user_id,location_id,role) VALUES($1::uuid,$2::uuid,'operator_admin')",{actor.user,id});
        record(db,actor,"location_created","location",id,requestId,body); db.commit(); result["id"]=id; return {201,result};
    }
    if(!std::regex_match(path,match,std::regex("/api/(locations|staff/locations|admin/locations)/([^/]+)/(dashboard|events|vehicles|configuration|zones|spaces|audit|staff-list|users)"))) throw ApiError(404,"not_found");
    auto scope=match[1].str(), location=match[2].str(),operation=match[3].str(); uuid(location);
    if(!db.query("SELECT 1 FROM locations WHERE id=$1::uuid",{location}).size()) throw ApiError(404,"location_not_found");
    bool staff=scope!="locations", admin=scope=="admin/locations";
    if(staff) { db.begin(); lockActor(db,actor); authorizeLocation(db,actor,location,admin); }
    if(operation=="dashboard" || operation=="events") {
        if(staff) db.commit();
        publishOutbox(db);
        db.begin(); db.query("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ");
        if(staff) authorizeLocation(db,actor,location,admin);
        auto cursor=db.query("SELECT coalesce(max(id),0)::text AS cursor FROM delivery_events").get(0,"cursor");
        result["cursor"]=cursor;
        result["locationId"]=location;
        result["timestamp"]=db.query("SELECT now()::text AS time").get(0,"time");
        if(operation=="events") {
            auto after=boundedNumber(req->getParameter("after"),"invalid_cursor",18);
            // Replay the newest 1000 location events; older/future cursors force a snapshot.
            auto boundary=db.query("SELECT coalesce(min(id),0)::text AS boundary FROM (SELECT id FROM delivery_events WHERE location_id=$1::uuid ORDER BY id DESC LIMIT 1000) e",{location}).get(0,"boundary");
            result["reset"]=std::stoll(after)>std::stoll(cursor) || (std::stoll(boundary)>0 && std::stoll(after)<std::stoll(boundary)-1);
            result["events"]=Json::Value(Json::arrayValue);
            if(!result["reset"].asBool()) {
                auto events=db.query("SELECT id::text,aggregate_id::text,aggregate_version::text,occurred_at::text FROM delivery_events WHERE location_id=$1::uuid AND id>$2::bigint ORDER BY id LIMIT 100",{location,after});
                result["events"]=objects(events,{"id","aggregate_id","aggregate_version","occurred_at"});
                if(!staff) {
                    // Drivers receive location-level invalidations, never another
                    // driver's individual space identifier or resource version.
                    for(auto &event:result["events"]) {
                        event["aggregate_id"]=location;
                        event["aggregate_version"]=event["id"];
                    }
                }
                // Do not jump past a page of events.
                if(events.size()==100) result["cursor"]=events.get(99,"id");
            }
        } else {
            auto floors=db.query("SELECT z.id::text,z.label,count(s.id) FILTER(WHERE s.operational_status='enabled')::text AS capacity,count(p.id)::text AS occupied,count(s.id) FILTER(WHERE s.operational_status='out_of_service')::text AS out_of_service,(count(s.id) FILTER(WHERE s.operational_status='enabled')-count(p.id))::text AS available FROM zones z LEFT JOIN spaces s ON s.zone_id=z.id LEFT JOIN parking_sessions p ON p.space_id=s.id AND p.checked_out_at IS NULL WHERE z.location_id=$1::uuid GROUP BY z.id ORDER BY z.label,z.id",{location});
            result["floors"]=objects(floors,{"id","label","capacity","occupied","available","out_of_service"});
            // Unassigned spaces have their own aggregate, without exposing individual bays to drivers.
            result["unassigned"]=objects(db.query("SELECT count(*)::text AS total FROM spaces WHERE location_id=$1::uuid AND zone_id IS NULL",{location}),{"total"})[0];
            if(staff) {
                auto rows=db.query("SELECT s.id::text,s.label,s.zone_id::text,s.version::text,s.supported_vehicle_type,s.operational_status,p.id::text AS session_id,p.registration_snapshot,p.checked_in_at::text,u.display_name,u.email,v.vehicle_type,v.color FROM spaces s LEFT JOIN parking_sessions p ON p.space_id=s.id AND p.checked_out_at IS NULL LEFT JOIN users u ON u.id=p.user_id LEFT JOIN vehicles v ON v.id=p.vehicle_id WHERE s.location_id=$1::uuid ORDER BY s.label,s.id LIMIT 100 OFFSET $2::integer",{location,boundedNumber(req->getParameter("offset"),"invalid_offset")});
                result["spaces"]=objects(rows,{"id","label","zone_id","version","supported_vehicle_type","operational_status","session_id","registration_snapshot","checked_in_at","display_name","email","vehicle_type","color"});
                record(db,actor,"staff_dashboard_read","location",location,requestId);
            }
        }
        db.commit(); return {200,result};
    }
    if(operation=="vehicles" && scope=="staff/locations" && req->method()==drogon::Get) {
        auto plate=req->getParameter("registration"),jurisdiction=req->getParameter("jurisdiction");
        if(plate.empty() || plate.size()>64 || jurisdiction.empty() || jurisdiction.size()>64) throw ApiError(400,"exact_registration_and_jurisdiction_required");
        result["vehicles"]=objects(db.query("SELECT v.id::text,v.normalized_registration,v.registration_jurisdiction,v.vehicle_type,v.make,v.model,v.color,u.display_name,u.email FROM vehicles v JOIN users u ON u.id=v.user_id WHERE v.disabled_at IS NULL AND u.status='enabled' AND v.normalized_registration=normalize_registration($1) AND v.registration_jurisdiction=upper(btrim($2)) LIMIT 1",{plate,jurisdiction}),{"id","normalized_registration","registration_jurisdiction","vehicle_type","make","model","color","display_name","email"});
        record(db,actor,"vehicle_lookup","location",location,requestId);
    } else if(admin && operation=="configuration" && req->method()==drogon::Get) {
        result["location"]=objects(db.query("SELECT id::text,name,timezone FROM locations WHERE id=$1::uuid",{location}),{"id","name","timezone"})[0];
        result["zones"]=objects(db.query("SELECT id::text,label FROM zones WHERE location_id=$1::uuid ORDER BY label LIMIT 500",{location}),{"id","label"});
    } else if(admin && operation=="configuration" && req->method()==drogon::Put) {
        auto body=parseJson(std::string(req->body())); fields(body,{"name","timezone","reason"}); required(body,"reason",500);
        auto timezone=required(body,"timezone",100);
        if(!db.query("SELECT 1 FROM pg_timezone_names WHERE name=$1",{timezone}).size()) throw ApiError(400,"invalid_timezone");
        db.query("UPDATE locations SET name=$2,timezone=$3,updated_at=now() WHERE id=$1::uuid",{location,required(body,"name",200),timezone});
        record(db,actor,"location_updated","location",location,requestId,body); result["saved"]=true;
    } else if(admin && operation=="zones" && req->method()==drogon::Post) {
        auto body=parseJson(std::string(req->body())); fields(body,{"label","reason"}); required(body,"reason",500);
        auto row=db.query("INSERT INTO zones(location_id,label) VALUES($1::uuid,$2) RETURNING id::text",{location,required(body,"label",64)});
        result["id"]=row.get(0,"id"); record(db,actor,"zone_created","location",location,requestId,body);
    } else if(admin && operation=="zones" && req->method()==drogon::Put) {
        auto body=parseJson(std::string(req->body())); fields(body,{"id","label","reason"}); required(body,"reason",500);
        auto id=required(body,"id",36); uuid(id);
        auto row=db.query("UPDATE zones SET label=$3 WHERE id=$1::uuid AND location_id=$2::uuid RETURNING id::text",{id,location,required(body,"label",64)});
        if(!row.size()) throw ApiError(404,"zone_not_found");
        record(db,actor,"zone_updated","location",location,requestId,body); result["saved"]=true;
    } else if(admin && operation=="spaces" && req->method()==drogon::Put) {
        auto body=parseJson(std::string(req->body())); fields(body,{"id","label","zoneId","vehicleType","reason"}); required(body,"reason",500);
        auto id=required(body,"id",36),zone=required(body,"zoneId",36),type=required(body,"vehicleType",20); uuid(id);uuid(zone);
        if(type!="car" && type!="van" && type!="motorcycle") throw ApiError(400,"invalid_vehicle_type");
        if(!db.query("SELECT 1 FROM zones WHERE id=$1::uuid AND location_id=$2::uuid",{zone,location}).size()) throw ApiError(400,"zone_location_mismatch");
        auto row=db.query("SELECT id FROM spaces WHERE id=$1::uuid AND location_id=$2::uuid FOR UPDATE",{id,location});
        if(!row.size()) throw ApiError(404,"space_not_found");
        if(db.query("SELECT 1 FROM parking_sessions WHERE space_id=$1::uuid AND checked_out_at IS NULL",{id}).size()) throw ApiError(409,"space_occupied");
        db.query("UPDATE spaces SET zone_id=$2::uuid,label=$3,supported_vehicle_type=$4 WHERE id=$1::uuid",{id,zone,required(body,"label",64),type});
        notify(db,id);record(db,actor,"space_updated","space",id,requestId,body);result["saved"]=true;
    } else if(admin && operation=="spaces" && req->method()==drogon::Post) {
        auto body=parseJson(std::string(req->body())); fields(body,{"label","zoneId","vehicleType","reason"}); required(body,"reason",500);
        auto zone=required(body,"zoneId",36); uuid(zone); auto type=required(body,"vehicleType",20);
        if(type!="car" && type!="van" && type!="motorcycle") throw ApiError(400,"invalid_vehicle_type");
        if(!db.query("SELECT 1 FROM zones WHERE id=$1::uuid AND location_id=$2::uuid",{zone,location}).size()) throw ApiError(400,"zone_location_mismatch");
        auto row=db.query("INSERT INTO spaces(location_id,zone_id,label,supported_vehicle_type) VALUES($1::uuid,$2::uuid,$3,$4) RETURNING id::text",{location,zone,required(body,"label",64),type});
        auto id=row.get(0,"id"); notify(db,id); result["id"]=id; record(db,actor,"space_created","space",id,requestId,body);
    } else if(admin && operation=="staff-list" && req->method()==drogon::Get) {
        result["staff"]=objects(db.query("SELECT u.id::text,u.display_name,u.email,a.role FROM staff_assignments a JOIN users u ON u.id=a.user_id WHERE a.location_id=$1::uuid ORDER BY u.id LIMIT 100 OFFSET $2::integer",{location,boundedNumber(req->getParameter("offset"),"invalid_offset")}),{"id","display_name","email","role"}); record(db,actor,"staff_list_read","location",location,requestId);
    } else if(admin && operation=="users" && req->method()==drogon::Get) {
        auto email=req->getParameter("email"); if(email.empty() || email.size()>200) throw ApiError(400,"exact_email_required");
        result["users"]=objects(db.query("SELECT u.id::text,u.display_name,u.email,u.status,v.id::text AS vehicle_id,v.normalized_registration,v.registration_jurisdiction FROM users u LEFT JOIN vehicles v ON v.user_id=u.id AND v.disabled_at IS NULL WHERE lower(u.email)=lower($1) ORDER BY u.id LIMIT 10",{email}),{"id","display_name","email","status","vehicle_id","normalized_registration","registration_jurisdiction"});
        record(db,actor,"user_lookup","location",location,requestId);
    } else if(admin && operation=="users" && req->method()==drogon::Put) {
        // Account changes apply across this single operator. Do not use for multi-tenant deployment.
        // Lock target users before assignment locks, as in parking/role transactions.
        db.commit(); auto body=parseJson(std::string(req->body())); fields(body,{"userId","status","disableVehicle","reason"});
        auto target=required(body,"userId",36); uuid(target); auto state=required(body,"status",20); required(body,"reason",500);
        if(state!="enabled" && state!="disabled") throw ApiError(400,"invalid_status");
        if(body.isMember("disableVehicle") && !body["disableVehicle"].isBool()) throw ApiError(400,"invalid_disable_vehicle");
        if(target==actor.user) throw ApiError(409,"cannot_disable_own_account");
        db.begin(); auto users=db.query("SELECT id::text,status FROM users WHERE id IN ($1::uuid,$2::uuid) ORDER BY id FOR UPDATE",{actor.user,target});
        if(users.size()!=2) throw ApiError(404,"user_not_found");
        for(int i=0;i<users.size();++i) if(users.get(i,"id")==actor.user && users.get(i,"status")!="enabled") throw ApiError(403,"account_disabled");
        authorizeLocation(db,actor,location,true);
        auto vehicles=db.query("SELECT id::text FROM vehicles WHERE user_id=$1::uuid AND disabled_at IS NULL ORDER BY id FOR UPDATE",{target});
        if(db.query("SELECT 1 FROM parking_sessions WHERE user_id=$1::uuid AND checked_out_at IS NULL",{target}).size()) throw ApiError(409,"end_session_before_user_change");
        db.query("UPDATE users SET status=$2,updated_at=now() WHERE id=$1::uuid",{target,state});
        if(body.get("disableVehicle",false).asBool() && vehicles.size()) db.query("UPDATE vehicles SET disabled_at=now(),updated_at=now() WHERE id=$1::uuid",{vehicles.get(0,"id")});
        record(db,actor,"user_updated","location",location,requestId,body); result["saved"]=true;
    } else if(admin && operation=="audit" && req->method()==drogon::Get) {
        auto filter=req->getParameter("action"); if(filter.size()>80) throw ApiError(400,"invalid_filter");
        result["events"]=objects(db.query("SELECT a.id::text,a.actor_id::text,a.action,a.target_type,a.target_id::text,a.occurred_at::text,a.request_id::text,a.sanitized_changes::text FROM audit_events a WHERE (a.target_id=$1::uuid OR a.target_id IN(SELECT id FROM spaces WHERE location_id=$1::uuid) OR a.target_id IN(SELECT p.id FROM parking_sessions p JOIN spaces s ON s.id=p.space_id WHERE s.location_id=$1::uuid)) AND ($2='' OR a.action=$2) ORDER BY a.occurred_at DESC,a.id LIMIT 50 OFFSET $3::integer",{location,filter,boundedNumber(req->getParameter("offset"),"invalid_offset")}),{"id","actor_id","action","target_type","target_id","occurred_at","request_id","sanitized_changes"}); record(db,actor,"audit_read","location",location,requestId);
    } else throw ApiError(404,"not_found");
    if(admin && req->method()!=drogon::Get && operation!="spaces") {
        auto anchor=db.query("SELECT id::text FROM spaces WHERE location_id=$1::uuid ORDER BY id LIMIT 1 FOR UPDATE",{location});
        if(anchor.size()) notify(db,anchor.get(0,"id"));
    }
    db.commit(); return {200,result};
}
}
