#include "availability.h"
#include <trantor/utils/Date.h>

void registerAvailability(const drogon::orm::DbClientPtr &db) {
    drogon::app().registerHandler("/api/locations",
        [db](const drogon::HttpRequestPtr &, std::function<void(const drogon::HttpResponsePtr &)> &&callback) {
            auto reply = std::make_shared<std::function<void(const drogon::HttpResponsePtr &)>>(std::move(callback));
            db->execSqlAsync(
                "SELECT l.id::text, l.name, count(s.id) FILTER (WHERE s.operational_status='enabled') AS capacity, "
                "count(p.id) FILTER (WHERE s.operational_status='enabled') AS occupied, "
                "count(s.id) FILTER (WHERE s.operational_status='enabled' AND p.id IS NULL) AS available, "
                "count(s.id) FILTER (WHERE s.operational_status='out_of_service') AS out_of_service "
                "FROM locations l LEFT JOIN spaces s ON s.location_id=l.id "
                "LEFT JOIN parking_sessions p ON p.space_id=s.id AND p.checked_out_at IS NULL "
                "GROUP BY l.id,l.name ORDER BY l.name,l.id LIMIT 100",
                [reply](const drogon::orm::Result &rows) {
                    Json::Value body;
                    body["locations"] = Json::Value(Json::arrayValue);
                    for (const auto &row : rows) {
                        Json::Value location;
                        location["id"] = row["id"].as<std::string>();
                        location["name"] = row["name"].as<std::string>();
                        location["capacity"] = row["capacity"].as<int>();
                        location["occupied"] = row["occupied"].as<int>();
                        location["available"] = row["available"].as<int>();
                        location["outOfService"] = row["out_of_service"].as<int>();
                        body["locations"].append(location);
                    }
                    body["timestamp"] = trantor::Date::now().toCustomFormattedString("%Y-%m-%dT%H:%M:%SZ");
                    auto response = drogon::HttpResponse::newHttpJsonResponse(body);
                    response->addHeader("Cache-Control", "no-store");
                    (*reply)(response);
                },
                [reply](const drogon::orm::DrogonDbException &) {
                    Json::Value body; body["error"] = "availability_unavailable";
                    auto response = drogon::HttpResponse::newHttpJsonResponse(body);
                    response->setStatusCode(drogon::k503ServiceUnavailable);
                    (*reply)(response);
                });
        }, {drogon::Get});
}
