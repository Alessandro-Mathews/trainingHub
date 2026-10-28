#pragma once

#include "traininghub/models/Usuario.h"

#include <drogon/orm/DbClient.h>
#include <functional>
#include <optional>
#include <vector>

namespace traininghub::repositories
{

class UsuarioRepository
{
public:
    using FindCallback = std::function<void(const std::optional<models::Usuario> &)>;
    using ErrorCallback = drogon::orm::ExceptionCallback;
    using ListCallback = std::function<void(const std::vector<models::Usuario> &)>;
    using CreateCallback = std::function<void(std::int64_t)>;

    explicit UsuarioRepository(const drogon::orm::DbClientPtr &db);

    void criar(const models::Usuario &usuario, CreateCallback callback,
               ErrorCallback errorCallback) const;
    void buscarPorId(std::int64_t academiaId, std::int64_t id,
                     FindCallback callback, ErrorCallback errorCallback) const;
    void listarPorAcademia(std::int64_t academiaId, ListCallback callback,
                           ErrorCallback errorCallback) const;

    void findByAcademiaAndEmail(std::int64_t academiaId,
                               const std::string &email,
                               FindCallback callback,
                               ErrorCallback errorCallback) const;

private:
    drogon::orm::DbClientPtr db_;
};

}
