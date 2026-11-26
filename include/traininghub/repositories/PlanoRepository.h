#pragma once

#include "traininghub/models/Plano.h"

#include <drogon/orm/DbClient.h>
#include <functional>
#include <vector>

namespace traininghub::repositories
{
class PlanoRepository
{
public:
    using FindCallback = std::function<void(const std::optional<models::Plano> &)>;
    using ListCallback = std::function<void(const std::vector<models::Plano> &)>;
    using ErrorCallback = drogon::orm::ExceptionCallback;

    explicit PlanoRepository(const drogon::orm::DbClientPtr &db);
    void criar(std::int64_t academiaId, const std::string &nome,
        const std::optional<std::string> &descricao, std::int64_t valorCentavos,
        std::int64_t duracaoDias, FindCallback callback, ErrorCallback errorCallback) const;
    void listarPorAcademia(std::int64_t academiaId, ListCallback callback,
        ErrorCallback errorCallback) const;
    void buscarPorId(std::int64_t academiaId, std::int64_t id, FindCallback callback,
        ErrorCallback errorCallback) const;
    void atualizar(std::int64_t academiaId, std::int64_t id, const std::string &nome,
        const std::optional<std::string> &descricao, std::int64_t valorCentavos,
        std::int64_t duracaoDias, FindCallback callback, ErrorCallback errorCallback) const;
    void atualizarStatus(std::int64_t academiaId, std::int64_t id, bool ativo,
        FindCallback callback, ErrorCallback errorCallback) const;

private:
    drogon::orm::DbClientPtr db_;
};
}
