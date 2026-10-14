#include "identity.h"
#include <ctime>

namespace parking {
Identity authenticate(Database &db, const drogon::HttpRequestPtr &request, const AuthConfig &config) {
    auto header = request->getHeader("authorization");
    if (header.compare(0, 7, "Bearer ") != 0 || header.size() > 12000) throw ApiError(401, "authentication_required");
    const auto token = header.substr(7);
    // The configured provider validates the signature, expiry and active session.
    // Never trust locally decoded JWT claims before successful introspection.
    auto client = drogon::HttpClient::newHttpClient(config.host);
    auto introspect = drogon::HttpRequest::newHttpFormPostRequest();
    introspect->setPath("/realms/" + config.realm + "/protocol/openid-connect/token/introspect");
    introspect->setParameter("client_id", "parking-api");
    introspect->setParameter("client_secret", config.secret);
    introspect->setParameter("token", token);
    auto result = client->sendRequest(introspect, 3.0);
    if (result.first != drogon::ReqResult::Ok || !result.second || result.second->statusCode() != drogon::k200OK) throw ApiError(503, "identity_provider_unavailable");
    auto verified = result.second->getJsonObject();
    if (!verified || !(*verified)["active"].asBool()) throw ApiError(401, "invalid_or_expired_session");
    auto first = token.find('.'), last = token.find('.', first == std::string::npos ? 0 : first + 1);
    if (first == std::string::npos || last == std::string::npos) throw ApiError(401, "invalid_token");
    auto encoded = token.substr(first + 1, last - first - 1);
    for (auto &c : encoded) { if (c == '-') c = '+'; else if (c == '_') c = '/'; }
    while (encoded.size() % 4) encoded += '=';
    auto claims = parseJson(drogon::utils::base64Decode(encoded));
    bool audience = claims["aud"] == "parking-api";
    if (claims["aud"].isArray()) for (const auto &value : claims["aud"]) if (value == "parking-api") audience = true;
    if (claims["iss"] != config.issuer || !audience || claims["azp"] != "parking-web" ||
        claims["sub"] != (*verified)["sub"] || claims["exp"].asInt64() <= std::time(nullptr)) throw ApiError(401, "invalid_token_scope");
    if (!claims["email_verified"].asBool()) throw ApiError(403, "verified_account_required");
    std::string subject = required(claims, "sub"), session = required(claims, "sid");
    if (db.query("SELECT 1 FROM revoked_auth_sessions WHERE provider_session_id=$1 AND expires_at>now()", {session}).size()) throw ApiError(401, "revoked_session");
    auto user = db.query("INSERT INTO users(identity_provider_reference,display_name,email) VALUES($1,$2,$3) "
                         "ON CONFLICT(identity_provider_reference) DO UPDATE SET display_name=excluded.display_name,email=excluded.email "
                         "RETURNING id::text,status", {config.issuer + "|" + subject, claims.get("name", "").asString(), claims.get("email", "").asString()});
    if (user.get(0,"status") != "enabled") throw ApiError(403, "account_disabled");
    bool mfa = false;
    if (claims["amr"].isArray()) for (const auto &method : claims["amr"]) if (method == "otp") mfa = true;
    return {user.get(0,"id"), subject, session, mfa};
}
void authorizeLocation(Database &db, const Identity &actor, const std::string &location, bool admin) {
    if (!actor.mfa) throw ApiError(403, "staff_mfa_required");
    auto result = db.query("SELECT role FROM staff_assignments WHERE user_id=$1::uuid AND location_id=$2::uuid FOR SHARE", {actor.user, location});
    if (!result.size() || (admin && result.get(0,"role") != "operator_admin")) throw ApiError(403, "location_access_denied");
}
}
