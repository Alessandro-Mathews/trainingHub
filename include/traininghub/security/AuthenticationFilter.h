#pragma once

#include <drogon/HttpFilter.h>

namespace traininghub::security
{
class AuthenticationFilter : public drogon::HttpFilter<AuthenticationFilter>
{
public:
    void doFilter(const drogon::HttpRequestPtr &req, drogon::FilterCallback &&reject,
                  drogon::FilterChainCallback &&next) override;
};
}
