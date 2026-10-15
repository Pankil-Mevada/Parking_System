#pragma once
#include <libpq-fe.h>
#include <json/json.h>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace parking {
struct ApiError : std::runtime_error {
    int status;
    ApiError(int code, const std::string &message) : std::runtime_error(message), status(code) {}
};
struct SqlError : std::runtime_error {
    std::string state, constraint;
    explicit SqlError(PGresult *r) : std::runtime_error("database_error"),
        state(PQresultErrorField(r, PG_DIAG_SQLSTATE) ? PQresultErrorField(r, PG_DIAG_SQLSTATE) : ""),
        constraint(PQresultErrorField(r, PG_DIAG_CONSTRAINT_NAME) ? PQresultErrorField(r, PG_DIAG_CONSTRAINT_NAME) : "") {}
};
class Rows {
    std::shared_ptr<PGresult> result;
public:
    explicit Rows(PGresult *r) : result(r, PQclear) {}
    int size() const { return PQntuples(result.get()); }
    std::string get(int row, const char *column) const {
        return PQgetvalue(result.get(), row, PQfnumber(result.get(), column));
    }
    bool null(int row, const char *column) const {
        return PQgetisnull(result.get(), row, PQfnumber(result.get(), column));
    }
};
class Database {
    std::unique_ptr<PGconn, decltype(&PQfinish)> connection;
    bool transaction = false;
public:
    explicit Database(const std::string &url) : connection(PQconnectdb(url.c_str()), PQfinish) {
        if (PQstatus(connection.get()) != CONNECTION_OK) throw ApiError(503, "database_unavailable");
        query("SET statement_timeout='5s'");
        query("SET lock_timeout='4s'");
        query("SET TIME ZONE 'UTC'");
    }
    Rows query(const std::string &sql, const std::vector<std::string> &values = {}) {
        std::vector<const char *> parameters;
        for (const auto &value : values) parameters.push_back(value.c_str());
        PGresult *r = PQexecParams(connection.get(), sql.c_str(), static_cast<int>(parameters.size()),
                                  nullptr, parameters.data(), nullptr, nullptr, 0);
        if (!r) throw ApiError(503, "database_unavailable");
        auto status = PQresultStatus(r);
        if (status != PGRES_TUPLES_OK && status != PGRES_COMMAND_OK) {
            SqlError error(r); PQclear(r); throw error;
        }
        return Rows(r);
    }
    void begin() { query("BEGIN"); transaction = true; }
    void commit() { query("COMMIT"); transaction = false; }
    ~Database() { if (transaction) { auto r = PQexec(connection.get(), "ROLLBACK"); if (r) PQclear(r); } }
};
Json::Value parseJson(const std::string &value);
std::string jsonString(const Json::Value &value);
std::string sha256(const std::string &value);
std::string required(const Json::Value &body, const char *field, size_t maximum = 200);
void fields(const Json::Value &body, const std::vector<std::string> &allowed);
void uuid(const std::string &value);
}
