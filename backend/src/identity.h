#pragma once
#include "storage.h"
#include <drogon/drogon.h>
namespace parking {
struct Identity { std::string user, subject, session; bool mfa; };
struct AuthConfig { std::string host, realm, issuer, secret, origin; };
Identity authenticate(Database &db, const drogon::HttpRequestPtr &request, const AuthConfig &config);
void authorizeLocation(Database &db, const Identity &actor, const std::string &location, bool admin = false);
}
