#pragma once
#include <string>
namespace parking {
std::string setting(const std::string &key, const std::string &fallback="");
void registerOperations(const std::string &databaseUrl);
}
