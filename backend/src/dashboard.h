#pragma once
#include "parking.h"
namespace parking {
Reply dashboard(Database &, const Identity &, const drogon::HttpRequestPtr &, const std::string &);
void publishOutbox(Database &);
}
