#include "traininghub/repositories/UsuarioRepository.h"

#include <utility>

namespace traininghub::repositories
{

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
        [callback = std::move(callback)](const drogon::orm::Result &result)
        {
            if (result.empty())
            {
                callback(std::nullopt);
                return;
            }

            const auto &row = result[0];
            models::Usuario user;
            user.id = row["id"].as<std::int64_t>();
            user.academia_id = row["academia_id"].as<std::int64_t>();
            user.perfil_id = row["perfil_id"].as<std::int64_t>();
            user.nome = row["nome"].as<std::string>();
            user.email = row["email"].as<std::string>();
            user.senha_hash = row["senha_hash"].as<std::string>();
            user.ativo = row["ativo"].as<int>() != 0;
            user.criado_em = row["criado_em"].as<std::string>();
            callback(user);
        },
        std::move(errorCallback), academiaId, email
    );
}

}
