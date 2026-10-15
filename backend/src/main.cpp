#include "availability.h"
#include "parking.h"
#include "dashboard.h"
#include <thread>
#include <chrono>
#include <cstdlib>
#include <iostream>

int main() {
    const char *connection = std::getenv("API_DATABASE_URL");
    if (!connection || !*connection) {
        std::cerr << "API_DATABASE_URL is required; see .env.example\n";
        return 1;
    }
    auto db = drogon::orm::DbClient::newPgClient(connection, 4);
    db->setTimeout(3.0);
    registerAvailability(db);
    auto setting=[](const char *key) { const char *value=std::getenv(key); if(!value || !*value) throw std::runtime_error(std::string(key)+" is required"); return std::string(value); };
    try {
        parking::AuthConfig auth{setting("OIDC_INTERNAL_URL"),setting("OIDC_REALM"),setting("OIDC_ISSUER"),setting("OIDC_CLIENT_SECRET"),setting("APP_ORIGIN")};
        registerProtectedApi(connection,auth);
        std::thread([url=std::string(connection)] {
            for(;;) {
                try { parking::Database connection(url); parking::publishOutbox(connection); }
                catch(const std::exception &) { LOG_WARN << "Outbox publication unavailable; retrying"; }
                std::this_thread::sleep_for(std::chrono::milliseconds(500));
            }
        }).detach();
        drogon::app().registerHandler("/api/auth/config",[auth](const drogon::HttpRequestPtr &,std::function<void(const drogon::HttpResponsePtr &)> &&callback) {
            Json::Value body; body["url"]=auth.issuer.substr(0,auth.issuer.find("/realms/")); body["realm"]=auth.realm; body["clientId"]="parking-web";
            callback(drogon::HttpResponse::newHttpJsonResponse(body));
        },{drogon::Get});
    } catch(const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
    drogon::app().registerHandler("/api/health", [](const drogon::HttpRequestPtr &, std::function<void(const drogon::HttpResponsePtr &)> &&callback) {
        Json::Value body; body["status"] = "ok";
        callback(drogon::HttpResponse::newHttpJsonResponse(body));
    }, {drogon::Get});
    drogon::app().registerHandler("/api/ready", [db](const drogon::HttpRequestPtr &, std::function<void(const drogon::HttpResponsePtr &)> &&callback) {
        auto reply = std::make_shared<std::function<void(const drogon::HttpResponsePtr &)>>(std::move(callback));
        db->execSqlAsync("SELECT version FROM schema_migrations WHERE version='003'",
            [reply](const drogon::orm::Result &rows) {
                Json::Value body; body["status"] = rows.empty() ? "not_ready" : "ready";
                auto response = drogon::HttpResponse::newHttpJsonResponse(body);
                if (rows.empty()) response->setStatusCode(drogon::k503ServiceUnavailable);
                (*reply)(response);
            }, [reply](const drogon::orm::DrogonDbException &) {
                Json::Value body; body["status"] = "not_ready";
                auto response = drogon::HttpResponse::newHttpJsonResponse(body);
                response->setStatusCode(drogon::k503ServiceUnavailable);
                (*reply)(response);
            });
    }, {drogon::Get});
    drogon::app().setLogLevel(trantor::Logger::kWarn).setClientMaxBodySize(65536)
        .addListener("0.0.0.0", 8080).setThreadNum(2).run();
}
