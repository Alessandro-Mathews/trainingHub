#pragma once

#include "traininghub/models/Academia.h"

#include <drogon/orm/DbClient.h>
#include <functional>
#include <optional>
#include <vector>

namespace traininghub::repositories
{

class AcademiaRepository
{
public:
    using FindAllCallback =
        std::function<void(const std::vector<models::Academia> &)>;
    using ErrorCallback = drogon::orm::ExceptionCallback;
    using FindCallback = std::function<void(const std::optional<models::Academia> &)>;

    explicit AcademiaRepository(const drogon::orm::DbClientPtr &db);

    void findAll(FindAllCallback callback, ErrorCallback errorCallback) const;
    void buscarPorId(std::int64_t id, FindCallback callback,
                     ErrorCallback errorCallback) const;

private:
    drogon::orm::DbClientPtr db_;
};

}
