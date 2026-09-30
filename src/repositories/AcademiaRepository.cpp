#include "traininghub/repositories/AcademiaRepository.h"

#include <utility>

namespace traininghub::repositories
{

AcademiaRepository::AcademiaRepository(
    const drogon::orm::DbClientPtr &db
)
    : db_(db)
{
}

void AcademiaRepository::findAll(
    FindAllCallback callback,
    ErrorCallback errorCallback
) const
{
    db_->execSqlAsync(
        "SELECT id, nome, cnpj, email, telefone, ativo, criado_em "
        "FROM academia ORDER BY id",
        [callback = std::move(callback)](const drogon::orm::Result &result)
        {
            std::vector<models::Academia> academias;
            academias.reserve(result.size());

            for (const auto &row : result)
            {
                models::Academia academia;
                academia.id = row["id"].as<std::int64_t>();
                academia.nome = row["nome"].as<std::string>();
                if (!row["cnpj"].isNull())
                    academia.cnpj = row["cnpj"].as<std::string>();
                if (!row["email"].isNull())
                    academia.email = row["email"].as<std::string>();
                if (!row["telefone"].isNull())
                    academia.telefone = row["telefone"].as<std::string>();
                academia.ativo = row["ativo"].as<int>() != 0;
                academia.criado_em = row["criado_em"].as<std::string>();
                academias.push_back(std::move(academia));
            }

            callback(academias);
        },
        std::move(errorCallback)
    );
}

}
