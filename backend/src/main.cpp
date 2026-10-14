#include "availability.h"
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
    drogon::app().registerHandler("/api/health", [](const drogon::HttpRequestPtr &, std::function<void(const drogon::HttpResponsePtr &)> &&callback) {
        Json::Value body; body["status"] = "ok";
        callback(drogon::HttpResponse::newHttpJsonResponse(body));
    }, {drogon::Get});
    drogon::app().registerHandler("/api/ready", [db](const drogon::HttpRequestPtr &, std::function<void(const drogon::HttpResponsePtr &)> &&callback) {
        auto reply = std::make_shared<std::function<void(const drogon::HttpResponsePtr &)>>(std::move(callback));
        db->execSqlAsync("SELECT version FROM schema_migrations WHERE version='001'",
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
