#include "operations.h"
#include "storage.h"
#include <drogon/drogon.h>
#include <openssl/crypto.h>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <map>
#include <mutex>
#include <sstream>
#include <atomic>

namespace parking {
namespace {
std::mutex metricsMutex;
struct Metric {uint64_t count=0;double sum=0;uint64_t buckets[5]={};};
std::map<std::string,Metric> metrics;
std::atomic<uint64_t> conflicts{0},authFailures{0},streamBatches{0},errors{0};
std::string route(const std::string &path) {
    for(auto prefix:{"/api/admin/","/api/staff/","/api/me/","/api/locations/"})
        if(path.rfind(prefix,0)==0)return std::string(prefix)+"resource";
    for(auto fixed:{"/api/health","/api/ready","/api/me","/api/locations","/api/auth/config","/api/auth/logout","/internal/metrics"})if(path==fixed)return fixed;
    return "unknown";
}
}
std::string setting(const std::string &key,const std::string &fallback) {
    const char *file=std::getenv((key+"_FILE").c_str());
    if(file && *file) {
        std::ifstream input(file);if(!input)throw std::runtime_error(key+" secret file unavailable");
        std::string value((std::istreambuf_iterator<char>(input)),{});
        while(!value.empty() && (value.back()=='\n'||value.back()=='\r'))value.pop_back();
        if(value.empty()||value.size()>16384)throw std::runtime_error(key+" secret file invalid");
        return value;
    }
    const char *value=std::getenv(key.c_str());return value && *value ? std::string(value):fallback;
}
void registerOperations(const std::string &databaseUrl) {
    auto token=setting("OPS_METRICS_TOKEN");
    auto gauges=drogon::orm::DbClient::newPgClient(databaseUrl,1);gauges->setTimeout(3);
    drogon::app().registerPreRoutingAdvice([](const drogon::HttpRequestPtr &req) {
        req->attributes()->insert("ops_start",std::chrono::steady_clock::now());
    });
    drogon::app().registerPostHandlingAdvice([](const drogon::HttpRequestPtr &req,const drogon::HttpResponsePtr &response) {
        const auto start=req->attributes()->get<std::chrono::steady_clock::time_point>("ops_start");
        double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
        auto status=static_cast<int>(response->statusCode());
        const auto group=route(req->path());
        auto id=response->getHeader("X-Request-ID");if(id.empty())id=drogon::utils::getUuid();
        response->addHeader("X-Request-ID",id);response->addHeader("X-Content-Type-Options","nosniff");
        response->addHeader("X-Frame-Options","DENY");response->addHeader("Referrer-Policy","no-referrer");
        response->addHeader("Content-Security-Policy","default-src 'none'; frame-ancestors 'none'");
        response->addHeader("Cache-Control","no-store");
        { std::lock_guard<std::mutex> guard(metricsMutex);auto &m=metrics[group+"|"+std::to_string(status)];m.count++;m.sum+=seconds;
          const double bounds[]={.05,.1,.5,1.,5.};for(size_t i=0;i<5;i++)if(seconds<=bounds[i])m.buckets[i]++; }
        if(status==409)conflicts++;
        if(status==401)authFailures++;
        if(status>=500)errors++;
        if(req->path().size()>=7 && req->path().substr(req->path().size()-7)=="/events" && status==200)streamBatches++;
        // No query strings, request bodies, personal data, IPs or credentials.
        // Fixed route groups also bound metric cardinality and log attacker input.
        if(group!="/internal/metrics" && group!="/api/health") {
            Json::Value event;event["event"]="http_request";event["requestId"]=id;event["route"]=group;event["status"]=status;event["durationMs"]=seconds*1000;
            LOG_WARN << jsonString(event);
        }
    });
    drogon::app().registerHandler("/internal/metrics",[token,gauges](const drogon::HttpRequestPtr &req,std::function<void(const drogon::HttpResponsePtr &)> &&callback) {
        auto expected="Bearer "+token,received=req->getHeader("authorization");
        if(token.size()<32 || received.size()!=expected.size() || CRYPTO_memcmp(received.data(),expected.data(),expected.size())!=0) {
            auto response=drogon::HttpResponse::newHttpResponse();response->setStatusCode(drogon::k403Forbidden);callback(response);return;
        }
        auto reply=std::make_shared<std::function<void(const drogon::HttpResponsePtr &)>>(std::move(callback));
        gauges->execSqlAsync("SELECT (SELECT count(*) FROM outbox_events WHERE published_at IS NULL)::text AS pending,coalesce((SELECT extract(epoch FROM now()-min(created_at)) FROM outbox_events WHERE published_at IS NULL),0)::text AS lag,(SELECT count(*) FROM pg_stat_activity WHERE datname=current_database())::text AS connections,current_setting('max_connections') AS max_connections,(SELECT count(*) FROM client_health WHERE last_seen>now()-interval '30 seconds')::text AS clients,(SELECT count(*) FROM client_health WHERE last_seen<=now()-interval '30 seconds' AND last_seen>now()-interval '5 minutes')::text AS stale",
            [reply](const drogon::orm::Result &rows) {
                std::ostringstream out;
                out<<"# TYPE parking_http_requests_total counter\n# TYPE parking_http_duration_seconds histogram\n";
                {std::lock_guard<std::mutex> guard(metricsMutex);for(const auto &[key,m]:metrics) {
                    auto split=key.find('|');std::string labels="route=\""+key.substr(0,split)+"\",status=\""+key.substr(split+1)+"\"";
                    out<<"parking_http_requests_total{"<<labels<<"} "<<m.count<<"\n";
                    out<<"parking_http_duration_seconds_sum{"<<labels<<"} "<<m.sum<<"\n";
                    out<<"parking_http_duration_seconds_count{"<<labels<<"} "<<m.count<<"\n";
                    const char *bounds[]={"0.05","0.1","0.5","1","5"};for(size_t i=0;i<5;i++)out<<"parking_http_duration_seconds_bucket{"<<labels<<",le=\""<<bounds[i]<<"\"} "<<m.buckets[i]<<"\n";
                    out<<"parking_http_duration_seconds_bucket{"<<labels<<",le=\"+Inf\"} "<<m.count<<"\n";
                }}
                out<<"parking_conflicts_total "<<conflicts.load()<<"\nparking_auth_failures_total "<<authFailures.load()<<"\nparking_http_errors_total "<<errors.load()<<"\nparking_stream_batches_total "<<streamBatches.load()<<"\n";
                out<<"parking_outbox_pending "<<rows[0]["pending"].as<std::string>()<<"\nparking_outbox_lag_seconds "<<rows[0]["lag"].as<std::string>()<<"\nparking_db_connections "<<rows[0]["connections"].as<std::string>()<<"\nparking_db_max_connections "<<rows[0]["max_connections"].as<std::string>()<<"\n";
                out<<"parking_stream_clients_recent "<<rows[0]["clients"].as<std::string>()<<"\nparking_stream_clients_stale "<<rows[0]["stale"].as<std::string>()<<"\n";
                auto response=drogon::HttpResponse::newHttpResponse();response->setContentTypeString("text/plain; version=0.0.4");response->setBody(out.str());(*reply)(response);
            },[reply](const drogon::orm::DrogonDbException &) {auto response=drogon::HttpResponse::newHttpResponse();response->setStatusCode(drogon::k503ServiceUnavailable);(*reply)(response);});
    },{drogon::Get});
}
}
