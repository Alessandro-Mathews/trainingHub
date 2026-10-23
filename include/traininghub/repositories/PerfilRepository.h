#pragma once

#include "traininghub/models/Perfil.h"

#include <drogon/orm/DbClient.h>
#include <functional>
#include <optional>
#include <vector>

namespace traininghub::repositories
{

class PerfilRepository
{
public:
    using ListCallback = std::function<void(const std::vector<models::Perfil> &)>;
    using FindCallback = std::function<void(const std::optional<models::Perfil> &)>;
    using CreateCallback = std::function<void(std::int64_t)>;
    using ChangeCallback = std::function<void(bool)>;
    using ErrorCallback = drogon::orm::ExceptionCallback;

    explicit PerfilRepository(const drogon::orm::DbClientPtr &db);

    void listar(ListCallback callback, ErrorCallback errorCallback) const;
    void buscarPorId(std::int64_t id, FindCallback callback,
                     ErrorCallback errorCallback) const;
    void criar(const models::Perfil &perfil, CreateCallback callback,
               ErrorCallback errorCallback) const;
    void atualizar(std::int64_t id, const models::Perfil &perfil,
                   ChangeCallback callback, ErrorCallback errorCallback) const;
    void excluir(std::int64_t id, ChangeCallback callback,
                 ErrorCallback errorCallback) const;

private:
    drogon::orm::DbClientPtr db_;
};

}
