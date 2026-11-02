#include "traininghub/repositories/AuthContextRepository.h"

namespace traininghub::repositories
{
void AuthContextRepository::find(std::int64_t userId, Callback callback,
                                drogon::orm::ExceptionCallback errorCallback) const
{
    // One snapshot validates all three records without fetching password hashes.
    db_->execSqlAsync(
        "SELECT u.id, u.academia_id, u.perfil_id, u.ativo AS user_active, "
        "a.ativo AS academia_active, p.ativo AS perfil_active, p.nome AS perfil_name "
        "FROM usuario u LEFT JOIN academia a ON a.id = u.academia_id "
        "LEFT JOIN perfil p ON p.id = u.perfil_id WHERE u.id = ?",
        [callback, errorCallback](const drogon::orm::Result &result)
        {
            std::optional<AuthRecord> record;
            try
            {
                if (!result.empty())
                {
                    const auto &row = result[0];
                    record.emplace();
                    record->identity = {row["id"].as<std::int64_t>(),
                                        row["academia_id"].as<std::int64_t>(),
                                        row["perfil_id"].as<std::int64_t>()};
                    record->userActive = row["user_active"].as<int>() == 1;
                    record->academiaActive = !row["academia_active"].isNull()
                        && row["academia_active"].as<int>() == 1;
                    record->perfilActive = !row["perfil_active"].isNull()
                        && row["perfil_active"].as<int>() == 1;
                    if (!row["perfil_name"].isNull())
                        record->perfilName = row["perfil_name"].as<std::string>();
                }
            }
            catch (...)
            {
                errorCallback(drogon::orm::ConversionError("Failed to map authentication context"));
                return;
            }
            callback(record);
        }, errorCallback, userId);
}
}
