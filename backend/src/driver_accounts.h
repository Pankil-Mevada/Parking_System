#pragma once
#include "parking.h"
namespace parking {
Reply createDriver(Database &,const Identity &,const drogon::HttpRequestPtr &,const AuthConfig &,const std::string &);
}
