#include "traininghub/repositories/PerfilRepository.h"

#include <utility>

namespace traininghub::repositories
{
namespace
{
models::Perfil fromRow(const drogon::orm::Row &row)
{
    models::Perfil perfil;
    perfil.id = row["id"].as<std::int64_t>();
    perfil.nome = row["nome"].as<std::string>();
    if (!row["descricao"].isNull())
        perfil.descricao = row["descricao"].as<std::string>();
    perfil.ativo = row["ativo"].as<int>();
    perfil.criado_em = row["criado_em"].as<std::string>();
    return perfil;
}
}

PerfilRepository::PerfilRepository(const drogon::orm::DbClientPtr &db)
    : db_(db)
{
}

void PerfilRepository::listar(ListCallback callback, ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "SELECT id, nome, descricao, ativo, criado_em FROM perfil ORDER BY id",
        [callback = std::move(callback), errorCallback](const drogon::orm::Result &result)
        {
            std::vector<models::Perfil> perfis;
            try
            {
                perfis.reserve(result.size());
                for (const auto &row : result)
                    perfis.push_back(fromRow(row));
            }
            catch (...)
            {
                errorCallback(drogon::orm::ConversionError("Failed to map Perfil database result"));
                return;
            }
            callback(perfis);
        },
        errorCallback);
}

void PerfilRepository::buscarPorId(std::int64_t id, FindCallback callback,
                                  ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "SELECT id, nome, descricao, ativo, criado_em FROM perfil WHERE id = ?",
        [callback = std::move(callback), errorCallback](const drogon::orm::Result &result)
        {
            std::optional<models::Perfil> perfil;
            try
            {
                if (!result.empty())
                    perfil = fromRow(result[0]);
            }
            catch (...)
            {
                errorCallback(drogon::orm::ConversionError("Failed to map Perfil database result"));
                return;
            }
            callback(perfil);
        },
        errorCallback, id);
}

void PerfilRepository::criar(const models::Perfil &perfil, CreateCallback callback,
                            ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "INSERT INTO perfil (nome, descricao, ativo) VALUES (?, ?, ?)",
        [callback = std::move(callback)](const drogon::orm::Result &result)
        {
            callback(static_cast<std::int64_t>(result.insertId()));
        },
        std::move(errorCallback), perfil.nome, perfil.descricao, perfil.ativo);
}

void PerfilRepository::atualizar(std::int64_t id, const models::Perfil &perfil,
                                ChangeCallback callback, ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "UPDATE perfil SET nome = ?, descricao = ?, ativo = ? WHERE id = ?",
        [callback = std::move(callback)](const drogon::orm::Result &result)
        {
            callback(result.affectedRows() > 0);
        },
        std::move(errorCallback), perfil.nome, perfil.descricao, perfil.ativo, id);
}

void PerfilRepository::excluir(std::int64_t id, ChangeCallback callback,
                              ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "DELETE FROM perfil WHERE id = ?",
        [callback = std::move(callback)](const drogon::orm::Result &result)
        {
            callback(result.affectedRows() > 0);
        },
        std::move(errorCallback), id);
}

}
