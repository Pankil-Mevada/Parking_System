#include "parking.h"
#include "driver_accounts.h"
#include <regex>
#include <trantor/utils/ConcurrentTaskQueue.h>

namespace parking {
void registerProtectedApi(const std::string &databaseUrl, const AuthConfig &config) {
    auto workers=std::make_shared<trantor::ConcurrentTaskQueue>(8,"parking-writes");
    auto handler=[workers,databaseUrl,config](const drogon::HttpRequestPtr &request,
                  std::function<void(const drogon::HttpResponsePtr &)> &&callback) {
        auto reply=std::make_shared<std::function<void(const drogon::HttpResponsePtr &)>>(std::move(callback));
        auto requestId=drogon::utils::getUuid();
        if(workers->getTaskCount()>64) { Json::Value error; error["error"]="server_busy"; auto r=drogon::HttpResponse::newHttpJsonResponse(error); r->setStatusCode(drogon::k503ServiceUnavailable); r->addHeader("X-Request-ID",requestId); r->addHeader("Cache-Control","no-store"); (*reply)(r); return; }
        workers->runTaskInQueue([request,reply,databaseUrl,config,requestId]() {
            Reply result;
            try {
                // Bearer authorization is explicit. This API does not authenticate
                // cookies, so cross-site ambient-cookie writes cannot authenticate.
                auto origin=request->getHeader("origin");
                if(!origin.empty() && origin!=config.origin) throw ApiError(403,"origin_denied");
                Database db(databaseUrl);
                auto actor=authenticate(db,request,config);
                if(request->method()==drogon::Post && std::regex_match(request->path(),std::regex("/api/staff/locations/[^/]+/drivers")))result=createDriver(db,actor,request,config,requestId);
                else result=execute(db,actor,request,requestId);
            } catch(const ApiError &e) { result.status=e.status; result.body["error"]=e.what(); }
              catch(const SqlError &e) {
                  result.status=e.state=="23505" ? 409 : (e.state=="23514" || e.state=="22P02" ? 400 : 503);
                  result.body["error"]=result.status==409?"parking_or_registration_conflict":(result.status==400?"invalid_request":"transaction_failed");
                  if(e.state=="23505" && e.constraint=="unique_enabled_registration")result.body["error"]="vehicle_registration_already_in_use";
              }
              catch(const std::exception &) { result.status=500; result.body["error"]="internal_error"; }
            auto response=drogon::HttpResponse::newHttpJsonResponse(result.body);
            if(request->path().size()>=7 && request->path().substr(request->path().size()-7)=="/events" && result.status==200) {
                // Bounded SSE response, then reconnect. Authorization is checked on
                // every batch, rather than retaining an indefinitely privileged stream.
                response=drogon::HttpResponse::newHttpResponse();
                response->setContentTypeString("text/event-stream");
                response->setBody("retry: 1000\nevent: changes\nid: "+result.body["cursor"].asString()+"\ndata: "+jsonString(result.body)+"\n\n");
                response->addHeader("X-Accel-Buffering","no");
            }
            response->setStatusCode(static_cast<drogon::HttpStatusCode>(result.status));
            response->addHeader("Cache-Control","no-store"); response->addHeader("X-Request-ID",requestId);
            response->addHeader("X-Content-Type-Options","nosniff");
            (*reply)(response);
        });
    };
    // Drogon's binder preserves lvalue references; each route must own a copy.
    for(auto path:{"/api/me","/api/me/vehicle","/api/me/parking-session","/api/me/parking-history"})
        drogon::app().registerHandler(path,decltype(handler)(handler),{drogon::Get});
    drogon::app().registerHandler("/api/me/vehicle",decltype(handler)(handler),{drogon::Put});
    drogon::app().registerHandler("/api/me/staff-application",decltype(handler)(handler),{drogon::Post});
    drogon::app().registerHandlerViaRegex("/api/staff/locations/[^/]+/drivers/[^/]+/vehicle",decltype(handler)(handler),{drogon::Put});
    drogon::app().registerHandlerViaRegex("/api/staff/locations/[^/]+/drivers",decltype(handler)(handler),{drogon::Get,drogon::Post});
    drogon::app().registerHandler("/api/auth/logout",decltype(handler)(handler),{drogon::Post});
    drogon::app().registerHandler("/api/staff/check-ins",decltype(handler)(handler),{drogon::Post});
    drogon::app().registerHandlerViaRegex("/api/staff/sessions/[^/]+/check-out",decltype(handler)(handler),{drogon::Post});
    drogon::app().registerHandlerViaRegex("/api/staff/locations/[^/]+/spaces",decltype(handler)(handler),{drogon::Get});
    drogon::app().registerHandlerViaRegex("/api/admin/spaces/[^/]+/status",decltype(handler)(handler),{drogon::Put});
    drogon::app().registerHandlerViaRegex("/api/admin/locations/[^/]+/staff",decltype(handler)(handler),{drogon::Post});
    drogon::app().registerHandler("/api/me/dashboard",decltype(handler)(handler),{drogon::Get});
    drogon::app().registerHandler("/api/admin/locations",decltype(handler)(handler),{drogon::Post});
    drogon::app().registerHandlerViaRegex("/api/locations/[^/]+/(dashboard|events)",decltype(handler)(handler),{drogon::Get});
    drogon::app().registerHandlerViaRegex("/api/staff/locations/[^/]+/(dashboard|events|vehicles)",decltype(handler)(handler),{drogon::Get});
    drogon::app().registerHandlerViaRegex("/api/admin/locations/[^/]+/(configuration|users)",decltype(handler)(handler),{drogon::Get,drogon::Put});
    drogon::app().registerHandlerViaRegex("/api/admin/locations/[^/]+/(audit|staff-list)",decltype(handler)(handler),{drogon::Get});
    drogon::app().registerHandlerViaRegex("/api/admin/locations/[^/]+/staff-accounts",decltype(handler)(handler),{drogon::Get,drogon::Post});
    drogon::app().registerHandlerViaRegex("/api/admin/locations/[^/]+/(zones|spaces)",decltype(handler)(handler),{drogon::Post,drogon::Put});
}
}
