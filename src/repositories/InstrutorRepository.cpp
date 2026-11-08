#include "traininghub/repositories/InstrutorRepository.h"

#include <utility>

namespace traininghub::repositories
{
namespace
{
models::Instrutor fromRow(const drogon::orm::Row &row)
{
    return {row["id"].as<std::int64_t>(), row["usuario_id"].as<std::int64_t>(),
            row["criado_em"].as<std::string>()};
}

auto mapOne(InstrutorRepository::FindCallback callback, InstrutorRepository::ErrorCallback errorCallback)
{
    return [callback = std::move(callback), errorCallback](const drogon::orm::Result &result)
    {
        std::optional<models::Instrutor> instrutor;
        try
        {
            if (!result.empty()) instrutor = fromRow(result[0]);
        }
        catch (...)
        {
            errorCallback(drogon::orm::ConversionError("Failed to map Instrutor database result"));
            return;
        }
        callback(instrutor);
    };
}
}

InstrutorRepository::InstrutorRepository(const drogon::orm::DbClientPtr &db) : db_(db) {}

void InstrutorRepository::buscarUsuarioParaCriacao(std::int64_t academiaId, std::int64_t usuarioId,
    UsuarioCallback callback, ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "SELECT u.ativo AS usuario_ativo, a.ativo AS academia_ativa, "
        "p.ativo AS perfil_ativo, p.nome AS perfil_nome, i.id AS instrutor_id "
        "FROM usuario u LEFT JOIN academia a ON a.id = u.academia_id "
        "LEFT JOIN perfil p ON p.id = u.perfil_id LEFT JOIN instrutor i ON i.usuario_id = u.id "
        "WHERE u.academia_id = ? AND u.id = ?",
        [callback = std::move(callback), errorCallback](const drogon::orm::Result &result)
        {
            std::optional<UsuarioParaInstrutor> usuario;
            try
            {
                if (!result.empty())
                {
                    const auto &row = result[0];
                    usuario.emplace();
                    usuario->usuarioAtivo = row["usuario_ativo"].as<int>() == 1;
                    usuario->academiaAtiva = !row["academia_ativa"].isNull()
                        && row["academia_ativa"].as<int>() == 1;
                    usuario->perfilAtivo = !row["perfil_ativo"].isNull()
                        && row["perfil_ativo"].as<int>() == 1;
                    if (!row["perfil_nome"].isNull())
                        usuario->perfilNome = row["perfil_nome"].as<std::string>();
                    usuario->possuiInstrutor = !row["instrutor_id"].isNull();
                }
            }
            catch (...)
            {
                errorCallback(drogon::orm::ConversionError("Failed to map Instrutor eligibility"));
                return;
            }
            callback(usuario);
        }, errorCallback, academiaId, usuarioId);
}

void InstrutorRepository::criar(std::int64_t academiaId, std::int64_t usuarioId,
    const std::string &perfilNome, FindCallback callback, ErrorCallback errorCallback) const
{
    // Recheck eligibility in the write statement; UNIQUE is the concurrent duplicate guard.
    // RETURNING avoids a second read and returns only the row inserted by this statement.
    db_->execSqlAsync(
        "INSERT INTO instrutor (usuario_id) SELECT u.id FROM usuario u "
        "JOIN perfil p ON p.id = u.perfil_id JOIN academia a ON a.id = u.academia_id "
        "WHERE u.academia_id = ? AND u.id = ? AND u.ativo = 1 "
        "AND p.ativo = 1 AND p.nome = ? AND a.ativo = 1 "
        "RETURNING id, usuario_id, criado_em",
        mapOne(std::move(callback), errorCallback), errorCallback,
        academiaId, usuarioId, perfilNome);
}

void InstrutorRepository::buscarPorId(std::int64_t academiaId, std::int64_t id,
    FindCallback callback, ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "SELECT i.id, i.usuario_id, i.criado_em FROM instrutor i "
        "JOIN usuario u ON u.id = i.usuario_id WHERE u.academia_id = ? AND i.id = ?",
        mapOne(std::move(callback), errorCallback), errorCallback, academiaId, id);
}

void InstrutorRepository::listarPorAcademia(std::int64_t academiaId, ListCallback callback,
    ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "SELECT i.id, i.usuario_id, i.criado_em FROM instrutor i "
        "JOIN usuario u ON u.id = i.usuario_id WHERE u.academia_id = ? ORDER BY i.id",
        [callback = std::move(callback), errorCallback](const drogon::orm::Result &result)
        {
            std::vector<models::Instrutor> instrutores;
            try
            {
                instrutores.reserve(result.size());
                for (const auto &row : result) instrutores.push_back(fromRow(row));
            }
            catch (...)
            {
                errorCallback(drogon::orm::ConversionError("Failed to map Instrutor database result"));
                return;
            }
            callback(instrutores);
        }, errorCallback, academiaId);
}
}
