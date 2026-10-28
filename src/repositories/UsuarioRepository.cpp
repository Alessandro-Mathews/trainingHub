#include "traininghub/repositories/UsuarioRepository.h"

#include <utility>

namespace traininghub::repositories
{
namespace
{
models::Usuario fromRow(const drogon::orm::Row &row)
{
    models::Usuario user;
    user.id = row["id"].as<std::int64_t>();
    user.academia_id = row["academia_id"].as<std::int64_t>();
    user.perfil_id = row["perfil_id"].as<std::int64_t>();
    user.nome = row["nome"].as<std::string>();
    user.email = row["email"].as<std::string>();
    user.senha_hash = row["senha_hash"].as<std::string>();
    user.ativo = row["ativo"].as<int>() != 0;
    user.criado_em = row["criado_em"].as<std::string>();
    return user;
}

auto mapOne(UsuarioRepository::FindCallback callback, UsuarioRepository::ErrorCallback errorCallback)
{
    return [callback = std::move(callback), errorCallback](const drogon::orm::Result &result)
    {
        std::optional<models::Usuario> user;
        try
        {
            if (!result.empty()) user = fromRow(result[0]);
        }
        catch (...)
        {
            errorCallback(drogon::orm::ConversionError("Failed to map Usuario database result"));
            return;
        }
        callback(user);
    };
}
}

UsuarioRepository::UsuarioRepository(const drogon::orm::DbClientPtr &db)
    : db_(db)
{
}

void UsuarioRepository::findByAcademiaAndEmail(
    std::int64_t academiaId, const std::string &email,
    FindCallback callback, ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "SELECT id, academia_id, perfil_id, nome, email, senha_hash, ativo, criado_em "
        "FROM usuario WHERE academia_id = ? AND email = ? LIMIT 1",
        mapOne(std::move(callback), errorCallback),
        errorCallback, academiaId, email
    );
}

void UsuarioRepository::criar(const models::Usuario &usuario, CreateCallback callback,
                              ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "INSERT INTO usuario (academia_id, perfil_id, nome, email, senha_hash) VALUES (?, ?, ?, ?, ?)",
        [callback = std::move(callback)](const drogon::orm::Result &result)
        {
            callback(static_cast<std::int64_t>(result.insertId()));
        }, std::move(errorCallback), usuario.academia_id, usuario.perfil_id,
        usuario.nome, usuario.email, usuario.senha_hash);
}

void UsuarioRepository::buscarPorId(std::int64_t academiaId, std::int64_t id,
                                    FindCallback callback, ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "SELECT id, academia_id, perfil_id, nome, email, senha_hash, ativo, criado_em "
        "FROM usuario WHERE academia_id = ? AND id = ?",
        mapOne(std::move(callback), errorCallback), errorCallback, academiaId, id);
}

void UsuarioRepository::listarPorAcademia(std::int64_t academiaId, ListCallback callback,
                                          ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "SELECT id, academia_id, perfil_id, nome, email, senha_hash, ativo, criado_em "
        "FROM usuario WHERE academia_id = ? ORDER BY id",
        [callback = std::move(callback), errorCallback](const drogon::orm::Result &result)
        {
            std::vector<models::Usuario> usuarios;
            try
            {
                usuarios.reserve(result.size());
                for (const auto &row : result) usuarios.push_back(fromRow(row));
            }
            catch (...)
            {
                errorCallback(drogon::orm::ConversionError("Failed to map Usuario database result"));
                return;
            }
            callback(usuarios);
        }, errorCallback, academiaId);
}

}
