#include "traininghub/repositories/PlanoRepository.h"

#include <utility>

namespace traininghub::repositories
{
namespace
{
models::Plano fromRow(const drogon::orm::Row &row)
{
    models::Plano plano;
    plano.id = row["id"].as<std::int64_t>();
    plano.academiaId = row["academia_id"].as<std::int64_t>();
    plano.nome = row["nome"].as<std::string>();
    if (!row["descricao"].isNull()) plano.descricao = row["descricao"].as<std::string>();
    plano.valorCentavos = row["valor_centavos"].as<std::int64_t>();
    plano.duracaoDias = row["duracao_dias"].as<std::int64_t>();
    const auto ativo = row["ativo"].as<int>();
    if ((ativo != 0 && ativo != 1) || plano.valorCentavos < 0 || plano.duracaoDias <= 0)
        throw drogon::orm::ConversionError("Invalid Plano persisted domain");
    plano.ativo = ativo == 1;
    plano.criadoEm = row["criado_em"].as<std::string>();
    return plano;
}

auto mapOne(PlanoRepository::FindCallback callback, PlanoRepository::ErrorCallback errorCallback)
{
    return [callback = std::move(callback), errorCallback](const drogon::orm::Result &result)
    {
        std::optional<models::Plano> plano;
        try
        {
            if (!result.empty()) plano = fromRow(result[0]);
        }
        catch (...)
        {
            errorCallback(drogon::orm::ConversionError("Failed to map Plano database result"));
            return;
        }
        callback(plano);
    };
}
}

PlanoRepository::PlanoRepository(const drogon::orm::DbClientPtr &db) : db_(db) {}

void PlanoRepository::criar(std::int64_t academiaId, const std::string &nome,
    const std::optional<std::string> &descricao, std::int64_t valorCentavos,
    std::int64_t duracaoDias, FindCallback callback, ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "INSERT INTO plano (academia_id,nome,descricao,valor_centavos,duracao_dias) VALUES (?,?,?,?,?) "
        "RETURNING id,academia_id,nome,descricao,valor_centavos,duracao_dias,ativo,criado_em",
        mapOne(std::move(callback), errorCallback), errorCallback,
        academiaId, nome, descricao, valorCentavos, duracaoDias);
}

void PlanoRepository::listarPorAcademia(std::int64_t academiaId, ListCallback callback,
    ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "SELECT id,academia_id,nome,descricao,valor_centavos,duracao_dias,ativo,criado_em "
        "FROM plano WHERE academia_id = ? ORDER BY id",
        [callback = std::move(callback), errorCallback](const drogon::orm::Result &result)
        {
            std::vector<models::Plano> planos;
            try
            {
                planos.reserve(result.size());
                for (const auto &row : result) planos.push_back(fromRow(row));
            }
            catch (...)
            {
                errorCallback(drogon::orm::ConversionError("Failed to map Plano database result"));
                return;
            }
            callback(planos);
        }, errorCallback, academiaId);
}

void PlanoRepository::buscarPorId(std::int64_t academiaId, std::int64_t id,
    FindCallback callback, ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "SELECT id,academia_id,nome,descricao,valor_centavos,duracao_dias,ativo,criado_em "
        "FROM plano WHERE id = ? AND academia_id = ?",
        mapOne(std::move(callback), errorCallback), errorCallback, id, academiaId);
}

void PlanoRepository::atualizar(std::int64_t academiaId, std::int64_t id, const std::string &nome,
    const std::optional<std::string> &descricao, std::int64_t valorCentavos,
    std::int64_t duracaoDias, FindCallback callback, ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "UPDATE plano SET nome = ?, descricao = ?, valor_centavos = ?, duracao_dias = ? "
        "WHERE id = ? AND academia_id = ? "
        "RETURNING id,academia_id,nome,descricao,valor_centavos,duracao_dias,ativo,criado_em",
        mapOne(std::move(callback), errorCallback), errorCallback,
        nome, descricao, valorCentavos, duracaoDias, id, academiaId);
}

void PlanoRepository::atualizarStatus(std::int64_t academiaId, std::int64_t id, bool ativo,
    FindCallback callback, ErrorCallback errorCallback) const
{
    db_->execSqlAsync(
        "UPDATE plano SET ativo = ? WHERE id = ? AND academia_id = ? "
        "RETURNING id,academia_id,nome,descricao,valor_centavos,duracao_dias,ativo,criado_em",
        mapOne(std::move(callback), errorCallback), errorCallback, ativo ? 1 : 0, id, academiaId);
}
}
