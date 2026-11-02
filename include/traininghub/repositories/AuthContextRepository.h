#pragma once

#include "traininghub/security/AuthSession.h"
#include <drogon/orm/DbClient.h>
#include <functional>
#include <optional>
#include <string>
#include <utility>

namespace traininghub::repositories
{
struct AuthRecord
{
    security::AuthSession identity;
    bool userActive{};
    bool academiaActive{};
    bool perfilActive{};
    std::string perfilName;
};

class AuthContextRepository
{
public:
    using Callback = std::function<void(const std::optional<AuthRecord> &)>;
    explicit AuthContextRepository(drogon::orm::DbClientPtr db) : db_(std::move(db)) {}
    void find(std::int64_t userId, Callback callback,
              drogon::orm::ExceptionCallback errorCallback) const;
private:
    drogon::orm::DbClientPtr db_;
};
}
