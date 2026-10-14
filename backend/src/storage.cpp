#include "storage.h"
#include <openssl/sha.h>
#include <algorithm>
#include <iomanip>
#include <regex>
#include <sstream>

namespace parking {
Json::Value parseJson(const std::string &value) {
    Json::Value result; Json::CharReaderBuilder builder; builder["rejectDupKeys"] = true;
    std::string errors; auto reader = std::unique_ptr<Json::CharReader>(builder.newCharReader());
    if (!reader->parse(value.data(), value.data() + value.size(), &result, &errors)) throw ApiError(400, "invalid_json");
    return result;
}
std::string jsonString(const Json::Value &value) { Json::StreamWriterBuilder builder; builder["indentation"] = ""; return Json::writeString(builder, value); }
std::string sha256(const std::string &value) {
    unsigned char digest[SHA256_DIGEST_LENGTH]; SHA256(reinterpret_cast<const unsigned char *>(value.data()), value.size(), digest);
    std::ostringstream out; for (auto byte : digest) out << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(byte);
    return out.str();
}
std::string required(const Json::Value &body, const char *field, size_t maximum) {
    if (!body[field].isString()) throw ApiError(400, std::string("invalid_") + field);
    auto value = body[field].asString();
    if (value.empty() || value.size() > maximum || value.find('\0') != std::string::npos ||
        value.find_first_not_of(" \t\r\n") == std::string::npos) throw ApiError(400, std::string("invalid_") + field);
    return value;
}
void fields(const Json::Value &body, const std::vector<std::string> &allowed) {
    if (!body.isObject()) throw ApiError(400, "object_required");
    for (const auto &field : body.getMemberNames()) if (std::find(allowed.begin(), allowed.end(), field) == allowed.end()) throw ApiError(400, "unknown_field");
}
void uuid(const std::string &value) {
    static const std::regex pattern("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$");
    if (!std::regex_match(value, pattern)) throw ApiError(400, "invalid_id");
}
}
