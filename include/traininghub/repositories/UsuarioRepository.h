#pragma once

#include "traininghub/models/Usuario.h"

#include <drogon/orm/DbClient.h>
#include <functional>
#include <optional>

namespace traininghub::repositories
{

class UsuarioRepository
{
public:
    using FindCallback = std::function<void(const std::optional<models::Usuario> &)>;
    using ErrorCallback = drogon::orm::ExceptionCallback;

    explicit UsuarioRepository(const drogon::orm::DbClientPtr &db);

    void findByAcademiaAndEmail(std::int64_t academiaId,
                               const std::string &email,
                               FindCallback callback,
                               ErrorCallback errorCallback) const;

private:
    drogon::orm::DbClientPtr db_;
};

}
