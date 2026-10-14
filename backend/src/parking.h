#pragma once
#include "identity.h"
namespace parking {
struct Reply { int status = 200; Json::Value body; };
Reply execute(Database &db, const Identity &actor, const drogon::HttpRequestPtr &request,
              const std::string &requestId);
void registerProtectedApi(const std::string &databaseUrl, const AuthConfig &config);
}
